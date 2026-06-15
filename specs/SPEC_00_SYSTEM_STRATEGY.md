---
Spec_ID: "SPEC_00"
Title: "System Strategy - Vision, Principles and Strategic Constraints"
Version: "0.1.0-MVP"
Maturity_Level: "Semilla"
Status: "Draft"
Target_Agent: "sdd-apply"
Context_Tags: ["#Strategy", "#Vision", "#Roadmap", "#Principles"]
Dependency_Hashes: []
Last_Updated: "2026-06-13"
---

# SPEC_00_SYSTEM_STRATEGY

> **Propósito**: Definir el marco conceptual y las directrices inmutables de negocio y tecnología del sistema yaml-agno.

---

## 1. PURPOSE AND STRATEGIC INTENT

### 1.1 Propósito del Proyecto

**yaml-agno** es una librería pip-installable que permite definir **agentes, equipos y workflows de Agno enteramente en YAML**, con **50+ templates auto-prompted**, **Dependency Injection System** para variables dinámicas, y abstracción completa de **80+ parámetros de Agent()**, **Team()**, y **6 primitivas de Workflow**.

### 1.2 Problema que Resuelve

- **Complejidad de Agno Framework**: Agno tiene 80+ parámetros de configuración que requieren código Python
- **Curva de aprendizaje empinada**: Nuevo usuarios deben aprender Python + Agno internals
- **Falta de estandarización**: No existe un formato canónico para compartir configuraciones de agentes
- **Dificultad de versioning**: Configuraciones en código son difíciles de versionar y comparar

### 1.3 Solución Propuesta

- **YAML-First**: Todo se configura vía YAML, no código Python
- **Templates Auto-Prompted**: 50+ templates con frontmatter que describen uso
- **DI System**: Variables dinámicas desde DB/API/Env sin modificar YAML
- **Interconocimiento Cognitivo**: Teams conocen sus I/O schemas
- **Caja Negra**: Clientes ven I/O, desarrolladores ven YAML

---

## 2. VISION AND FUTURE EVOLUTION

### 2.1 Fase 1: Herramienta Interna CENF (Ahora)

- yaml-agno como herramienta interna para CENF
- Meta-agentes de apoyo (Agno Docs Expert, Prompting Expert)
- Validación con casos reales (Facturación AFIP, Excel Processing)

### 2.2 Fase 2: Ambots-Hs (Futuro)

- Sistema agéntico open-source
- Marketplace de templates
- Multi-language support
- Community contributions

### 2.3 Evolución del Producto

```
Semilla (Ahora) → Estándar (6 meses) → Élite (12 meses) → Futuro (18 meses)
```

---

## 3. CORE PRINCIPLES

### 3.1 Principios Inmutables

1. **YAML-First**: Todo config vía YAML, no Python code para users
2. **Caja Negra**: Clientes ven I/O, developers ven YAML
3. **Interconocimiento Cognitivo**: Teams conocen sus I/O schemas
4. **DI System**: Variables dinámicas desde DB/API/Env
5. **Templates Auto-Prompted**: Frontmatter describe uso
6. **CEL + Callables**: Ambos desde día uno
7. **Multi-tenant Ready**: ConfigDB + hot-reload
8. **Zero-Trust Security**: PII sanitization, secret masking

### 3.2 Principios Arquitectónicos

- **Clean Architecture**: Dependencias hacia adentro (dominio)
- **DDD Táctico**: Bounded contexts, aggregates, value objects
- **CQRS**: Separación de commands (escritura) y queries (lectura)
- **Hexagonal**: Ports y adapters para infraestructura
- **Event-Loop Safety**: Async/await sin bloqueos
- **Boundary Validation**: Validación en frontera con Pydantic V2

---

## 4. MANDATORY ECOSYSTEM PRIMITIVES

### 4.1 Agno Framework Primitives

- **Agent() constructor**: 80+ parámetros
- **Team() constructor**: Todos los parámetros
- **Workflow primitives**: 6 tipos (Step, Steps, Parallel, Condition, Router, Loop)
- **Tools**: FunctionToolkit, toolkits
- **Knowledge**: Vector DBs, file systems
- **Memory**: Session, working, long-term
- **Learning**: Adaptive learning per agent

