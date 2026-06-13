---
Spec_ID: "SPEC_04"
Title: "Memory Architecture - Session, Working Memory and Long-term Storage"
Version: "0.1.0-MVP"
Maturity_Level: "Semilla"
Status: "Draft"
Target_Agent: "sdd-apply"
Context_Tags: ["#Memory", "#Engram", "#ContextCompression", "#Session"]
Dependency_Hashes: ["SPEC_00", "SPEC_01", "SPEC_02"]
Last_Updated: "2026-06-13"
---

# SPEC_04_MEMORY_ARCHITECTURE

> **Propósito**: Definir las capas de memoria (sesión, working memory, long-term memory), políticas de compresión de contexto, deduplicación y gobernanza de seguridad para yaml-agno.

---

## 1. MEMORY LAYERS AND TOKENS LIMITS

### 1.1 Arquitectura de Memoria

```mermaid
graph TB
    subgraph["Layer 1: Input/Output"]
        [User Message]
        [Agent Response]
    end
    
    subgraph["Layer 2: Session Memory (PostgreSQL)"]
        [SessionContext]
        [Message History]
        [Agent States]
    end
    
    subgraph["Layer 3: Working Memory (Agno Internal)"]
        [Current Run Context]
        [Tool Call Results]
        [Intermediate Variables]
    end
    
    subgraph["Layer 4: Long-term Memory (Engram)"]
        [Past Sessions]
        [Learnings]
        [Domain Knowledge]
    end
    
    [User Message] --> [SessionContext]
    [Agent Response] --> [SessionContext]
    [SessionContext] --> |Load into context| [Current Run Context]
    [Current Run Context] --> |Relevant findings| [Long-term Memory]
    [Long-term Memory] -.-> |Recall| [Current Run Context]
```

### 1.2 Memoria por Capa

| Capa | Storage | TTL | Max Tokens | Responsabilidad |
|------|---------|-----|------------|-----------------|
| **Session Memory** | PostgreSQL | 30 días | 100K tokens | Historial completo de conversación |
| **Working Memory** | Agno internal | 1 sesión | 8K tokens | Contexto del run actual |
| **Long-term Memory** | Engram | Permanente | ∞ (deduplicado) | Aprendizaje cross-session |

### 1.3 Configuración de Memoria YAML

```yaml
agent:
  name: "my_agent"
  # ...
  
  memory:
    # Session memory (PostgreSQL)
    session:
      enabled: true
      storage_type: postgres  # sqlite|postgres|memory
      retention_days: 30
      max_messages: 100
    
    # Working memory (Agno)
    working:
      max_context_tokens: 8000
      compression_threshold: 6000  # Trigger compression al 75%
      include_tool_calls: true
    
    # Long-term memory (Engram)
    long_term:
      enabled: true
      project: "yaml-agno"
      scope: project  # project|personal
      
      # Recall settings
      recall_on_start: true  # Recall mem_context al inicio
      recall_keywords: ["previous", "past", "learned", "remembered"]
      
      # Save settings
      save_on_decision: true  # Auto-save decisiones
      save_on_discovery: true  # Auto-save descubrimientos
      save_on_bugfix: true  # Auto-save bug fixes
```

---

## 2. CONTEXT COMPRESSION AND DEDUPLICATION

### 2.1 Algoritmo de Compresión de Contexto

**Estrategia**: Semantic compression con preservación de información clave

