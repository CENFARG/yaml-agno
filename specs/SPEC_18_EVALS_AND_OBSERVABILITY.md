---
Spec_ID: "SPEC_18"
Title: "Evals and Observability Integrations - Agno Evals and OTel Provider Catalog"
Version: "0.2.0-iter1"
Maturity_Level: "Semilla"
Status: "Draft"
Target_Agent: "sdd-apply"
Context_Tags: ["#Evals", "#AccuracyEval", "#PerformanceEval", "#ReliabilityEval", "#AgentAsJudge", "#OpenTelemetry", "#Langfuse", "#Langsmith", "#Tracing", "#ObservabilityManager"]
Dependency_Hashes: ["SPEC_09", "SPEC_03", "SPEC_01"]
Last_Updated: "2026-06-17"
Revision_Note: "iter1: ObservabilityProviderRegistry pasa de eager import (16 adapters al construir) a lazy import por provider en resolve() via DependencyManager; traducido texto chino en Scenario 10."
---

# SPEC_18_EVALS_AND_OBSERVABILITY

> **Propósito**: Especificar el sistema de evaluaciones Agno (accuracy, agent-as-judge, performance, reliability), el catálogo de 16 providers de observabilidad OTel, y la persistencia de traces en DB, todo mapeado desde YAML y orquestado por el `ObservabilityManager` de Core Infra.

---

## 0. FRONTERA CON SPEC_09 (LECTURA OBLIGATORIA)

Existe una frontera deliberada entre SPEC_09 y SPEC_18. Ambos tocan observabilidad, pero en capas distintas.

| Dimensión | SPEC_09 (Observability & SRE) | SPEC_18 (este documento) |
|-----------|-------------------------------|--------------------------|
| **Alcance** | Telemetría genérica interna (OTel metrics/tracing SRE) | Catálogo de providers Agno + sistema de evals |
| **Responsable** | `ObservabilityManager` + `LoggerManager` (Ports Core Infra) | `ObservabilityProviderRegistry` + `EvalRunner` (este SPEC) |
| **Contracto** | Port (Protocol): `start_span`, `increment_counter` | Adapter por provider (Langfuse, Langsmith, ...) + modelos de Eval |
| **Qué captura** | RED metrics, spans SRE propios de yaml-agno | Traces de LLM/tool/agent que Agno exporta via OpenInference/OpenLIT |
| **Circuit Breaker / Retry** | Sí (definido aquí referencia) | Hereda de SPEC_09 (no redefine) |
| **Datasets / Scoring** | No | Sí (AccuracyEval, AgentAsJudge, PerformanceEval, ReliabilityEval) |
| **Tracing to DB** | No | Sí (`trace_db` dedicado) |

**Regla de oro**:
- Si la pregunta es "¿qué span/métrica SRE emito cuando un agente falla?" → SPEC_09.
- Si la pregunta es "¿cómo activo Langfuse o corro un AccuracyEval?" → SPEC_18.

SPEC_18 **consume** el `ObservabilityManager` de SPEC_09 (Port) y le inyecta adapters concretos de cada provider. No redefine el Port. No redefine Circuit Breaker ni Retry (ver SPEC_09 secciones 3.1 y 3.2).

**Referencia cruzada explícita**:
- Port `ObservabilityManager`: SPEC_09 §1.2.
- Métricas base (`agent_execution_*`): SPEC_09 §2.1.
- Circuit Breaker y `ResilientExecutor`: SPEC_09 §3.1, §3.3.
- Retención / sampling de spans: SPEC_09 §5 (preguntas de calibración).

---

## 1. EVALS - CATÁLOGO DE TIPOS DE EVALUACIÓN

### 1.1 Clasificación de Evals

Agno expone cuatro familias de evaluación. yaml-agno las mapea desde un bloque YAML `evals:`.

| Eval | Módulo Agno | Qué mide | Salida | Score |
|------|-------------|----------|--------|-------|
| **AccuracyEval** | `agno.eval.accuracy` | Coincidencia contra gold-standard (`expected_output`) vía LLM-as-judge | `AccuracyResult` con `avg_score` (0-10) | numérico |
| **AgentAsJudgeEval** | `agno.eval.agent_as_judge` | Criterios de calidad custom (tono, factualidad, usabilidad) | resultado con `scoring_strategy` numeric/binary | numérico o binario |
| **PerformanceEval** | `agno.eval.performance` | Latencia y huella de memoria | `PerformanceResult` (runtime, memory) | métrica |
| **ReliabilityEval** | `agno.eval.reliability` | Tool calls esperados, manejo de errores, rate limits | `ReliabilityResult` con `assert_passed()` | pass/fail |

### 1.2 AccuracyEval - LLM-as-Judge contra Gold Standard

Compara la respuesta real del agente contra `expected_output`. Un modelo evaluador (`model`) puntúa la coincidencia.

```python
# yaml-agno/src/evals/accuracy_adapter.py

from typing import Optional
from agno.eval.accuracy import AccuracyEval, AccuracyResult
from agno.run.agent import RunOutput

class AccuracyEvalAdapter:
    """
    Adapter de AccuracyEval.
    LLM-as-judge: un modelo puntúa cuán cerca está la respuesta del agente
    del expected_output, usando additional_guidelines opcional.
    """

    def __init__(
        self,
        name: str,
        evaluator_model: str,
        agent_ref: str,
        team_ref: Optional[str] = None,
        input: str = "",
        expected_output: str = "",
        additional_guidelines: Optional[str] = None,
        num_iterations: int = 1,
    ):
        self.name = name
        self.evaluator_model = evaluator_model
        self.agent_ref = agent_ref
        self.team_ref = team_ref
        self.input = input
        self.expected_output = expected_output
        self.additional_guidelines = additional_guidelines
        self.num_iterations = num_iterations

    def build(self, resolved_agent, resolved_model) -> AccuracyEval:
        return AccuracyEval(
            name=self.name,
            model=resolved_model,
            agent=resolved_agent,
            input=self.input,
            expected_output=self.expected_output,
            additional_guidelines=self.additional_guidelines,
            num_iterations=self.num_iterations,
        )

    def run_with_output(self, output: str, eval_obj: AccuracyEval) -> Optional[AccuracyResult]:
        """Permite evaluar contra una salida ya generada (sin re-ejecutar el agente)."""
        return eval_obj.run_with_output(output=output, print_results=False)
```

**Patrones soportados** (derivados de docs Agno):
- Eval con tools (`agent` con `CalculatorTools`).
- Eval contra output dado (`run_with_output`).
- Eval async (`arun`).
- Eval con Team (`team=` en lugar de `agent=`).
- Custom evaluator agent (`evaluator_agent=` con `output_schema=AccuracyAgentResponse`).

### 1.3 AgentAsJudgeEval - Criterios de Calidad Custom

Permite definir criterios arbitrarios ("tono profesional", "precisión factual") y un modelo juzga.

```python
# yaml-agno/src/evals/agent_as_judge_adapter.py

from typing import Optional, Union, List, Callable
from agno.eval.agent_as_judge import AgentAsJudgeEval

class AgentAsJudgeEvalAdapter:
    """
    Adapter de AgentAsJudgeEval.

    scoring_strategy: "numeric" (1-10) o "binary" (pass/fail).
    threshold: mínimo para pasar (solo numeric).
    on_fail: callback cuando el eval falla (para alertas/HITL).
    cases: lista de pares input/output para evaluación batch.
    """

    def __init__(
        self,
        name: str,
        criteria: str,
        scoring_strategy: str = "binary",   # "numeric" | "binary"
        threshold: int = 7,
        evaluator_model: Optional[str] = None,
        evaluator_agent_ref: Optional[str] = None,
        additional_guidelines: Optional[Union[str, List[str]]] = None,
        on_fail: Optional[Callable] = None,
        run_in_background: bool = False,
        debug_mode: bool = False,
    ):
        self.criteria = criteria
        self.scoring_strategy = scoring_strategy
        self.threshold = threshold
        self.evaluator_model = evaluator_model
        self.evaluator_agent_ref = evaluator_agent_ref
        self.additional_guidelines = additional_guidelines
        self.on_fail = on_fail
        self.run_in_background = run_in_background
        self.debug_mode = debug_mode

    def build(self, resolved_model, resolved_evaluator_agent) -> AgentAsJudgeEval:
        kwargs = dict(
            name=self.name,
            criteria=self.criteria,
            scoring_strategy=self.scoring_strategy,
            threshold=self.threshold,
            additional_guidelines=self.additional_guidelines,
            on_fail=self.on_fail,
            run_in_background=self.run_in_background,
            debug_mode=self.debug_mode,
        )
        if resolved_evaluator_agent is not None:
            kwargs["evaluator_agent"] = resolved_evaluator_agent
        elif resolved_model is not None:
            kwargs["model"] = resolved_model
        return AgentAsJudgeEval(**kwargs)
```

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `criteria` | `str` | `""` | Criterio de calidad (requerido) |
| `scoring_strategy` | `Literal["numeric","binary"]` | `"binary"` | Modo de puntaje |
| `threshold` | `int` | `7` | Mínimo para pasar (solo numeric) |
| `on_fail` | `Optional[Callable]` | `None` | Callback en fallo |
| `additional_guidelines` | `Optional[Union[str, List[str]]]` | `None` | Guías extra |
| `evaluator_agent` | `Optional[Agent]` | `None` | Agente evaluador custom |
| `run_in_background` | `bool` | `False` | Non-blocking |