### 4.2 External Primitives

- **CEL (Common Expression Language)**: Para condiciones en workflows
- **MCP (Model Context Protocol)**: Para tool exposure
- **CodeGraph**: External repo con Agno code semantic graph
- **Pydantic V2**: Para validación de datos
- **FastAPI**: Para AgentOS (opcional)
- **PostgreSQL**: Para producción (opcional)

---

## 5. BOUNDED CONTEXTS

### 5.1 Contexto: yaml-agno Core

**Responsabilidad**: Traducir YAML → Agno Objects

- **AgentFactory**: YAML → Agent()
- **TeamFactory**: YAML → Team()
- **WorkflowFactory**: YAML → Workflow()
- **DIFactory**: Resolver ${provider.key}
- **TemplateManager**: 50+ templates con frontmatter

### 5.2 Contexto: Meta-Agentes

**Responsabilidad**: Apoyar creación de configs

- **Agno Docs Expert**: Búsqueda en docs de Agno
- **Prompting Expert**: Mejora de prompts
- **Code Expert**: CodeGraph integration

### 5.3 Contexto: Cliente Real

**Responsabilidad**: Validar YAML con casos reales

- **Team Facturación**: Procesa facturas AFIP
- **Team Excel**: Processing de Excel files
- **Team Email**: Processing de emails

---

## 6. STRATEGIC CONSTRAINTS

### 6.1 Constraints de Desarrollo

- **Strict TDD**: 100%+ coverage
- **Feature-Branch-Chain**: Git workflow
- **Code Review**: Opus 4.8 mandatory
- **PR Budget**: 200-250 lines max

### 6.2 Constraints de Diseño

- **No reimplementar Agno**: Build ON TOP
- **No AgentOS internals**: lifespan, session, run loop
- **No env vars directos**: Deployment-level
- **YAML válido**: Schema validation estricta

### 6.3 Constraints de Deployment

- **Multi-tenant**: Tenant isolation obligatorio
- **Hot-reload**: Config changes sin restart
- **Rollback**: Capacidad de rollback rápido

---

## 7. TECHNICAL ASSUMPTIONS ADOPTED

### 7.1 Assumptions de Stack

- **Python 3.12+**: Version mínima
- **PostgreSQL 16+**: Para producción
- **Pydantic V2**: Para validación
- **SQLAlchemy 2.0**: Para DB ORM
-  Para API

### 7.2 Assumptions de Agno

- **Agno estable**: API no cambia entre minor versions
- **Agent.run() síncrono y asíncrono**: Ambos disponibles
- **Teams supports 5 modes**: coordinate, route, broadcast, tasks, coroutine
- **Workflows support 6 primitives**: Step, Steps, Parallel, Condition, Router, Loop

### 7.3 Assumptions de Deployment

- **Kubernetes**: Para orquestación
- **Docker**: Para containers
- **GitOps**: Para deployments

---

## 8. ROADMAP (12 SEMANAS - MVPS SEMANALES)

| Semana | MVP | yaml-agno | Meta-Agent/Producto | Validación |
|--------|-----|-----------|--------------------|------------|
| **1** | yaml-agno Core | Agent config + Templates (50+) + DI System | — | Crear 1 agent desde YAML |
| **2** | Teams + Docs Expert | Team config + Workflow primitives | **Agno Docs Expert** | Docs Expert ayuda a crear 1 Team |
| **3** | Prompting + cognitive_profile | cognitive_profile + deployment.mode | **Prompting + Ing. Contexto** | Prompting Expert mejora 1 Team |
| **4** | Protocols + Comunicación | MCP/A2A/ACP + Guardrails + HITL | — | 2 teams se comunican |
| **5** | CodeGraph + Code Expert | CodeGraph + Skills, Multimodal, Compression | **Agno Code Expert** | CodeGraph Expert crea 1 Team |
| **6** | Team Templates | Template system + Facturación AFIP | **Team Facturación** | Team procesa 1 solicitud real |
| **7** | Multi-Tenant + Hot-Reload | ConfigDB multi-tenant + Excel Processing | **Team Excel Processing** | 2 clientes con mismo codebase |
| **8** | Integración Orquestador | Gus/Cloud + Email Processing | **Team Email** | Gus coordina 3 teams |
| **9** | Learning Machine | — | **Learning Machine** | Analiza 5 teams |
| **10** | Optimización + Meetings | Model Selector + Meeting Summarization | **Team Meetings** | 4 teams optimizados |
| **11** | Docs + Examples | Docs completas + 10+ examples | — | Developer externo crea 1 team |
| **12** | Release 1.0 | pip installable + tests 100%+ | — | 2 clientes CENF en producción |

