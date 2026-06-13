---
Spec_ID: "SPEC_09"
Title: "Observability and SRE - Metrics, Tracing and Resilience"
Version: "0.1.0-MVP"
Maturity_Level: "Semilla"
Status: "Draft"
Target_Agent: "sdd-apply"
Context_Tags: ["#OpenTelemetry", "#SRE", "#CircuitBreaker", "#Resilience"]
Dependency_Hashes: ["SPEC_00", "SPEC_01"]
Last_Updated: "2026-06-13"
---

# SPEC_09_OBSERVABILITY_AND_SRE

> **Propósito**: Especificar contratos de telemetría OpenTelemetry, límites de resiliencia, circuit breaker y políticas de retry para yaml-agno.

---

## 1. OPENTELEMETRY STANDARD METRICS

### 1.1 Métricas Requeridas

| Métrica | Tipo | Unidad | Descripción |
|---------|------|--------|-------------|
| `agent_execution_duration_seconds` | Histogram | segundos | Duración de ejecución de agente |
| `agent_execution_total` | Counter | count | Total de ejecuciones de agente |
| `agent_execution_errors_total` | Counter | count | Total de errores de ejecución |
| `team_execution_duration_seconds` | Histogram | segundos | Duración de ejecución de team |
| `workflow_step_duration_seconds` | Histogram | segundos | Duración de step de workflow |
| `workflow_execution_total` | Counter | count | Total de ejecuciones de workflow |
| `workflow_execution_errors_total` | Counter | count | Total de errores de workflow |
| `di_cache_hit_total` | Counter | count | Total de cache hits DI |
| `di_cache_miss_total` | Counter | count | Total de cache misses DI |
| `session_message_total` | Counter | count | Total de mensajes en sesión |
| `context_compression_total` | Counter | count | Total de compresiones de contexto |
| `engram_save_total` | Counter | count | Total de saves en Engram |
| `engram_search_total` | Counter | count | Total de searches en Engram |

### 1.2 Labels (Attributes) Requeridas

Todas las métricas deben incluir estos labels:

| Label | Descripción | Ejemplo |
|-------|-------------|---------|
| `tenant_id` | ID de tenant | `uuid` |
| `agent_name` | Nombre del agente | `invoice_processor` |
| `team_name` | Nombre del team | `validation_team` |
| `workflow_name` | Nombre del workflow | `invoice_processing` |
| `model_provider` | Provider del modelo | `openai` |
| `model_name` | Nombre del modelo | `gpt-4o` |
| `status` | Estado de ejecución | `success|error` |
| `error_type` | Tipo de error | `timeout|validation` |

### 1.3 Buckets de Histogram

```python
# yaml-agno/src/telemetry/metrics.py

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader

# Buckets para duración (en segundos)
DURATION_BUCKETS = (
    0.005,  # 5ms
    0.01,   # 10ms
    0.025,  # 25ms
    0.05,   # 50ms
    0.1,    # 100ms
    0.25,   # 250ms
    0.5,    # 500ms
    1.0,    # 1s
    2.5,    # 2.5s
    5.0,    # 5s
    10.0,   # 10s
    30.0,   # 30s
    60.0,   # 60s
    float('inf'),
)

def setup_metrics():
    """Configura métricas OpenTelemetry"""
    reader = PeriodicExportingMetricReader(ConsoleMetricExporter(), export_interval_millis=10000)
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    return metrics.get_meter(__name__)
```

---

## 2. METADATA AND REQUIRED LABELS

### 2.1 Spans de Tracing

```python
# yaml-agno/src/telemetry/tracing.py

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.sdk.trace.export import BatchSpanProcessor

def setup_tracing():
    """Configura tracing OpenTelemetry"""
    provider = TracerProvider()
    processor = SimpleSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    return trace.get_tracer(__name__)

# Uso
tracer = setup_tracing()

with tracer.start_as_current_span("agent_execution") as span:
    span.set_attribute("agent_name", "invoice_processor")
    span.set_attribute("tenant_id", str(tenant_id))
    span.set_attribute("model_provider", "openai")
    
    try:
        result = await agent.run()
        span.set_attribute("status", "success")
    except Exception as e:
        span.set_attribute("status", "error")
        span.set_attribute("error_type", type(e).__name__)
        span.record_exception(e)
```

### 2.2 Context Propagation

```python
# Propagación de contexto entre servicios

from opentelemetry.propagators.builtin import (
    TraceContextPropagator,
    TextMapPropagator
)

# Injectar context en headers
propagator = TraceContextPropagator()
headers = {}
propagator.inject(carrier=headers, context=context)

# Extractar context de headers
context = propagator.extract(carrier=headers, context=context)
```

---

## 3. CIRCUIT BREAKER & RETRY POLICIES