```python
# yaml-agno/src/memory/compression.py

from typing import List, Dict, Any
from datetime import datetime, timedelta

class ContextCompressor:
    """Comprime contexto de sesión cuando se excede threshold"""
    
    def __init__(self, threshold_tokens: int = 6000):
        self.threshold_tokens = threshold_tokens
    
    def should_compress(self, current_tokens: int) -> bool:
        """Decide si es necesario comprimir"""
        return current_tokens >= self.threshold_tokens
    
    def compress_history(
        self,
        messages: List[Dict[str, Any]],
        target_tokens: int = 4000
    ) -> List[Dict[str, Any]]:
        """
        Comprime historial manteniendo mensajes importantes.
        
        Estrategia:
        1. Preservar últimos N mensajes (recientes)
        2. Preservar mensajes con tool_call results
        3. Resumir mensajes intermedios
        """
        if not messages:
            return []
        
        # 1. Identificar mensajes importantes (no eliminar)
        important = self._identify_important(messages)
        
        # 2. Resumir mensajes no importantes
        summarized = self._summarize_messages(
            [m for m in messages if not important.get(m.get("id"))],
            target_tokens=target_tokens
        )
        
        # 3. Reconstruir con importantes + resumen
        compressed = [
            m for m in messages
            if important.get(m.get("id"))
        ] + [summarized]
        
        return compressed
    
    def _identify_important(self, messages: List[Dict[str, Any]]) -> Dict[str, bool]:
        """Identifica mensajes que NO deben comprimirse"""
        important = {}
        
        for msg in messages:
            msg_id = msg.get("id")
            if not msg_id:
                continue
            
            # Importar si:
            # - Es uno de los últimos 5 mensajes
            # - Contiene tool_call
            # - Contiene error
            # - Es el primer mensaje del usuario
            is_important = (
                msg == messages[-1] or  # Último mensaje
                msg == messages[-2] or  # Penúltimo
                msg.get("role") == "tool" or  # Tool result
                "error" in msg.get("content", "").lower() or  # Error
                msg == messages[0]  # Primer mensaje
            )
            
            important[msg_id] = is_important
        
        return important
    
    def _summarize_messages(self, messages: List[Dict[str, Any]], target_tokens: int) -> Dict[str, Any]:
        """Resume grupo de mensajes en un solo mensaje"""
        if not messages:
            return {}
        
        # TODO: Implementar LLM call para resumir
        # Por ahora, concatenar con indicador de resumen
        return {
            "id": f"summary_{datetime.utcnow().timestamp()}",
            "role": "system",
            "content": f"[{len(messages)} messages summarized for context compression]",
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": {"compressed": True, "original_count": len(messages)}
        }
```

### 2.2 Deduplicación en Engram

**Estrategia**: Engram MCP tiene deduplicación automática por `topic_key`

```yaml
# yaml-agno/src/memory/engram_manager.py

from typing import Optional, List
from pydantic import BaseModel

class EngramMemoryManager:
    """Gestiona memoria de largo plazo via Engram MCP"""
    
    def __init__(self, project: str, session_id: str):
        self.project = project
        self.session_id = session_id
    
    async def save_decision(
        self,
        title: str,
        content: str,
        where: str,
        learned: str | None = None
    ) -> None:
        """
        Guarda decisión arquitectónica en Engram.
        
        Usa topic_key para upsert (evita duplicados).
        """
        from .engram_utils import mem_save  # MCP tool
        
        await mem_save(
            title=title,
            type="decision",
            content=f"**What**: {content}\n**Where**: {where}\n**Learned**: {learned or ''}",
            project=self.project,
            session_id=self.session_id
        )
    
    async def save_discovery(
        self,
        title: str,
        content: str,
        where: str | None = None
    ) -> None:
        """Guarda descubrimiento técnico"""
        from .engram_utils import mem_save
        
        await mem_save(
            title=title,
            type="discovery",
            content=f"**What**: {content}\n**Where**: {where or 'Unknown'}",
            project=self.project,
            session_id=self.session_id
        )
    
    async def search_relevant(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Busca memoria relevante para contexto actual"""
        from .engram_utils import mem_search, mem_get_observation
        
        results = await mem_search(
            query=query,
            project=self.project,
            limit=limit
        )
        
        # Obtener contenido completo de cada resultado
        memories = []
        for result in results:
            full_obs = await mem_get_observation(id=result["id"])
            memories.append(full_obs)
        
        return memories
```

---

## 3. MEMORY GOVERNANCE AND SECURITY RULES

### 3.1 Políticas de Aislamiento

| Regla | Implementación | Verificación |
|-------|----------------|--------------|
| **Tenant Isolation** | RLS en PostgreSQL + `tenant_id` en todas las queries | `assert session.tenant_id == current_tenant` |
| **User Isolation** | `user_id` en session_contexts | Queries filtradas por `user_id` |
| **Session Isolation** | `session_id` único por sesión | `session_contexts.session_id UNIQUE` |

### 3.2 Desidentificación de PII

**Estrategia**: Masking automático de datos sensibles antes de guardar en memoria