**Nota**: `run(input=..., output=...)` para evaluación simple o `run(cases=[...])` para batch. Mutuamente excluyentes.

### 1.4 PerformanceEval - Latencia y Memoria

```python
# yaml-agno/src/evals/performance_adapter.py

from agno.eval.performance import PerformanceEval

class PerformanceEvalAdapter:
    """
    Mide runtime y memory footprint.
    num_iterations: repeticiones para promediar.
    warmup_runs: descartar N primeras.
    measure_runtime: si False, solo mide memoria (útil para memory_growth_tracking).
    memory_growth_tracking: detectar leaks en runs repetidos (Teams con memoria).
    """

    def __init__(
        self,
        name: str,
        func_ref: str,          # callable sync o async (agent factory / run fn)
        num_iterations: int = 1,
        warmup_runs: int = 0,
        measure_runtime: bool = True,
        memory_growth_tracking: bool = False,
        debug_mode: bool = False,
        is_async: bool = False,
    ):
        self.name = name
        self.func_ref = func_ref
        self.num_iterations = num_iterations
        self.warmup_runs = warmup_runs
        self.measure_runtime = measure_runtime
        self.memory_growth_tracking = memory_growth_tracking
        self.debug_mode = debug_mode
        self.is_async = is_async

    def build(self, resolved_func) -> PerformanceEval:
        return PerformanceEval(
            name=self.name,
            func=resolved_func,
            num_iterations=self.num_iterations,
            warmup_runs=self.warmup_runs,
            measure_runtime=self.measure_runtime,
            memory_growth_tracking=self.memory_growth_tracking,
            debug_mode=self.debug_mode,
        )
```

**Requiere**: `pip install memory_profiler`. El `func_ref` resuelve a una callable registrada (factory de agente o función `run_agent`).

### 1.5 ReliabilityEval - Tool Calls y Errores

```python
# yaml-agno/src/evals/reliability_adapter.py

from typing import Optional, List
from agno.eval.reliability import ReliabilityEval, ReliabilityResult
from agno.run.agent import RunOutput
from agno.run.team import TeamRunOutput

class ReliabilityEvalAdapter:
    """
    Verifica que el agente/team haga los tool calls esperados.
    Acepta agent_response (RunOutput) o team_response (TeamRunOutput).
    expected_tool_calls: lista de nombres de tools que debieron invocarse.
    """

    def __init__(
        self,
        name: str,
        expected_tool_calls: List[str],
    ):
        self.name = name
        self.expected_tool_calls = expected_tool_calls

    def build(self) -> ReliabilityEval:
        return ReliabilityEval(
            name=self.name,
            expected_tool_calls=self.expected_tool_calls,
        )

    def evaluate(self, eval_obj: ReliabilityEval, response: RunOutput | TeamRunOutput) -> Optional[ReliabilityResult]:
        # Distinguir agent vs team por tipo
        if isinstance(response, TeamRunOutput):
            result = eval_obj.run(team_response=response, print_results=False)
        else:
            result = eval_obj.run(agent_response=response, print_results=False)
        return result
```

**Para Teams**: `expected_tool_calls` puede incluir `delegate_task_to_member` (tool de delegación) además de tools de miembros.

### 1.6 Eval Datasets

Los datasets son conjuntos de casos (input/expected_output) cargados desde archivos.

```yaml
# yaml-agno/datasets/calculator_eval_dataset.yaml
name: calculator_eval_dataset
version: "1.0.0"
format: accuracy            # accuracy | agent_as_judge | reliability
cases:
  - id: case_001
    input: "What is 10*5 then to the power of 2? do it step by step"
    expected_output: "2500"
    additional_guidelines: "Output should include steps and final answer."
  - id: case_002
    input: "What is 10!?"
    expected_output: "3628800"
  - id: case_003
    input: "9.11 and 9.9 -- which is bigger?"
    expected_output: "9.9"
    additional_guidelines: "OK to include additional relevant text."
```

```python
# yaml-agno/src/evals/dataset_loader.py

from pathlib import Path
from typing import List
import yaml
from pydantic import BaseModel, Field

class EvalCase(BaseModel):
    id: str
    input: str
    expected_output: str | None = None
    additional_guidelines: str | None = None
    metadata: dict = Field(default_factory=dict)

class EvalDataset(BaseModel):
    name: str
    version: str = "1.0.0"
    format: str                # accuracy | agent_as_judge | reliability
    cases: List[EvalCase]

class EvalDatasetLoader:
    """Carga datasets YAML desde el directorio datasets/."""

    def __init__(self, datasets_dir: Path):
        self.datasets_dir = datasets_dir

    def load(self, dataset_name: str) -> EvalDataset:
        path = self.datasets_dir / f"{dataset_name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Eval dataset not found: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return EvalDataset.model_validate(raw)

    def list_datasets(self) -> List[str]:
        return [
            p.stem for p in self.datasets_dir.glob("*.yaml")
        ]
```

---

## 2. EVAL RUNS Y SCORING

### 2.1 EvalRun - Ejecución Orquestada

Un `EvalRun` itera sobre un dataset (o caso simple), ejecuta el eval, agrega scores y persiste el resultado.

```python
# yaml-agno/src/evals/runner.py

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

@dataclass
class EvalRunResult:
    run_id: str
    eval_name: str
    eval_type: str                 # accuracy | agent_as_judge | performance | reliability
    started_at: datetime
    finished_at: Optional[datetime] = None
    case_results: list[dict] = field(default_factory=list)
    aggregate: dict = field(default_factory=dict)
    status: str = "running"        # running | passed | failed | error
    threshold_breached: bool = False

class EvalRunner:
    """
    Orquesta un eval sobre uno o varios casos.
    Usa asyncio.TaskGroup para paralelizar casos (NO asyncio.gather).
    Persiste resultados en db (trace_db o db principal).
    """

    def __init__(self, db, observability_manager):
        self.db = db
        self.obs = observability_manager

    async def arun_accuracy(
        self,
        eval_adapter,            # AccuracyEvalAdapter
        dataset: Optional[EvalDataset],
        resolved_agent,
        resolved_model,
        threshold: float = 8.0,
    ) -> EvalRunResult:
        run = EvalRunResult(
            run_id=str(uuid4()),
            eval_name=eval_adapter.name,
            eval_type="accuracy",
            started_at=datetime.now(timezone.utc),
        )

        try:
            async with self.obs.start_span("eval_run.accuracy") as span:
                span.set_attribute("eval.run_id", run.run_id)
                span.set_attribute("eval.threshold", threshold)

                cases = dataset.cases if dataset else [
                    EvalCase(id="single", input=eval_adapter.input,
                             expected_output=eval_adapter.expected_output,
                             additional_guidelines=eval_adapter.additional_guidelines)
                ]

                # Construir el eval base (compartido)
                base_eval = eval_adapter.build(resolved_agent, resolved_model)

                # Ejecutar casos en paralelo con TaskGroup
                results: list[dict] = []

                async def run_case(case: EvalCase):
                    case_eval = eval_adapter.build(resolved_agent, resolved_model)
                    case_eval.input = case.input
                    case_eval.expected_output = case.expected_output
                    if case.additional_guidelines:
                        case_eval.additional_guidelines = case.additional_guidelines
                    res = await case_eval.arun(print_results=False)
                    return {
                        "case_id": case.id,
                        "avg_score": getattr(res, "avg_score", None) if res else None,
                        "passed": (res and res.avg_score is not None and res.avg_score >= threshold),
                    }

                async with asyncio.TaskGroup() as tg:
                    tasks = [tg.create_task(run_case(c)) for c in cases]

                for t in tasks:
                    results.append(t.result())

                run.case_results = results
                scores = [r["avg_score"] for r in results if r["avg_score"] is not None]
                run.aggregate = {
                    "count": len(results),
                    "mean_score": sum(scores) / len(scores) if scores else 0.0,
                    "min_score": min(scores) if scores else 0.0,
                    "max_score": max(scores) if scores else 0.0,
                    "pass_rate": sum(1 for r in results if r["passed"]) / len(results) if results else 0.0,
                }
                run.threshold_breached = run.aggregate["mean_score"] < threshold
                run.status = "failed" if run.threshold_breached else "passed"
                run.finished_at = datetime.now(timezone.utc)

                # Métrica de resultado de eval
                self.obs.increment_counter(
                    "eval_run_total",
                    labels={
                        "eval_type": "accuracy",
                        "eval_name": run.eval_name,
                        "status": run.status,
                    },
                )

            await self._persist(run)
            return run

        except Exception as e:
            run.status = "error"
            run.finished_at = datetime.now(timezone.utc)
            self.obs.increment_counter(
                "eval_run_errors_total",
                labels={"eval_type": "accuracy", "error_type": type(e).__name__},
            )
            raise
```