---

## 9. CORE INFRA MANAGER INTEGRATION

### 9.1 ConfigManager Integration

**Responsabilidad**: Fuente única de verdad para configuración inmutable de entorno.

**Port (Protocol)**:
```python
from __future__ import annotations
from typing import Protocol, Literal

Env = Literal['local', 'dev', 'staging', 'prod']

class ConfigManager(Protocol):
    """@ai-directive: No accedas a os.environ directamente; siempre usa ConfigManager."""
    def get_env(self) -> Env: ...
    def get_string(self, key: str, default_value: str | None = None) -> str: ...
    def get_number(self, key: str, default_value: float | None = None) -> float: ...
    def get_boolean(self, key: str, default_value: bool | None = None) -> bool: ...
    def get_json[T](self, key: str, default_value: T | None = None) -> T: ...
    def get_section[T: dict](self, namespace: str) -> T: ...
    async def reload(self) -> None: ...
```

**Uso en yaml-agno**:
```python
# yaml-agno/src/config/agent_factory.py

class AgentFactory:
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
    
    async def create_agent(self, yaml_path: str) -> Agent:
        # Obtener configuración de tenant desde ConfigManager
        tenant_id = self.config.get_string("tenant_id")
        env = self.config.get_env()
        
        # Cargar YAML con variables DI resueltas
        yaml_content = await self._load_yaml(yaml_path)
        resolved = await self._resolve_di_variables(yaml_content)
        
        return Agent(**resolved)
```

**Do's & Don'ts**:
- ✅ Resolver precedencia: Env vars > Remoto > Ficheros > Defaults
- ✅ Validar con Pydantic V2 en bootstrap
- ❌ NO leer secretos (usar SecretManager)
- ❌ NO escribir configuración (read-only)

---

## 10. SUPUESTOS TÉCNICOS ADOPTADOS

### [Decisión 1] YAML-First como Arquitectura Core

**Justificación**: YAML es humano-legible, versionable, y permite templates con frontmatter. Users no necesitan Python.

### [Decisión 2] DI System con 4 Providers

**Justificación**: Database (queries), Env (variables), API (REST), File (JSON/YAML/TOML) cubren 99% de casos reales.

### [Decisión 3] Templates Auto-Prompted con Frontmatter

**Justificación**: Frontmatter permite programación agent para descubrir y usar templates automáticamente.

---

## 11. PREGUNTAS DE CALIBRACIÓN ESTRATÉGICA

### [Pregunta 1] Escalabilidad de Templates

**¿50+ templates es suficiente o necesitamos 100+ para covering?**

Implica:
- **50**: Covering básico, más simple mantenimiento
- **100+**: Covering exhaustivo, más templates que mantener
- **Trade-off**: Completitud vs mantenibilidad

### [Pregunta 2] MVPs Semanales vs Quincenales

**¿Es viable MVPs semanales o necesitamos quincenales?**

Implica:
- **Semanales**: Más rápido feedback, mayor presión
- **Quincenales**: Más tiempo por MVP, menos iteraciones
- **Trade-off**: Velocidad vs calidad

### [Pregunta 3] Multi-tenant desde Día 1

**¿Debemos implementar multi-tenant desde Week 1 o postergar a Week 7?**