```python
# yaml-agno/src/memory/pii_sanitizer.py

import re
from typing import Any, Dict

class PIISanitizer:
    """Sanitiza PII antes de persistir"""
    
    # Patterns para detectar PII
    PATTERNS = {
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "credit_card": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
        "phone": r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",
    }
    
    def sanitize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitiza PII en diccionario recursivamente"""
        if isinstance(data, dict):
            return {k: self.sanitize(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.sanitize(item) for item in data]
        elif isinstance(data, str):
            return self._sanitize_string(data)
        else:
            return data
    
    def _sanitize_string(self, text: str) -> str:
        """Sanitiza PII en string"""
        sanitized = text
        
        for pii_type, pattern in self.PATTERNS.items():
            matches = re.finditer(pattern, sanitized)
            for match in matches:
                original = match.group()
                masked = self._mask_value(original, pii_type)
                sanitized = sanitized.replace(original, masked)
        
        return sanitized
    
    def _mask_value(self, value: str, pii_type: str) -> str:
        """Enmascara valor según tipo"""
        if pii_type == "email":
            # user@domain.com -> u***@domain.com
            parts = value.split("@")
            return f"{parts[0][0]}***@{parts[1]}"
        elif pii_type == "ssn":
            # 123-45-6789 -> ***-**-****
            return "***-**-****"
        elif pii_type == "credit_card":
            # 1234-5678-9012-3456 -> ****-****-****-3456
            parts = value.split("-")
            return f"****-****-****-{parts[-1]}"
        elif pii_type == "phone":
            # 123-456-7890 -> ***-***-7890
            parts = value.split("-")
            return f"***-***-{parts[-1]}"
        else:
            return "***"
```

### 3.3 Enmascaramiento de Secretos

**Estrategia**: Detectar y enmascarar secretos antes de persistir

```python
# yaml-agno/src/memory/secret_sanitizer.py

import os
from typing import Dict, Any

class SecretSanitizer:
    """Enmascara secretos (API keys, tokens, passwords)"""
    
    # Prefixes comunes de secretos
    SECRET_PATTERNS = [
        "api_key", "apikey", "api-key",
        "secret", "secret_key", "secretkey",
        "token", "access_token", "auth_token",
        "password", "pass",
        "private_key", "privatekey",
    ]
    
    def sanitize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitiza secretos en diccionario"""
        if isinstance(data, dict):
            sanitized = {}
            for k, v in data.items():
                if self._is_secret_key(k):
                    sanitized[k] = self._mask_secret(v)
                else:
                    sanitized[k] = self.sanitize(v)
            return sanitized
        else:
            return data
    
    def _is_secret_key(self, key: str) -> bool:
        """Detecta si key es secreto"""
        key_lower = key.lower()
        return any(pattern in key_lower for pattern in self.SECRET_PATTERNS)
    
    def _mask_secret(self, value: Any) -> str:
        """Enmascara valor secreto"""
        if isinstance(value, str):
            if len(value) <= 8:
                return "***"
            else:
                # Mostrar primeros 4 y últimos 4 caracteres
                return f"{value[:4]}...{value[-4:]}"
        else:
            return "***"
```

### 3.4 Reglas de Retención (GDPR)

| Tipo de Dato | Retención | Justificación |
|--------------|-----------|---------------|
| **Session messages** | 30 días | GDPR - derecho al olvido |
| **Agent execution logs** | 90 días | Debugging, compliance |
| **Domain events** | 7 días | Event sourcing window |
| **Long-term memory (Engram)** | Permanente | Aprendizaje cross-session |
| **PII data** | Masked siempre | Privacy by design |

---

## 4. MEMORY ACCESS PATTERNS

### 4.1 Patrón: Recall al Inicio de Sesión

```python
# yaml-agno/src/memory/session_bootstrap.py

class SessionBootstrap:
    """Bootstrap de sesión con recall de memoria"""
    
    async def initialize_session(
        self,
        user_id: str,
        session_id: str,
        tenant_id: str
    ) -> SessionContext:
        """
        Inicializa sesión con recall automático.
        
        1. Recall Engram context (opcional)
        2. Cargar session_contexts desde PostgreSQL
        3. Inicializar working memory
        """
        # 1. Recall de Engram (si configurado)
        if self.config.recall_on_start:
            past_context = await self.recall_past_context(user_id)
            # TODO: Inyectar en system prompt
        
        # 2. Cargar sesión existente o crear nueva
        session = await self.load_or_create_session(
            user_id=user_id,
            session_id=session_id,
            tenant_id=tenant_id
        )
        
        # 3. Verificar TTL
        if self._is_expired(session):
            await self.cleanup_expired(session)
            session = await self.create_new_session(...)
        
        return session
    
    async def recall_past_context(self, user_id: str) -> List[Dict[str, Any]]:
        """Recall contexto pasado desde Engram"""
        manager = EngramMemoryManager(
            project=self.config.project,
            session_id=self.session_id
        )
        
        # Buscar memorias relevantes
        memories = await manager.search_relevant(
            query=f"user:{user_id} past sessions decisions",
            limit=10
        )
        
        return memories
```

### 4.2 Patrón: Save-on-Decision