### 2.2 Reglas de Scoring por Tipo

| Eval | Score | Pass cond | Threshold default |
|------|-------|-----------|-------------------|
| Accuracy | `avg_score` 0-10 | `avg_score >= threshold` | 8.0 |
| AgentAsJudge (numeric) | 1-10 | `score >= threshold` | 7 |
| AgentAsJudge (binary) | pass/fail | `result == pass` | n/a |
| Performance | runtime_ms, mem_mb | `runtime_ms <= p95_target` | configurable |
| Reliability | bool | `assert_passed()` no lanza | todos los tool calls presentes |

### 2.3 Persistencia de Eval Runs

Los eval runs se persisten en `trace_db` (ver §6) o en el `db` principal de Agno, siguiendo el patrón de los docs (`db=db` en `AccuracyEval`). yaml-agno expone endpoints REST `GET/POST/PATCH/DELETE /eval-runs` (definido en SPEC_19).

```python
# Tabla conceptual (mapeo Agno schema)
# eval_runs:
#   id, eval_type, eval_name, agent_id, team_id, status,
#   aggregate_json, case_results_json, created_at, user_id
```

---

## 3. CATÁLOGO DE 16 OBSERVABILITY PROVIDERS

Todos los providers se integran vía OpenTelemetry (mayoría vía OpenInference `openinference-instrumentation-agno`) o via SDK propio. yaml-agno los abstrae detrás de un adapter uniforme.

### 3.1 Tabla Maestra de Providers

| # | Provider | Captura | Env Vars Clave | Instalación | Estrategia |
|---|----------|---------|----------------|-------------|------------|
| 1 | **AgentOps** | agent runs, team coordination, tool usage, workflows | `AGENTOPS_API_KEY` | `agentops` | `agentops.init()` |
| 2 | **Arize Phoenix** | traces, LLM spans, performance | `ARIZE_PHOENIX_API_KEY`, `PHOENIX_COLLECTOR_ENDPOINT` | `arize-phoenix openinference-instrumentation-agno` | `phoenix.otel.register()` |
| 3 | **Atla** | monitoring, automated eval, analytics | `ATLA_API_KEY` | `atla-insights` | `configure()` + `instrument_agno()` |
| 4 | **LangDB** | AI gateway, agent runs, tool calls, perf metrics | `LANGDB_API_KEY`, `LANGDB_PROJECT_ID` | `pylangdb[agno]` | `pylangdb.agno.init()` |
| 5 | **Langfuse** | traces, model calls, cost | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | `langfuse openinference-instrumentation-agno` | OTLP + OpenInference/OpenLIT |
| 6 | **Langsmith** | traces, model calls | `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LANGSMITH_ENDPOINT`, `LANGSMITH_TRACING` | `openinference-instrumentation-agno` | OTLP + headers `x-api-key` |
| 7 | **Langtrace** | traces, model calls | `LANGTRACE_API_KEY` | `langtrace-python-sdk` | `langtrace.init()` |
| 8 | **Langwatch** | traces, monitoring | `LANGWATCH_API_KEY` | `langwatch openinference-instrumentation-agno` | `langwatch.setup(instrumentors=[...])` |
| 9 | **Latitude** | traces, evals, token/cost/latency | `LATITUDE_API_KEY`, `LATITUDE_PROJECT` | `openinference-instrumentation-agno` | OTLP + OpenInference |
| 10 | **Logfire** | traces (Pydantic) | `LOGFIRE_WRITE_TOKEN` | `openinference-instrumentation-agno` | OTLP + Authorization header |
| 11 | **Maxim** | monitoring, eval, traces | `MAXIM_API_KEY`, `MAXIM_LOG_REPO_ID` | `maxim-py` | `maxim.logger.agno.instrument_agno()` |
| 12 | **MLflow** | GenAI traces | `MLFLOW_TRACKING_URI`, `MLFLOW_EXPERIMENT_NAME` | `mlflow openinference-instrumentation-agno` | `mlflow.agno.autolog()` |
| 13 | **OpenLIT** | LLM calls, tools, costs, perf, errors | `OTEL_EXPORTER_OTLP_ENDPOINT` | `openlit` | `openlit.init()` |
| 14 | **Traceloop** | agent exec, workflows, tool calls, tokens | `TRACELOOP_API_KEY` | `traceloop-sdk` | `Traceloop.init()` (OpenLLMetry) |
| 15 | **Weave (WandB)** | model calls, visualizations | `WANDB_API_KEY` | `weave` | `weave.init()` + `@weave.op()` |
| 16 | *(OpenTelemetry puro)* | generic OTel backend (Jaeger, Tempo, etc.) | `OTEL_EXPORTER_OTLP_ENDPOINT` | `opentelemetry-sdk opentelemetry-exporter-otlp` | `OTLPSpanExporter` directo |

### 3.2 Detalle por Provider - Config YAML

yaml-agno declara providers en `observability.providers`. Cada provider tiene una clave unificada que el `ObservabilityProviderRegistry` resuelve a un adapter.

#### 3.2.1 Langfuse

```yaml
observability:
  tracing: true
  trace_db:
    type: postgres
    db_url: ${TRACE_DB_URL}
  providers:
    - provider: langfuse
      enabled: true
      region: us                  # us | eu | self_hosted
      self_hosted_endpoint: null  # si region=self_hosted
      env:
        LANGFUSE_PUBLIC_KEY: ${LANGFUSE_PUBLIC_KEY}
        LANGFUSE_SECRET_KEY: ${LANGFUSE_SECRET_KEY}
```

```python
# yaml-agno/src/observability/providers/langfuse_adapter.py

import base64, os
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

LANGFUSE_ENDPOINTS = {
    "us": "https://us.cloud.langfuse.com/api/public/otel",
    "eu": "https://eu.cloud.langfuse.com/api/public/otel",
    "self_hosted": "http://localhost:3000/api/public/otel",
}

class LangfuseAdapter:
    """Configura OTLP export hacia Langfuse con auth Basic (public:secret en base64)."""

    def __init__(self, region: str = "us", self_hosted_endpoint: str | None = None):
        self.region = region
        self.self_hosted_endpoint = self_hosted_endpoint

    def configure(self, tracer_provider: TracerProvider) -> None:
        endpoint = (self.self_hosted_endpoint if self.region == "self_hosted"
                    else LANGFUSE_ENDPOINTS[self.region])
        auth = base64.b64encode(
            f"{os.environ['LANGFUSE_PUBLIC_KEY']}:{os.environ['LANGFUSE_SECRET_KEY']}".encode()
        ).decode()
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = endpoint
        os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Basic {auth}"
        tracer_provider.add_span_processor(
            SimpleSpanProcessor(OTLPSpanExporter())
        )

    @property
    def requires_openinference(self) -> bool:
        return True
```

#### 3.2.2 Langsmith

```yaml
observability:
  providers:
    - provider: langsmith
      enabled: true
      region: us                  # us | eu
      env:
        LANGSMITH_API_KEY: ${LANGSMITH_API_KEY}
        LANGSMITH_PROJECT: ${LANGSMITH_PROJECT}
```

```python
# yaml-agno/src/observability/providers/langsmith_adapter.py

import os
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

LANGSMITH_ENDPOINTS = {
    "us": "https://api.smith.langchain.com/otel/v1/traces",
    "eu": "https://eu.api.smith.langchain.com/otel/v1/traces",
}

class LangsmithAdapter:
    """Export OTLP con headers x-api-key y Langsmith-Project."""

    def __init__(self, region: str = "us"):
        self.region = region

    def configure(self, tracer_provider: TracerProvider) -> None:
        endpoint = LANGSMITH_ENDPOINTS[self.region]
        headers = {
            "x-api-key": os.environ["LANGSMITH_API_KEY"],
            "Langsmith-Project": os.environ["LANGSMITH_PROJECT"],
        }
        tracer_provider.add_span_processor(
            SimpleSpanProcessor(OTLPSpanExporter(endpoint=endpoint, headers=headers))
        )

    @property
    def requires_openinference(self) -> bool:
        return True
```

#### 3.2.3 Logfire