### 3.1 Circuit Breaker Configuration

```python
# yaml-agno/src/resilience/circuit_breaker.py

from enum import Enum
from typing import Callable, Any
import time

class CircuitState(str, Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered

class CircuitBreaker:
    """
    Circuit Breaker para prevenir cascading failures.
    
    Estados:
    - CLOSED: Passthrough normal
    - OPEN: Rechazar requests inmediatamente
    - HALF_OPEN: Permitir un request para probar recuperación
    """
    
    def __init__(
        self,
        failure_threshold: float = 50.0,  # % de failures para abrir
        recovery_timeout: float = 30.0,    # Segundos antes de HALF_OPEN
        min_requests: int = 10,            # Mínimo de requests para evaluar
        half_open_max_calls: int = 3       # Máximo de calls en HALF_OPEN
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.min_requests = min_requests
        self.half_open_max_calls = half_open_max_calls
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.total_requests = 0
        self.last_failure_time = 0
        self.half_open_calls = 0
    
    def record_success(self) -> None:
        """Registra éxito"""
        self.total_requests += 1
        self.success_count += 1
        
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1
            if self.success_count >= self.half_open_max_calls:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.half_open_calls = 0
    
    def record_failure(self) -> None:
        """Registra fallo"""
        self.total_requests += 1
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
        elif self._should_trip():
            self.state = CircuitState.OPEN
    
    def _should_trip(self) -> bool:
        """Determina si debe abrir el circuito"""
        if self.total_requests < self.min_requests:
            return False
        
        failure_rate = (self.failure_count / self.total_requests) * 100
        return failure_rate >= self.failure_threshold
    
    def allow_request(self) -> bool:
        """Determina si permitir request"""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False
        
        if self.state == CircuitState.HALF_OPEN:
            return self.half_open_calls < self.half_open_max_calls
        
        return False
    
    async def execute(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """Ejecuta función con circuit breaker"""
        if not self.allow_request():
            raise CircuitBreakerOpenError("Circuit breaker is OPEN")
        
        try:
            result = await func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise
```

### 3.2 Constantes de Retry

```python
# yaml-agno/src/resilience/retry.py

import asyncio
import random
from typing import Callable, Any

class RetryConfig:
    """Configuración de retry con exponential backoff"""
    
    # Constantes matemáticas
    BASE_DELAY: float = 2.0  # Segundos
    MAX_DELAY: float = 60.0  # Segundos
    MAX_RETRIES: int = 3     # Máximo de intentos
    JITTER: bool = True      # ±50% jitter
    JITTER_FACTOR: float = 0.5  # 50%
    
    @classmethod
    def calculate_delay(cls, attempt: int) -> float:
        """Calcula delay con exponential backoff + jitter"""
        # Exponential: 2^attempt
        delay = cls.BASE_DELAY * (2 ** attempt)
        
        # Cap at MAX_DELAY
        delay = min(delay, cls.MAX_DELAY)
        
        # Add jitter
        if cls.JITTER:
            jitter = delay * cls.JITTER_FACTOR
            delay = delay - jitter + (2 * jitter * random.random())
        
        return max(0, delay)
    
    @classmethod
    async def execute_with_retry(
        cls,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any
    ) -> Any:
        """Ejecuta función con retry"""
        last_error = None
        
        for attempt in range(cls.MAX_RETRIES + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                
                if attempt < cls.MAX_RETRIES:
                    delay = cls.calculate_delay(attempt)
                    await asyncio.sleep(delay)
        
        raise last_error  # Exhausted retries
```

### 3.3 Retry con Circuit Breaker

```python
# yaml-agno/src/resilience/resilient_executor.py

class ResilientExecutor:
    """Ejecutor con circuit breaker + retry"""
    
    def __init__(self, circuit_breaker: CircuitBreaker):
        self.circuit_breaker = circuit_breaker
    
    async def execute(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """Ejecuta con circuit breaker + retry"""
        
        # Circuit breaker check
        if not self.circuit_breaker.allow_request():
            raise CircuitBreakerOpenError("Circuit breaker is OPEN")
        
        try:
            # Retry logic
            result = await RetryConfig.execute_with_retry(func, *args, **kwargs)
            self.circuit_breaker.record_success()
            return result
        
        except Exception as e:
            self.circuit_breaker.record_failure()
            raise
```

---

## 4. BEHAVIOR DELTA - BDD SCENARIOS

### 4.1 Escenarios de Aceptación

#### Scenario 1: Golden Path - Agent Execution Traced

```gherkin
GIVEN an agent is executed
AND telemetry is enabled
WHEN the execution completes
THEN a span "agent_execution" is created
AND the span includes agent_name attribute
AND the span includes tenant_id attribute
AND the span duration is recorded
```