```python
# yaml-agno/src/memory/autosave.py

class AutosaveManager:
    """Guarda automáticamente decisiones y descubrimientos"""
    
    async def on_agent_decision(
        self,
        agent_name: str,
        decision: str,
        reasoning: str
    ) -> None:
        """Callback cuando agente toma decisión"""
        if not self.config.save_on_decision:
            return
        
        manager = EngramMemoryManager(
            project=self.config.project,
            session_id=self.session_id
        )
        
        await manager.save_decision(
            title=f"Decision by {agent_name}",
            content=decision,
            where=agent_name,
            learned=reasoning
        )
    
    async def on_discovery(
        self,
        title: str,
        content: str,
        where: str | None = None
    ) -> None:
        """Callback cuando se hace descubrimiento"""
        if not self.config.save_on_discovery:
            return
        
        manager = EngramMemoryManager(...)
        await manager.save_discovery(title=title, content=content, where=where)
```

---

## 5. BEHAVIOR DELTA - BDD SCENARIOS

### 5.1 Escenarios de Aceptación

#### Scenario 1: Golden Path - Session Memory Creation

```gherkin
GIVEN a user starts a new session
WHEN the session is initialized
THEN a SessionContext is created
AND the session_state is "active"
AND message_history is empty array
AND created_at and last_activity are set
```

#### Scenario 2: Golden Path - Context Compression

```gherkin
GIVEN a session with 150 messages (exceeding threshold)
AND the context exceeds 8000 tokens
WHEN compression is triggered
THEN the message history is reduced
AND recent messages (last 5) are preserved
AND tool_call messages are preserved
AND intermediate messages are summarized
AND the compressed context is under 4000 tokens
```

#### Scenario 3: Error Case - PII Not Sanitized

```gherkin
GIVEN a message containing PII "user@example.com"
WHEN the message is saved to memory
THEN the email is sanitized to "u***@example.com"
AND the sanitized version is persisted
AND the original email is NOT in the database
```

#### Scenario 4: Golden Path - Engram Recall

```gherkin
GIVEN a user with past decisions in Engram
AND recall_on_start is enabled
WHEN a new session starts
THEN past decisions are recalled
AND relevant memories are injected into context
AND the agent has awareness of past work
```

---

## 6. TDD MICRO-TASK EXECUTION PROTOCOL

### 6.1 Cascading Task Checklist

#### TASK_001: Define SessionContext Model

- **File**: `yaml-agno/src/memory/models/session_context.py`
- **Test**: `tests/unit/memory/test_session_context.py`
- **RED**:
  ```python
  def test_session_context_creation():
      ctx = SessionContext(
          session_id="s1",
          user_id="u1",
          tenant_id="t1"
      )
      assert ctx.session_state == SessionState.ACTIVE
  ```
- **GREEN**: Implementar `SessionContext` con Pydantic
- **Commit**: `feat: add SessionContext model`

#### TASK_002: Implement Add Message with FIFO

- **File**: `yaml-agno/src/memory/models/session_context.py`
- **Test**: `tests/unit/memory/test_session_context.py`
- **RED**:
  ```python
  def test_add_message_with_fifo():
      ctx = SessionContext(
          session_id="s1",
          user_id="u1",
          tenant_id="t1",
          max_history_size=3
      )
      ctx.add_message("user", "msg1")
      ctx.add_message("user", "msg2")
      ctx.add_message("user", "msg3")
      ctx.add_message("user", "msg4")
      assert len(ctx.message_history) == 3
      assert ctx.message_history[0]["content"] == "msg2"  # msg1 evicted
  ```
- **GREEN**: Implementar `add_message()` con FIFO eviction
- **Commit**: `feat: add FIFO message history`

#### TASK_003: Implement ContextCompressor

- **File**: `yaml-agno/src/memory/compression.py`
- **Test**: `tests/unit/memory/test_compression.py`
- **RED**:
  ```python
  def test_should_compress_at_threshold():
      compressor = ContextCompressor(threshold_tokens=6000)
      assert compressor.should_compress(6000) is True
      assert compressor.should_compress(5999) is False
  ```
- **GREEN**: Implementar `ContextCompressor.should_compress()`
- **Commit**: `feat: add ContextCompressor threshold check`

#### TASK_004: Implement Identify Important Messages

- **File**: `yaml-agno/src/memory/compression.py`
- **Test**: `tests/unit/memory/test_compression.py`
- **RED**:
  ```python
  def test_identify_important_messages():
      compressor = ContextCompressor()
      messages = [
          {"id": "1", "role": "user", "content": "first"},
          {"id": "2", "role": "tool", "content": "result"},
          {"id": "3", "role": "user", "content": "last"}
      ]
      important = compressor._identify_important(messages)
      assert important["1"] is True  # First message
      assert important["2"] is True  # Tool message
      assert important["3"] is True  # Last message
  ```