```yaml
observability:
  providers:
    - provider: logfire
      enabled: true
      region: eu                  # us | eu
      env:
        LOGFIRE_WRITE_TOKEN: ${LOGFIRE_WRITE_TOKEN}
```

```python
# yaml-agno/src/observability/providers/logfire_adapter.py

LOGFIRE_ENDPOINTS = {
    "us": "https://logfire-us.pydantic.dev",
    "eu": "https://logfire-eu.pydantic.dev",
}

class LogfireAdapter:
    def __init__(self, region: str = "eu"):
        self.region = region

    def configure(self, tracer_provider):
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = LOGFIRE_ENDPOINTS[self.region]
        os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = (
            f"Authorization={os.environ['LOGFIRE_WRITE_TOKEN']}"
        )
        tracer_provider.add_span_processor(
            SimpleSpanProcessor(OTLPSpanExporter())
        )
```

#### 3.2.4 Arize Phoenix

```yaml
observability:
  providers:
    - provider: arize
      enabled: true
      mode: cloud                  # cloud | local
      project_name: agno-stock-agent
      env:
        ARIZE_PHOENIX_API_KEY: ${ARIZE_PHOENIX_API_KEY}
```

```python
# yaml-agno/src/observability/providers/arize_adapter.py

import os

class ArizeAdapter:
    """Cloud: app.phoenix.arize.com. Local: phoenix serve -> localhost:6006."""

    def __init__(self, mode: str = "cloud", project_name: str = "default"):
        self.mode = mode
        self.project_name = project_name

    def configure(self, tracer_provider):
        from phoenix.otel import register
        if self.mode == "cloud":
            os.environ["PHOENIX_CLIENT_HEADERS"] = (
                f"api_key={os.environ['ARIZE_PHOENIX_API_KEY']}"
            )
            os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = "https://app.phoenix.arize.com"
        else:
            os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = "http://localhost:6006"
        register(project_name=self.project_name, auto_instrument=True)

    @property
    def requires_openinference(self) -> bool:
        return True
```

#### 3.2.5 AgentOps

```yaml
observability:
  providers:
    - provider: agentops
      enabled: true
      env:
        AGENTOPS_API_KEY: ${AGENTOPS_API_KEY}
```

```python
# yaml-agno/src/observability/providers/agentops_adapter.py

class AgentOpsAdapter:
    """SDK propio. agentops.init() instrumenta todo automaticamente."""

    def configure(self, tracer_provider):
        import agentops
        agentops.init()

    @property
    def requires_openinference(self) -> bool:
        return False
```

#### 3.2.6 Atla

```yaml
observability:
  providers:
    - provider: atla
      enabled: true
      instrument_target: openai   # modelo a instrumentar
      env:
        ATLA_API_KEY: ${ATLA_API_KEY}
```

```python
# yaml-agno/src/observability/providers/atla_adapter.py

import os

class AtlaAdapter:
    def __init__(self, instrument_target: str = "openai"):
        self.instrument_target = instrument_target

    def configure(self, tracer_provider):
        from atla_insights import configure, instrument_agno
        configure(token=os.environ["ATLA_API_KEY"])
        # instrument_agno se invoca como context manager en runtime
        self._instrument = instrument_agno
```

#### 3.2.7 LangDB

```yaml
observability:
  providers:
    - provider: langdb
      enabled: true
      env:
        LANGDB_API_KEY: ${LANGDB_API_KEY}
        LANGDB_PROJECT_ID: ${LANGDB_PROJECT_ID}
```

```python
# yaml-agno/src/observability/providers/langdb_adapter.py

class LangDBAdapter:
    def configure(self, tracer_provider):
        from pylangdb.agno import init
        init()   # debe llamarse antes de crear agentes
```

#### 3.2.8 Langtrace

```yaml
observability:
  providers:
    - provider: langtrace
      enabled: true
      env:
        LANGTRACE_API_KEY: ${LANGTRACE_API_KEY}
```

```python
# yaml-agno/src/observability/providers/langtrace_adapter.py

class LangtraceAdapter:
    def configure(self, tracer_provider):
        from langtrace_python_sdk import langtrace
        langtrace.init()
```

#### 3.2.9 Langwatch

```yaml
observability:
  providers:
    - provider: langwatch
      enabled: true
      env:
        LANGWATCH_API_KEY: ${LANGWATCH_API_KEY}
```

```python
# yaml-agno/src/observability/providers/langwatch_adapter.py

class LangwatchAdapter:
    def configure(self, tracer_provider):
        import langwatch
        from openinference.instrumentation.agno import AgnoInstrumentor
        langwatch.setup(instrumentors=[AgnoInstrumentor()])
```

#### 3.2.10 Latitude

```yaml
observability:
  providers:
    - provider: latitude
      enabled: true
      env:
        LATITUDE_API_KEY: ${LATITUDE_API_KEY}
        LATITUDE_PROJECT: ${LATITUDE_PROJECT}
```

```python
# yaml-agno/src/observability/providers/latitude_adapter.py

import os
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

class LatitudeAdapter:
    def configure(self, tracer_provider: TracerProvider):
        # endpoint OTLP de ingestion de Latitude
        os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = (
            f"Authorization=Bearer {os.environ['LATITUDE_API_KEY']}"
        )
        tracer_provider.add_span_processor(
            SimpleSpanProcessor(OTLPSpanExporter())
        )

    @property
    def requires_openinference(self) -> bool:
        return True
```

#### 3.2.11 Maxim

```yaml
observability:
  providers:
    - provider: maxim
      enabled: true
      env:
        MAXIM_API_KEY: ${MAXIM_API_KEY}
        MAXIM_LOG_REPO_ID: ${MAXIM_LOG_REPO_ID}
```

```python
# yaml-agno/src/observability/providers/maxim_adapter.py

class MaximAdapter:
    def configure(self, tracer_provider):
        from maxim import Maxim
        from maxim.logger.agno import instrument_agno
        maxim = Maxim().init()
        instrument_agno(maxim)
```

#### 3.2.12 MLflow

```yaml
observability:
  providers:
    - provider: mlflow
      enabled: true
      env:
        MLFLOW_TRACKING_URI: ${MLFLOW_TRACKING_URI}
        MLFLOW_EXPERIMENT_NAME: ${MLFLOW_EXPERIMENT_NAME}
```

```python
# yaml-agno/src/observability/providers/mlflow_adapter.py

import os, mlflow

class MLflowAdapter:
    def configure(self, tracer_provider):
        mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
        mlflow.set_experiment(os.environ["MLFLOW_EXPERIMENT_NAME"])
        mlflow.agno.autolog()
```

#### 3.2.13 OpenLIT

```yaml
observability:
  providers:
    - provider: openlit
      enabled: true
      otlp_endpoint: http://127.0.0.1:4318
```

```python
# yaml-agno/src/observability/providers/openlit_adapter.py

class OpenLITAdapter:
    def __init__(self, otlp_endpoint: str = "http://127.0.0.1:4318"):
        self.otlp_endpoint = otlp_endpoint

    def configure(self, tracer_provider):
        import openlit
        openlit.init(tracer=tracer_provider.get_tracer(__name__), disable_batch=True)
```

#### 3.2.14 Traceloop

```yaml
observability:
  providers:
    - provider: traceloop
      enabled: true
      app_name: agno_agent
      env:
        TRACELOOP_API_KEY: ${TRACELOOP_API_KEY}
```

```python
# yaml-agno/src/observability/providers/traceloop_adapter.py

class TraceloopAdapter:
    def __init__(self, app_name: str = "agno_agent"):
        self.app_name = app_name

    def configure(self, tracer_provider):
        from traceloop.sdk import Traceloop
        Traceloop.init(app_name=self.app_name)
```

#### 3.2.15 Weave (WandB)

```yaml
observability:
  providers:
    - provider: weave
      enabled: true
      project: agno
      env:
        WANDB_API_KEY: ${WANDB_API_KEY}
```

```python
# yaml-agno/src/observability/providers/weave_adapter.py

class WeaveAdapter:
    def __init__(self, project: str = "agno"):
        self.project = project

    def configure(self, tracer_provider):
        import weave
        weave.init(self.project)
        # Las funciones target se decoran con @weave.op() en runtime.
```

#### 3.2.16 OpenTelemetry puro (fallback genérico)

```yaml
observability:
  providers:
    - provider: opentelemetry
      enabled: true
      otlp_endpoint: ${OTEL_EXPORTER_OTLP_ENDPOINT}   # Jaeger, Tempo, etc.
      headers: {}
```

```python
# yaml-agno/src/observability/providers/otel_adapter.py

class OtelAdapter:
    def __init__(self, otlp_endpoint: str, headers: dict | None = None):
        self.otlp_endpoint = otlp_endpoint
        self.headers = headers or {}

    def configure(self, tracer_provider):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        exporter = OTLPSpanExporter(endpoint=self.otlp_endpoint, headers=self.headers)
        tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
```