#### Scenario 2: Golden Path - Metric Recorded

```gherkin
GIVEN an agent is executed successfully
AND metrics are enabled
WHEN the execution completes
THEN agent_execution_total counter is incremented
AND agent_execution_duration_seconds histogram records duration
AND the success label is set to "true"
```

#### Scenario 3: Error Case - Circuit Breaker Opens

```gherkin
GIVEN a circuit breaker with failure_threshold=50%
AND 10 requests have been made
AND 6 have failed (60% failure rate)
WHEN the 7th request fails
THEN the circuit breaker state changes to OPEN
AND subsequent requests are rejected
AND CircuitBreakerOpenError is raised
```

#### Scenario 4: Golden Path - Circuit Breaker Recovers

```gherkin
GIVEN a circuit breaker in OPEN state
AND the recovery_timeout (30s) has elapsed
WHEN a new request arrives
THEN the circuit breaker changes to HALF_OPEN
AND the request is allowed
AND if successful, the circuit breaker closes
```

#### Scenario 5: Golden Path - Retry with Backoff

```gherkin
GIVEN a function that fails twice then succeeds
AND retry policy is enabled
WHEN the function is executed
THEN the first attempt fails
AND a retry occurs after 2 seconds
AND the second attempt fails
AND a retry occurs after 4 seconds
AND the third attempt succeeds
AND the result is returned
```

---

## 5. TDD MICRO-TASK EXECUTION PROTOCOL

### 5.1 Cascading Task Checklist

#### TASK_001: Setup OpenTelemetry Metrics

- **File**: `yaml-agno/src/telemetry/metrics.py`
- **Test**: `tests/unit/telemetry/test_metrics.py`
- **RED**:
  ```python
  def test_metrics_initialized():
      meter = setup_metrics()
      assert meter is not None
  ```
- **GREEN**: Implement `setup_metrics()`
- **Commit**: `feat: add OpenTelemetry metrics setup`

#### TASK_002: Create Agent Execution Histogram

- **File**: `yaml-agno/src/telemetry/metrics.py`
- **Test**: `tests/unit/telemetry/test_metrics.py`
- **RED**:
  ```python
  def test_record_agent_duration():
      record_agent_duration(0.5, tenant_id="t1", agent_name="a1")
      # Verify histogram recorded
  ```
- **GREEN**: Implement histogram with buckets
- **Commit**: `feat: add agent execution histogram`

#### TASK_003: Create Agent Execution Counter

- **File**: `yaml-agno/src/telemetry/metrics.py`
- **Test**: `tests/unit/telemetry/test_metrics.py`
- **RED**:
  ```python
  def test_increment_agent_counter():
      increment_agent_execution(tenant_id="t1", agent_name="a1", status="success")
      # Verify counter incremented
  ```
- **GREEN**: Implement counter with labels
- **Commit**: `feat: add agent execution counter`

#### TASK_004: Setup OpenTelemetry Tracing

- **File**: `yaml-agno/src/telemetry/tracing.py`
- **Test**: `tests/unit/telemetry/test_tracing.py`
- **RED**:
  ```python
  def test_tracer_initialized():
      tracer = setup_tracing()
      assert tracer is not None
  ```
- **GREEN**: Implement `setup_tracing()`
- **Commit**: `feat: add OpenTelemetry tracing setup`

#### TASK_005: Create Agent Execution Span

- **File**: `yaml-agno/src/telemetry/tracing.py`
- **Test**: `tests/unit/telemetry/test_tracing.py`
- **RED**:
  ```python
  def test_agent_execution_span():
      with tracer.start_as_current_span("agent_execution") as span:
          span.set_attribute("agent_name", "test")
          # Verify span created
  ```
- **GREEN**: Implement span with attributes
- **Commit**: `feat: add agent execution span`

#### TASK_006: Implement Circuit Breaker

- **File**: `yaml-agno/src/resilience/circuit_breaker.py`
- **Test**: `tests/unit/resilience/test_circuit_breaker.py`
- **RED**:
  ```python
  def test_circuit_breaker_initially_closed():
      cb = CircuitBreaker()
      assert cb.state == CircuitState.CLOSED
  ```
- **GREEN**: Implement `CircuitBreaker` class
- **Commit**: `feat: add circuit breaker implementation`

#### TASK_007: Implement Circuit Breaker Trip Logic

- **File**: `yaml-agno/src/resilience/circuit_breaker.py`
- **Test**: `tests/unit/resilience/test_circuit_breaker.py`
- **RED**:
  ```python
  def test_circuit_breaker_trips_on_threshold():
      cb = CircuitBreaker(failure_threshold=50.0, min_requests=10)
      for i in range(6):
          cb.record_failure()
      assert cb.state == CircuitState.OPEN
  ```