- **GREEN**: Implementar `_identify_important()`
- **Commit**: `feat: add important message identification`

#### TASK_005: Implement PIISanitizer

- **File**: `yaml-agno/src/memory/pii_sanitizer.py`
- **Test**: `tests/unit/memory/test_pii_sanitizer.py`
- **RED**:
  ```python
  def test_sanitize_email():
      sanitizer = PIISanitizer()
      result = sanitizer._sanitize_string("user@example.com")
      assert result == "u***@example.com"
  ```
- **GREEN**: Implementar `PIISanitizer._sanitize_string()`
- **Commit**: `feat: add PII email sanitization`

#### TASK_006: Implement SecretSanitizer

- **File**: `yaml-agno/src/memory/secret_sanitizer.py`
- **Test**: `tests/unit/memory/test_secret_sanitizer.py`
- **RED**:
  ```python
  def test_sanitize_api_key():
      sanitizer = SecretSanitizer()
      result = sanitizer.sanitize({"api_key": "sk-1234567890"})
      assert result["api_key"] == "sk-...7890"
  ```
- **GREEN**: Implementar `SecretSanitizer.sanitize()`
- **Commit**: `feat: add secret masking`

#### TASK_007: Implement EngramMemoryManager

- **File**: `yaml-agno/src/memory/engram_manager.py`
- **Test**: `tests/integration/memory/test_engram_manager.py`
- **RED**:
  ```python
  async def test_save_decision(engram_manager):
      await engram_manager.save_decision(
          title="Test Decision",
          content="Decision content",
          where="test.py"
      )
      # Verify via mem_search
      results = await engram_manager.search_relevant("test decision")
      assert len(results) >= 1
  ```
- **GREEN**: Implementar `EngramMemoryManager.save_decision()`
- **Commit**: `feat: add Engram decision saving`

#### TASK_008: Implement Recall on Start

- **File**: `yaml-agno/src/memory/session_bootstrap.py`
- **Test**: `tests/integration/memory/test_session_bootstrap.py`
- **RED**:
  ```python
  async def test_recall_on_start(bootstrap):
      session = await bootstrap.initialize_session(
          user_id="test_user",
          session_id="test_session",
          tenant_id="test_tenant"
      )
      assert session is not None
      assert session.session_state == SessionState.ACTIVE
  ```
- **GREEN**: Implementar `SessionBootstrap.initialize_session()`
- **Commit**: `feat: add session initialization with recall`

---

## 7. SUPUESTOS TÉCNICOS ADOPTADOS

### [Decisión 1] Memoria de Sesión en PostgreSQL

**Justificación**:
- ACID transactions para consistency
- Soporta JSONB para message_history flexible
- Particionamiento para retención eficiente
- Mejor que Redis para persistencia (>30 días)

### [Decisión 2] Engram para Long-term Memory

**Justificación**:
- Sobrevive compactación de contexto
- Deduplicación automática por `topic_key`
- Búsqueda semántica (`mem_search`)
- Integración MCP nativa

### [Decisión 3] Compresión por Importancia

**Justificación**:
- Preservar últimos N mensajes (recencia)
- Preservar tool_call results (importante para debugging)
- Resumir mensajes intermedios (reduce tokens)

---

## 8. PREGUNTAS DE CALIBRACIÓN ESTRATÉGICA

### [Pregunta 1] Threshold de Compresión

**¿Es 6000 tokens (75% de 8000) el threshold óptimo para trigger compresión?**

Implica:
- **Demasiado bajo**: Compresión frecuente, pérdida de contexto
- **Demasiado alto**: Riesgo de exceder límite de modelo
- **Trade-off**: Frecuencia de compresión vs profundidad de contexto

### [Pregunta 2] Retención de Memoria Long-term

**¿Debería haber retención máxima para Engram (ej: 1000 memorias por usuario)?**

Implica:
- **Sí**: Limita storage cost, fuerza relevancia
- **No**: Memoria ilimitada, mejor para descubrimiento
- **Trade-off**: Storage cost vs capacidad de recuerdo

### [Pregunta 3] Compartición de Memoria entre Tenants

**¿Debería permitirse compartir memoria entre tenants del mismo cliente?**

Implica:
- **Sí**: Requiere opt-in, menor aislamiento
- **No**: Aislamiento estricto, mayor security
- **Trade-off**: Flexibilidad vs seguridad

---

*¿Deseas profundizar la especificación técnica al **Nivel 6** de algún componente específico o autorizar la ejecución de estas tareas por parte del equipo de agentes?*