---

## 4. OBSERVABILITY PROVIDER REGISTRY

### 4.1 Registry - Resolución Declarativa

El registry mapea el string `provider:` del YAML a una clase adapter.

```python
# yaml-agno/src/observability/provider_registry.py

from typing import Protocol, Type
from pydantic import BaseModel, Field
from opentelemetry.sdk.trace import TracerProvider

class ObservabilityProvider(Protocol):
    """Contrato uniforme de todo adapter de provider."""
    def configure(self, tracer_provider: TracerProvider) -> None: ...
    @property
    def requires_openinference(self) -> bool: ...

class ProviderConfig(BaseModel):
    provider: str                 # langfuse | langsmith | ...
    enabled: bool = True
    region: str | None = None
    mode: str | None = None
    project_name: str | None = None
    project: str | None = None
    otlp_endpoint: str | None = None
    self_hosted_endpoint: str | None = None
    app_name: str | None = None
    instrument_target: str | None = None
    headers: dict = Field(default_factory=dict)
    env: dict = Field(default_factory=dict)

class ObservabilityProviderRegistry:
    """
    Registro declarativo de providers.
    Resuelve el string del YAML a un adapter concreto.
    Aplica variables de entorno declaradas (sin hardcodear secrets).
    """

    def __init__(self, dependency_manager: "DependencyManager"):
        # @ai-directive LAZY LOADING: NO se importan los adapters al construir el registry
        # (eso sería eager import de 16 providers de una vez).
        # En su lugar se registra un mapa provider -> ruta de import, y la import
        # real del adapter se difiere al primer resolve() de cada provider,
        # via el DependencyManager del Core (carga perezosa por provider).
        # Solo el provider efectivamente configurado en el YAML se carga en runtime.
        self._dependency_manager = dependency_manager   # Core Infra (SPEC_00)
        self._adapters: dict[str, Type[ObservabilityProvider]] = {}
        self._adapter_paths: dict[str, tuple[str, str]] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Registra rutas de import (sin importar los módulos todavía)."""
        self._adapter_paths = {
            "langfuse":        (".providers.langfuse_adapter",   "LangfuseAdapter"),
            "langsmith":       (".providers.langsmith_adapter",  "LangsmithAdapter"),
            "logfire":         (".providers.logfire_adapter",    "LogfireAdapter"),
            "arize":           (".providers.arize_adapter",      "ArizeAdapter"),
            "agentops":        (".providers.agentops_adapter",   "AgentOpsAdapter"),
            "atla":            (".providers.atla_adapter",       "AtlaAdapter"),
            "langdb":          (".providers.langdb_adapter",     "LangDBAdapter"),
            "langtrace":       (".providers.langtrace_adapter",  "LangtraceAdapter"),
            "langwatch":       (".providers.langwatch_adapter",  "LangwatchAdapter"),
            "latitude":        (".providers.latitude_adapter",    "LatitudeAdapter"),
            "maxim":           (".providers.maxim_adapter",       "MaximAdapter"),
            "mlflow":          (".providers.mlflow_adapter",       "MLflowAdapter"),
            "openlit":         (".providers.openlit_adapter",      "OpenLITAdapter"),
            "traceloop":       (".providers.traceloop_adapter",    "TraceloopAdapter"),
            "weave":           (".providers.weave_adapter",        "WeaveAdapter"),
            "opentelemetry":   (".providers.otel_adapter",         "OtelAdapter"),
        }

    def _load_adapter(self, provider: str) -> Type[ObservabilityProvider]:
        """Lazy import: solo carga el módulo del provider solicitado (via DependencyManager)."""
        if provider in self._adapters:
            return self._adapters[provider]
        if provider not in self._adapter_paths:
            raise ValueError(f"Unknown observability provider: {provider}")
        module_path, class_name = self._adapter_paths[provider]
        # DependencyManager (Core) resuelve el import perezoso y cachea la clase.
        cls = self._dependency_manager.import_class(module_path, class_name)
        self._adapters[provider] = cls  # cache para llamadas subsiguientes
        return cls

    def resolve(self, config: ProviderConfig) -> ObservabilityProvider:
        # Lazy import del adapter SOLO para el provider efectivamente configurado.
        cls = self._load_adapter(config.provider)
        # aplicar env declarado
        import os
        for k, v in config.env.items():
            os.environ.setdefault(k, str(v))
        return self._instantiate(cls, config)

    def _instantiate(self, cls, config: ProviderConfig) -> ObservabilityProvider:
        kwargs = {}
        for f in ("region", "mode", "project_name", "project",
                  "otlp_endpoint", "self_hosted_endpoint",
                  "app_name", "instrument_target", "headers"):
            v = getattr(config, f, None)
            if v is not None:
                kwargs[f] = v
        return cls(**kwargs)

    def list_providers(self) -> list[str]:
        # Lista todos los providers registrados sin importarlos (lazy-safe).
        return sorted(self._adapter_paths.keys())
```

### 4.2 Integración con ObservabilityManager (Core Infra)

El `ObservabilityManager` de SPEC_09 es el Port. SPEC_18 le inyecta el TracerProvider configurado con los providers resueltos.

```python
# yaml-agno/src/observability/bootstrap.py

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry import trace as trace_api

class ObservabilityBootstrap:
    """
    Construye el TracerProvider, registra todos los providers activos,
    activa OpenInference si algun provider lo requiere, y lo enlaza
    con el ObservabilityManager (Port de SPEC_09).
    """

    def __init__(self, registry: ObservabilityProviderRegistry):
        self.registry = registry

    def bootstrap(self, provider_configs: list[ProviderConfig]):
        provider = TracerProvider()
        needs_openinference = False

        for cfg in provider_configs:
            if not cfg.enabled:
                continue
            adapter = self.registry.resolve(cfg)
            adapter.configure(provider)
            if getattr(adapter, "requires_openinference", False):
                needs_openinference = True

        if needs_openinference:
            try:
                from openinference.instrumentation.agno import AgnoInstrumentor
                AgnoInstrumentor().instrument(tracer_provider=provider)
            except ImportError:
                # warn: OpenInference no instalado pero un provider lo requiere
                pass

        trace_api.set_tracer_provider(provider)
        return provider
```

---

## 5. TRACE EXPORT Y TRACING TO DB

### 5.1 TraceExporter - Persistencia Interna

Además de exportar a providers externos, yaml-agno persiste traces en `trace_db` (dedicado) para query vía API (`GET /traces`).

```python
# yaml-agno/src/observability/trace_exporter.py

from typing import Optional
from agno.db.base import BaseDb, AsyncBaseDb
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace import ReadableSpan

class DbSpanExporter(SpanExporter):
    """
    SpanExporter que escribe spans en la trace_db dedicada.
    Permite query via AgentOS API (GET /traces, /traces/search).
    """

    def __init__(self, db: BaseDb | AsyncBaseDb):
        self.db = db

    def export(self, spans: list[ReadableSpan]) -> SpanExportResult:
        # serializar spans a filas en tabla traces/spans
        for span in spans:
            self._persist_span(span)
        return SpanExportResult.SUCCESS

    def _persist_span(self, span: ReadableSpan) -> None:
        # INSERT en tabla traces:
        # trace_id, span_id, parent_span_id, name, start_time, end_time,
        # attributes_json, status, user_id, session_id, agent_id
        ...

    def shutdown(self) -> None: ...
    def force_flush(self, timeout_millis: int = 30000) -> bool: ...

class TraceExporter:
    """Configura DbSpanExporter y BatchSpanProcessor sobre el TracerProvider."""

    def __init__(self, trace_db: Optional[BaseDb] = None,
                 batch_processing: bool = True,
                 max_queue_size: int = 2048,
                 schedule_delay_millis: int = 3000):
        self.trace_db = trace_db
        self.batch_processing = batch_processing
        self.max_queue_size = max_queue_size
        self.schedule_delay_millis = schedule_delay_millis

    def attach(self, tracer_provider) -> None:
        if self.trace_db is None:
            return
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor, SimpleSpanProcessor
        )
        exporter = DbSpanExporter(self.trace_db)
        processor = (BatchSpanProcessor(exporter,
                                        max_queue_size=self.max_queue_size,
                                        schedule_delay_millis=self.schedule_delay_millis)
                     if self.batch_processing else SimpleSpanProcessor(exporter))
        tracer_provider.add_span_processor(processor)
```

### 5.2 Schema Conceptual de Traces