- **GREEN**: Implement `_should_trip()` logic
- **Commit**: `feat: add circuit breaker trip logic`

#### TASK_008: Implement Retry with Exponential Backoff

- **File**: `yaml-agno/src/resilience/retry.py`
- **Test**: `tests/unit/resilience/test_retry.py`
- **RED**:
  ```python
  async def test_retry_with_backoff():
      attempts = [0]
      
      async def failing_func():
          attempts[0] += 1
          if attempts[0] < 3:
              raise TimeoutError()
          return "success"
      
      result = await RetryConfig.execute_with_retry(failing_func)
      assert result == "success"
      assert attempts[0] == 3
  ```
- **GREEN**: Implement `execute_with_retry()`
- **Commit**: `feat: add retry with exponential backoff`

#### TASK_009: Implement Retry Delay Calculation

- **File**: `yaml-agno/src/resilience/retry.py`
- **Test**: `tests/unit/resilience/test_retry.py`
- **RED**:
  ```python
  def test_delay_calculation():
      delay = RetryConfig.calculate_delay(attempt=1)
      assert 2 <= delay <= 4  # 2s ± 50% jitter
  ```
- **GREEN**: Implement `calculate_delay()` with jitter
- **Commit**: `feat: add delay calculation with jitter`

#### TASK_010: Implement Resilient Executor

- **File**: `yaml-agno/src/resilience/resilient_executor.py`
- **Test**: `tests/unit/resilience/test_resilient_executor.py`
- **RED**:
  ```python
  async def test_resilient_executor():
      cb = CircuitBreaker()
      executor = ResilientExecutor(cb)
      
      async def test_func():
          return "success"
      
      result = await executor.execute(test_func)
      assert result == "success"
  ```
- **GREEN**: Implement `ResilientExecutor.execute()`
- **Commit**: `feat: add resilient executor`

---

## 6. SUPUESTOS TÉCNICOS ADOPTADOS

### [Decisión 1] OpenTelemetry para Observabilidad

**Justificación**:
- Estándar vendor-neutral
- Soportado por todos los major clouds
- Integración con Agno framework

### [Decisión 2] Circuit Breaker Matemático

**Justificación**:
- Constantes explícitas (50%, 30s)
- Previsible y testeable
- Basado en patrones probados (Resilience4j)

### [Decisión 3] Jitter en Retry

**Justificación**:
- Previene thundering herd
- Distribuye retries en el tiempo
- Mejor que fixed delay

---

## 7. PREGUNTAS DE CALIBRACIÓN ESTRATÉGICA

### [Pregunta 1] Sampling Rate para Spans

**¿Qué sampling rate para traces (100%, 10%, 1%)?**

Implica:
- **100%**: Máximo detalle, alto costo
- **10%**: Balance costo/detalle
- **1%**: Mínimo costo, menos debugging
- **Trade-off**: Costo vs debuggability

### [Pregunta 2] Retención de Métricas

**¿Por cuánto tiempo retener métricas en Prometheus?**

Implica:
- **7 días**: Mínimo storage
- **30 días**: Buen balance
- **90 días**: Máximo para análisis histórico
- **Trade-off**: Storage vs capacidad de análisis

### [Pregunta 3] Alerting Thresholds

**¿Qué thresholds para alertas (eg: 5% error rate, 50% latency increase)?**

Implica:
- **Agresivo**: Más alertas, más fatigue
- **Conservador**: Menos alertas, riesgo de miss
- **Trade-off**: Sensibilidad vs noise

---

## 8. CALIBRACIÓN FINAL

### 8.1 Resumen de Especificación

Los 10 documentos SPEC completos cubren:

1. **SPEC_00**: Estrategia del sistema, visión, principios
2. **SPEC_01**: Runtime architecture, factories, session management
3. **SPEC_02**: Domain model DDD, entidades, value objects
4. **SPEC_03**: Persistencia PostgreSQL, schema DDL, transactions
5. **SPEC_04**: Memoria, Engram, compresión, PII sanitization
6. **SPEC_05**: Workflows, teams, interacción, error recovery
7. **SPEC_06**: API REST, AX schemas, health checks
8. **SPEC_07**: Dashboard frontend, React, Zustand
9. **SPEC_08**: TDD microtasks, checklist de implementación
10. **SPEC_09**: Observabilidad, métricas, circuit breaker

### 8.2 Próximos Pasos

1. **Revisión por usuario**: Validar SPECs completos
2. **Ajustes**: Modificar según feedback
3. **Ejecución**: Iniciar implementación vía `sdd-apply`
4. **Validación**: Usar `sdd-verify` para verificar implementación

---

*¿Deseas profundizar la especificación técnica al **Nivel 6** de algún componente específico o autorizar la ejecución de estas tareas por parte del equipo de agentes?*