```
traces:
  trace_id        TEXT PK
  root_span_id    TEXT
  start_time      TIMESTAMPTZ
  end_time        TIMESTAMPTZ
  user_id         TEXT
  session_id      TEXT
  agent_id        TEXT
  status          TEXT          -- ok | error
  span_count      INT

spans:
  span_id         TEXT PK
  trace_id        TEXT FK -> traces.trace_id
  parent_span_id  TEXT NULL
  name            TEXT
  kind            TEXT          -- LLM | TOOL | AGENT | TEAM | WORKFLOW
  start_time      TIMESTAMPTZ
  end_time        TIMESTAMPTZ
  attributes      JSONB
  status_code     TEXT
  status_message  TEXT
```

### 5.3 Configuración `tracing=True` + `db`

Sigue el patrón de docs Agno: `tracing=True` + `db=trace_db` dedica la DB. Si se omite `db`, Agno usa la primera DB encontrada (no recomendado en producción).

```python
# Equivalente YAML -> Python
agent_os = AgentOS(
    agents=[...],
    db=trace_db,
    tracing=True,
)
```

---

## 6. YAML SCHEMAS COMPLETOS

### 6.1 Schema Observability (providers + tracing + trace_db)

```yaml
# yaml-agno/config/observability.yaml
observability:
  # Activar tracing OTel global (mapea a AgentOS(tracing=True))
  tracing: true

  # DB dedicada para traces (recomendado en prod)
  trace_db:
    type: postgres
    db_url: ${TRACE_DB_URL}
    id: traces_db

  # Persistencia interna de spans (DbSpanExporter)
  trace_export:
    enabled: true
    batch_processing: true
    max_queue_size: 2048
    schedule_delay_millis: 3000

  # Multiples providers activos simultaneamente
  providers:
    - provider: langfuse
      enabled: true
      region: us
      env:
        LANGFUSE_PUBLIC_KEY: ${LANGFUSE_PUBLIC_KEY}
        LANGFUSE_SECRET_KEY: ${LANGFUSE_SECRET_KEY}

    - provider: langsmith
      enabled: false
      region: us
      env:
        LANGSMITH_API_KEY: ${LANGSMITH_API_KEY}
        LANGSMITH_PROJECT: ${LANGSMITH_PROJECT}

    - provider: logfire
      enabled: false
      region: eu
      env:
        LOGFIRE_WRITE_TOKEN: ${LOGFIRE_WRITE_TOKEN}
```

### 6.2 Schema Evals

```yaml
# yaml-agno/config/evals.yaml
evals:
  # Thresholds globales (override por eval)
  defaults:
    accuracy_threshold: 8.0
    agent_as_judge_threshold: 7
    performance_p95_ms: 5000

  accuracy:
    - name: "Calculator Evaluation"
      agent_ref: calculator_agent
      evaluator_model: openai/gpt-4o
      input: "What is 10*5 then to the power of 2? do it step by step"
      expected_output: "2500"
      additional_guidelines: "Output should include steps and final answer."
      num_iterations: 3
      threshold: 8.0
      dataset_ref: null          # o nombre de dataset para batch

  agent_as_judge:
    - name: "Explanation Quality"
      agent_ref: tech_writer_agent
      criteria: "Explanation should be clear, beginner-friendly, use simple language"
      scoring_strategy: numeric
      threshold: 7
      evaluator_agent_ref: strict_evaluator_agent
      additional_guidelines:
        - "Must be technically accurate"
        - "Must use analogies"
      on_fail_ref: alert_on_fail   # nombre del handler registrado

  performance:
    - name: "Simple Performance Evaluation"
      func_ref: factories.run_calculator_agent   # callable registrado
      num_iterations: 10
      warmup_runs: 0
      measure_runtime: true
      memory_growth_tracking: false
      is_async: true

  reliability:
    - name: "Tool Call Reliability"
      agent_ref: calculator_agent
      expected_tool_calls:
        - factorial
      threshold: pass              # reliability es pass/fail
```

### 6.3 Pydantic Models de Config

```python
# yaml-agno/src/config/observability_config.py

from pydantic import BaseModel, Field
from typing import Optional

class TraceDbConfig(BaseModel):
    type: str                     # postgres | sqlite
    db_url: Optional[str] = None
    db_file: Optional[str] = None
    id: Optional[str] = "traces_db"

class TraceExportConfig(BaseModel):
    enabled: bool = True
    batch_processing: bool = True
    max_queue_size: int = 2048
    schedule_delay_millis: int = 3000

class ObservabilityConfig(BaseModel):
    tracing: bool = False
    trace_db: Optional[TraceDbConfig] = None
    trace_export: TraceExportConfig = Field(default_factory=TraceExportConfig)
    providers: list[ProviderConfig] = Field(default_factory=list)
```

```python
# yaml-agno/src/config/evals_config.py

from pydantic import BaseModel, Field
from typing import Optional, Union, List

class AccuracyEvalConfig(BaseModel):
    name: str
    agent_ref: Optional[str] = None
    team_ref: Optional[str] = None
    evaluator_model: str
    input: str = ""
    expected_output: str = ""
    additional_guidelines: Optional[str] = None
    num_iterations: int = 1
    threshold: float = 8.0
    dataset_ref: Optional[str] = None

class AgentAsJudgeEvalConfig(BaseModel):
    name: str
    agent_ref: str
    criteria: str
    scoring_strategy: str = "binary"   # numeric | binary
    threshold: int = 7
    evaluator_model: Optional[str] = None
    evaluator_agent_ref: Optional[str] = None
    additional_guidelines: Optional[Union[str, List[str]]] = None
    on_fail_ref: Optional[str] = None
    run_in_background: bool = False

class PerformanceEvalConfig(BaseModel):
    name: str
    func_ref: str
    num_iterations: int = 1
    warmup_runs: int = 0
    measure_runtime: bool = True
    memory_growth_tracking: bool = False
    is_async: bool = False

class ReliabilityEvalConfig(BaseModel):
    name: str
    agent_ref: Optional[str] = None
    team_ref: Optional[str] = None
    expected_tool_calls: List[str]
    threshold: str = "pass"

class EvalDefaults(BaseModel):
    accuracy_threshold: float = 8.0
    agent_as_judge_threshold: int = 7
    performance_p95_ms: int = 5000

class EvalsConfig(BaseModel):
    defaults: EvalDefaults = Field(default_factory=EvalDefaults)
    accuracy: List[AccuracyEvalConfig] = Field(default_factory=list)
    agent_as_judge: List[AgentAsJudgeEvalConfig] = Field(default_factory=list)
    performance: List[PerformanceEvalConfig] = Field(default_factory=list)
    reliability: List[ReliabilityEvalConfig] = Field(default_factory=list)
```

---

## 7. EVAL EXECUTION FLOW

### 7.1 Flujo End-to-End

```mermaid
flowchart TD
    A[POST /eval-runs\ncreate eval run] --> B[EvalRunner.arun_*]
    B --> C{dataset_ref?}
    C -- yes --> D[EvalDatasetLoader.load]
    C -- no --> E[single case from input/expected_output]
    D --> F[Build AccuracyEval/AgentAsJudge/...]
    E --> F
    F --> G["asyncio.TaskGroup\n(parallel cases)"]
    G --> H[case_eval.arun\n-> evaluator model scores]
    H --> I[Aggregate: mean, min, max, pass_rate]
    I --> J{mean >= threshold?}
    J -- yes --> K[status=passed]
    J -- no --> L[status=failed\nthreshold_breached=true]
    K --> M[Persist to trace_db/db]
    L --> M
    M --> N["obs.increment_counter\neval_run_total{status}"]
    N --> O[Return EvalRunResult\n+ eval_run_id]
```

### 7.2 Flujo de Tracing (provider export + DB)

```mermaid
flowchart LR
    A[Agent.run / arun] --> B[AgnoInstrumentor\nOpenInference spans]
    B --> C[TracerProvider]
    C --> D1[Langfuse OTLP]
    C --> D2[Langsmith OTLP]
    C --> D3[DbSpanExporter\ntrace_db]
    D3 --> E[(traces table)]
    E --> F["GET /traces\nGET /traces/search\n(trace query API)"]
```

---

## 8. BEHAVIOR DELTA - BDD SCENARIOS

### 8.1 Eval Run

```gherkin
Scenario 1: Golden Path - AccuracyEval pasa sobre dataset
  GIVEN un dataset "calculator_eval_dataset" con 3 casos
  AND un agente "calculator_agent" registrado
  AND el modelo evaluador "openai/gpt-4o" disponible
  WHEN POST /eval-runs con {eval_type: accuracy, agent_ref: calculator_agent, dataset_ref: calculator_eval_dataset, threshold: 8.0}
  THEN se crea un eval_run con status "running"
  AND cada caso se ejecuta en paralelo via asyncio.TaskGroup
  AND el evaluator model puntúa cada respuesta contra expected_output
  AND el aggregate.mean_score >= 8.0
  AND el eval_run.status pasa a "passed"
  AND el resultado se persiste en trace_db
  AND la métrica eval_run_total{status=passed} se incrementa
```

```gherkin
Scenario 2: Eval Threshold Breach
  GIVEN un eval con threshold 8.0
  AND el mean_score resultante es 6.2
  WHEN el EvalRunner calcula el aggregate
  THEN eval_run.threshold_breached es true
  AND eval_run.status es "failed"
  AND la métrica eval_run_total{status=failed} se incrementa
  AND se emite un span con attribute eval.status=failed
```

```gherkin
Scenario 3: ReliabilityEval - tool call faltante
  GIVEN un agente que debería llamar "factorial"
  AND el agente no invocó ninguna herramienta
  WHEN ReliabilityEvalAdapter.evaluate ejecuta assert_passed()
  THEN se lanza AssertionError
  AND el resultado del caso es passed=false
```

```gherkin
Scenario 4: PerformanceEval mide latencia y memoria
  GIVEN un PerformanceEval con num_iterations=10
  WHEN performance_eval.arun() completa
  THEN el resultado incluye avg_runtime_ms
  AND el resultado incluye avg_memory_mb
  Y (si memory_growth_tracking=true) reporta memory_delta_mb
```

### 8.2 Provider Switch

```gherkin
Scenario 5: Activar Langfuse via YAML
  GIVEN un config observability.yaml con provider langfuse enabled=true
  AND LANGFUSE_PUBLIC_KEY y LANGFUSE_SECRET_KEY en entorno
  WHEN ObservabilityBootstrap.bootstrap() ejecuta
  THEN se crea un TracerProvider
  AND LangfuseAdapter.configure adjunta un OTLPSpanExporter
  Y el endpoint apunta a us.cloud.langfuse.com/api/public/otel
  Y el header Authorization=Basic <base64(pub:secret)> se setea
```

```gherkin
Scenario 6: Switch provider Langfuse -> Langsmith en caliente
  GIVEN el sistema corriendo con Langfuse activo
  WHEN el operador cambia provider a langsmith en config y recarga
  THEN ObservabilityBootstrap reconstruye el TracerProvider
  AND LangsmithAdapter.configure reemplaza el exporter
  Y los nuevos spans se exportan a smith.langchain.com/otel
  AND los spans antiguos ya exportados a Langfuse no se pierden
```

```gherkin
Scenario 7: Multiples providers simultaneos
  GIVEN config con langfuse y logfire ambos enabled=true
  WHEN bootstrap ejecuta
  THEN el TracerProvider tiene dos SpanProcessor
  Y cada span se exporta a ambos backends
  Y si alguno requiere OpenInference, AgnoInstrumentor se activa una sola vez
```

```gherkin
Scenario 8: Provider desconocido
  GIVEN config con provider "no_existe"
  WHEN ObservabilityProviderRegistry.resolve ejecuta
  THEN se lanza ValueError "Unknown observability provider: no_existe"
  Y el bootstrap aborta antes de iniciar el TracerProvider
```

### 8.3 Tracing Export

```gherkin
Scenario 9: Tracing persistido en trace_db dedicada
  GIVEN tracing=true y trace_db apuntando a postgres dedicado
  WHEN un agente ejecuta Agent.run
  THEN DbSpanExporter escribe spans en tabla traces/spans
  Y la DB principal de sesiones NO recibe traces
  Y GET /traces retorna los traces de trace_db
```

```gherkin
Scenario 10: tracing sin db dedicado (warning)
  GIVEN tracing=true y trace_db NO configurado
  WHEN bootstrap ejecuta
  THEN se emite un warning "trace_db no configurado"
  Y los traces se intentan persistir en la primera DB encontrada
  Y este comportamiento queda marcado como no recomendado para producción
```

---

## 9. TDD MICRO-TASK EXECUTION PROTOCOL

Strict TDD RED/GREEN/REFACTOR. Cada tarea: test primero, falla, implementación mínima, commit.

### TASK_001: EvalCase y EvalDataset models
- **File**: `yaml-agno/src/evals/dataset_loader.py`
- **Test**: `tests/unit/evals/test_dataset_loader.py`
- **RED**:
  ```python
  def test_eval_case_validation():
      c = EvalCase(id="c1", input="2+2?", expected_output="4")
      assert c.id == "c1"
      assert c.expected_output == "4"

  def test_eval_dataset_load(tmp_path):
      f = tmp_path / "d.yaml"
      f.write_text("name: d\nversion: '1'\nformat: accuracy\ncases:\n  - id: c1\n    input: q\n    expected_output: a\n")
      loader = EvalDatasetLoader(tmp_path)
      ds = loader.load("d")
      assert ds.name == "d"
      assert len(ds.cases) == 1
  ```
- **GREEN**: Implementar `EvalCase`, `EvalDataset`, `EvalDatasetLoader`.
- **Commit**: `feat(evals): add eval dataset models and loader`

### TASK_002: AccuracyEvalAdapter build
- **File**: `yaml-agno/src/evals/accuracy_adapter.py`
- **Test**: `tests/unit/evals/test_accuracy_adapter.py`
- **RED**:
  ```python
  def test_accuracy_adapter_build():
      a = AccuracyEvalAdapter(name="t", evaluator_model="m", agent_ref="x",
                              input="q", expected_output="4")
      e = a.build(resolved_agent=object(), resolved_model=object())
      assert e.input == "q"
      assert e.expected_output == "4"
  ```
- **GREEN**: Implementar adapter con `build()`.
- **Commit**: `feat(evals): add accuracy eval adapter`

### TASK_003: AgentAsJudgeEvalAdapter build (numeric + binary)
- **File**: `yaml-agno/src/evals/agent_as_judge_adapter.py`
- **Test**: `tests/unit/evals/test_agent_as_judge_adapter.py`
- **RED**:
  ```python
  def test_agent_as_judge_numeric():
      a = AgentAsJudgeEvalAdapter(name="t", criteria="clear", scoring_strategy="numeric", threshold=7)
      assert a.scoring_strategy == "numeric"

  def test_agent_as_judge_binary():
      a = AgentAsJudgeEvalAdapter(name="t", criteria="clear", scoring_strategy="binary")
      assert a.scoring_strategy == "binary"
  ```
- **GREEN**: Implementar con soporte evaluator_agent opcional.
- **Commit**: `feat(evals): add agent-as-judge adapter`

### TASK_004: PerformanceEvalAdapter y ReliabilityEvalAdapter
- **File**: `yaml-agno/src/evals/performance_adapter.py`, `reliability_adapter.py`
- **Test**: `tests/unit/evals/test_perf_reliability_adapter.py`
- **RED**:
  ```python
  def test_performance_adapter_defaults():
      a = PerformanceEvalAdapter(name="t", func_ref="f")
      assert a.num_iterations == 1
      assert a.is_async is False

  def test_reliability_adapter():
      a = ReliabilityEvalAdapter(name="t", expected_tool_calls=["factorial"])
      assert "factorial" in a.expected_tool_calls
  ```
- **GREEN**: Implementar ambos adapters.
- **Commit**: `feat(evals): add performance and reliability adapters`

### TASK_005: EvalRunner arun_accuracy con TaskGroup
- **File**: `yaml-agno/src/evals/runner.py`
- **Test**: `tests/integration/evals/test_runner.py`
- **RED**:
  ```python
  async def test_runner_accuracy_pass(monkeypatch):
      runner = EvalRunner(db=None, observability_manager=FakeObs())
      # mockear AccuracyEval.arun para retornar avg_score 9.0
      result = await runner.arun_accuracy(adapter, dataset, agent, model, threshold=8.0)
      assert result.status == "passed"
      assert result.aggregate["mean_score"] >= 8.0

  async def test_runner_accuracy_breach(monkeypatch):
      # avg_score 5.0
      result = await runner.arun_accuracy(...)
      assert result.status == "failed"
      assert result.threshold_breached is True
  ```
- **GREEN**: Implementar `EvalRunner.arun_accuracy` con `asyncio.TaskGroup`.
- **Commit**: `feat(evals): add eval runner with taskgroup`

### TASK_006: ObservabilityProviderRegistry resolve
- **File**: `yaml-agno/src/observability/provider_registry.py`
- **Test**: `tests/unit/observability/test_registry.py`
- **RED**:
  ```python
  def test_registry_lists_all_providers():
      r = ObservabilityProviderRegistry()
      providers = r.list_providers()
      assert "langfuse" in providers
      assert "langsmith" in providers
      assert len(providers) == 16

  def test_registry_resolve_unknown():
      r = ObservabilityProviderRegistry()
      cfg = ProviderConfig(provider="nope")
      import pytest
      with pytest.raises(ValueError):
          r.resolve(cfg)
  ```
- **GREEN**: Implementar registry con los 16 adapters.
- **Commit**: `feat(observability): add provider registry with 16 adapters`

### TASK_007: LangfuseAdapter y LangsmithAdapter configure
- **File**: `yaml-agno/src/observability/providers/langfuse_adapter.py`, `langsmith_adapter.py`
- **Test**: `tests/unit/observability/test_langfuse_langsmith.py`
- **RED**:
  ```python
  def test_langfuse_sets_endpoint_and_auth(monkeypatch):
      monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
      monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
      a = LangfuseAdapter(region="us")
      a.configure(FakeTracerProvider())
      import os
      assert "us.cloud.langfuse.com" in os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]
      assert "Basic" in os.environ["OTEL_EXPORTER_OTLP_HEADERS"]

  def test_langsmith_region_eu():
      assert LANGSMITH_ENDPOINTS["eu"].endswith("/traces")
  ```
- **GREEN**: Implementar ambos adapters.
- **Commit**: `feat(observability): add langfuse and langsmith adapters`

### TASK_008: Resto de adapters (14 providers)
- **File**: `yaml-agno/src/observability/providers/*.py`
- **Test**: `tests/unit/observability/test_all_providers.py`
- **RED**:
  ```python
  @pytest.mark.parametrize("provider_name", [
      "arize","agentops","atla","langdb","langtrace","langwatch",
      "latitude","maxim","mlflow","openlit","traceloop","weave","logfire","opentelemetry",
  ])
  def test_each_adapter_has_configure(provider_name):
      r = ObservabilityProviderRegistry()
      cfg = ProviderConfig(provider=provider_name)
      adapter = r.resolve(cfg)
      assert hasattr(adapter, "configure")
  ```
- **GREEN**: Implementar los 14 adapters restantes.
- **Commit**: `feat(observability): add remaining 14 provider adapters`

### TASK_009: ObservabilityBootstrap con OpenInference
- **File**: `yaml-agno/src/observability/bootstrap.py`
- **Test**: `tests/unit/observability/test_bootstrap.py`
- **RED**:
  ```python
  def test_bootstrap_activates_openinference_when_needed():
      r = ObservabilityProviderRegistry()
      b = ObservabilityBootstrap(r)
      provider = b.bootstrap([ProviderConfig(provider="langfuse", enabled=True)])
      assert provider is not None

  def test_bootstrap_skips_disabled():
      b = ObservabilityBootstrap(ObservabilityProviderRegistry())
      provider = b.bootstrap([ProviderConfig(provider="langfuse", enabled=False)])
      # provider creado sin processors de langfuse
      assert provider is not None
  ```
- **GREEN**: Implementar bootstrap con detección de `requires_openinference`.
- **Commit**: `feat(observability): add bootstrap with openinference detection`

### TASK_010: TraceExporter con DbSpanExporter
- **File**: `yaml-agno/src/observability/trace_exporter.py`
- **Test**: `tests/unit/observability/test_trace_exporter.py`
- **RED**:
  ```python
  def test_trace_exporter_attaches_processor():
      fake_db = FakeDb()
      ex = TraceExporter(trace_db=fake_db, batch_processing=False)
      tp = FakeTracerProvider()
      ex.attach(tp)
      assert len(tp.processors) == 1

  def test_trace_exporter_no_db_noop():
      ex = TraceExporter(trace_db=None)
      tp = FakeTracerProvider()
      ex.attach(tp)
      assert len(tp.processors) == 0
  ```
- **GREEN**: Implementar `DbSpanExporter` y `TraceExporter`.
- **Commit**: `feat(observability): add db trace exporter`

### TASK_011: ObservabilityConfig y EvalsConfig Pydantic
- **File**: `yaml-agno/src/config/observability_config.py`, `evals_config.py`
- **Test**: `tests/unit/config/test_obs_evals_config.py`
- **RED**:
  ```python
  def test_observability_config_parse():
      cfg = ObservabilityConfig.model_validate({
          "tracing": True,
          "trace_db": {"type": "postgres", "db_url": "x"},
          "providers": [{"provider": "langfuse", "enabled": True, "region": "us"}],
      })
      assert cfg.tracing is True
      assert cfg.providers[0].provider == "langfuse"

  def test_evals_config_defaults():
      cfg = EvalsConfig.model_validate({"accuracy": [{"name":"x","evaluator_model":"m","agent_ref":"a","input":"q","expected_output":"a"}]})
      assert cfg.defaults.accuracy_threshold == 8.0
  ```
- **GREEN**: Implementar modelos de config.
- **Commit**: `feat(config): add observability and evals config models`

### TASK_012: Integración ObservabilityManager (Port SPEC_09)
- **File**: `yaml-agno/src/observability/integration.py`
- **Test**: `tests/integration/observability/test_integration.py`
- **RED**:
  ```python
  async def test_eval_run_uses_obs_manager_span():
      obs = FakeObservabilityManager()
      runner = EvalRunner(db=None, observability_manager=obs)
      await runner.arun_accuracy(adapter, dataset, agent, model, threshold=8.0)
      assert obs.spans_started == 1
      assert "eval_run.accuracy" in obs.span_names
      assert obs.counters["eval_run_total"] >= 1
  ```
- **GREEN**: Cablear el `ObservabilityManager` (Port SPEC_09) en EvalRunner y bootstrap.
- **Commit**: `feat(observability): integrate observability manager port`

---

## 10. SUPUESTOS TÉCNICOS ADOPTADOS

### [Decisión 1] OpenTelemetry como capa común
Todos los providers OTel-compatibles comparten el mismo `TracerProvider`. Los providers con SDK propio (AgentOps, Weave, Traceloop) se inicializan vía su `init()` pero el registry los trata uniformemente.

### [Decisión 2] asyncio.TaskGroup para eval batch (NO gather)
Los casos de un dataset se paralelizan con `asyncio.TaskGroup`. Cancelación estructurada. Si un caso falla catastróficamente, el TaskGroup propaga la excepción sin dejar tareas huérfanas.

### [Decisión 3] trace_db dedicado en producción
`trace_db` separa traces de datos operacionales (sesiones, memoria). Esto sigue la recomendación explícita de los docs Agno y permite escalar observabilidad independientemente.

### [Decisión 4] OpenInference como instrumentación base
`openinference-instrumentation-agno` es la instrumentación canónica. Se activa una sola vez en el bootstrap si algún provider lo requiere (no múltiples veces).

### [Decisión 5] Threshold breach no es error de sistema
Un eval que no supera el threshold retorna `status=failed` (no lanza excepción). Solo errores técnicos (modelo caído, dataset corrupto) resultan en `status=error`.

### [Decisión 6] Secrets via env, no en YAML
Las claves (`LANGFUSE_SECRET_KEY`, etc.) se declaran como `${VAR}` en YAML y se resuelven desde entorno. Nunca se hardcodean en config versionado.

---

## 11. PREGUNTAS DE CALIBRACIÓN ESTRATÉGICA

### [Pregunta 1] ¿Sampling para export a providers externos?
`100%` de traces a Langfuse puede ser costoso en alto volumen.
Implica:
- **100%**: máximo detalle, alto costo de export y almacenamiento en el provider.
- **10%**: balance. Pierde casos raros.
- **Parent-based + 10% root**: captura traces con error siempre, muestrea exit.
Trade-off: costo vs debuggability. SPEC_09 §5 ya plantea sampling para spans SRE; aquí se hereda la misma política.

### [Pregunta 2] ¿Eval on every run vs eval on demand?
¿Correr AgentAsJudge automáticamente tras cada `POST /agents/*/runs` (post-hook), o solo vía `POST /eval-runs`?
Implica:
- **Post-hook**: feedback continuo, costo de LLM por request.
- **On demand**: control del operador, sin overhead en hot path.
Los docs Agno muestran `AgentAsJudgeEval` como post-hook posible (`usage/agent-as-judge-post-hook`).

### [Pregunta 3] ¿Regresión automática en CI?
¿Correr los evals de accuracy/reliability en cada PR contra un dataset fijo y bloquear merge si `mean_score` baja?
Implica:
- **Sí**: detecta regresiones, pero los evals LLM son no-deterministas (flaky).
- **No**: evaluación manual periódica.
Trade-off: seguridad de calidad vs ruido de flakiness.

### [Pregunta 4] ¿Retención de eval runs en DB?
¿30/90/365 días de historial de eval runs?
Trade-off: capacidad de análisis de drift vs storage.

### [Pregunta 5] ¿Provider múltiple obligatorio o uno activo?
¿Permitir N providers exportando simultáneamente (duplicación de traces) o forzar uno activo?
Implica: el registry soporta N, pero el costo de export se multiplica.

---

*¿Deseas profundizar la especificación técnica al **Nivel 6** de algún componente (ej. scoring avanzado de AgentAsJudge, o el adapter de un provider específico) o autorizar la ejecución de estas tareas por parte del equipo de agentes?*
