# yaml-agno - SPECIFICATION DOCUMENT

Version: 0.1.0
Date: 2025-06-13
Status: DRAFT

---

## 1. PROJECT OVERVIEW

**yaml-agno** is a Python pip-installable library that abstracts the Agno Framework through YAML configuration.

**Goal**: Enable a programming agent to generate complete agent systems without writing Python code directly, while leveraging the full Agno framework without reimplementation.

**Repository**: `C:\Dropbox\DOC.RECA\06-Software\yaml-agno\`

---

## 2. ARCHITECTURE DECISIONS

### 2.1 What to Abstract (YES)

| Component | Abstract? | Rationale |
|-----------|------------|-----------|
| **Agent() constructor** | ✅ YES | All 80+ parameters (model, instructions, tools, knowledge, etc.) |
| **Team() constructor** | ✅ YES | All parameters (members, mode, workflows, etc.) |
| **Workflow primitives** | ✅ YES | Step, Parallel, Condition, Router, Loop |
| **Tool composition** | ✅ YES | Toolkit bundling, tool selection |
| **Knowledge sources** | ✅ YES | Vector DBs, file systems, databases |
| **Learning config** | ✅ YES | Adaptive learning per agent |
| **Culture config** | ✅ YES | Organizational knowledge |
| **Evals config** | ✅ YES | Metrics, datasets, thresholds |
| **Context Providers** | ✅ YES | External data sources (web, DB, MCP) |
| **Hooks (pre/post)** | ✅ YES | Custom logic hooks |
| **Guardrails** | ✅ YES | Input/output safety rules |
| **HITL (Human-in-the-loop)** | ✅ YES | Approval flows |
| **Skills** | ✅ YES | Structured instructions |
| **Multimodal I/O** | ✅ YES | Image/Audio/Video/File configurations |
| **Context Compression** | ✅ YES | Compression strategies |
| **DI System** | ✅ YES | Dynamic variable injection |
| **Deployment modes** | ✅ YES | api, chatbot, hybrid wrappers |

### 2.2 What NOT to Abstract (NO)

| Component | Abstract? | Rationale |
|-----------|------------|-----------|
| **AgentOS internals** | ❌ NO | Infrastructure (lifespan, session mgmt, run loop) |
| **Environment variables** | ❌ NO | Deployment-level config |
| **Agno framework code** | ❌ NO | We build ON TOP, don't reimplement |

### 2.3 Abstraction Layers

```
┌─────────────────────────────────────────┐
│         yaml-agno (YAML)               │
│  Agent, Team, Workflow configurations   │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│      yaml-agno Factory Pattern          │
│  YAML → Pydantic → Agno Objects         │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│         Agno Framework                  │
│  Agent, Team, Workflow, Tools, etc.     │
└─────────────────────────────────────────┘
```

---

## 3. TEMPLATES SYSTEM (50+ Templates)

### 3.1 Template Structure (with Frontmatter)

```yaml
---
template: agent_simple_text
description: "Simple text → text agent for chatbots"
inputs: { type: text }
outputs: { type: text }
difficulty: beginner
tags: [chatbot, simple, text]
examples: ["agno-chat", "customer-service"]
---

agent:
  name: "Simple Chatbot"
  model: openai/gpt-4o
  instructions: |
    You are a helpful assistant...
```

### 3.2 Agent Templates (25+)

**By Input/Output:**
- `agent_simple_text.yaml` - Text → Text
- `agent_multimodal_in.yaml` - Image/Audio/Video → Text
- `agent_multimodal_out.yaml` - Text → Image/Audio/Video
- `agent_multimodal_full.yaml` - Multimedia → Multimedia
- `agent_file_output.yaml` - Text → File (PDF, DOCX)
- `agent_structured_in.yaml` - Schema → Text
- `agent_structured_out.yaml` - Text → Schema
- `agent_structured_full.yaml` - Schema → Schema

**By Architecture:**
- `agent_rag_simple.yaml` - Basic RAG
- `agent_rag_hybrid.yaml` - Hybrid search RAG
- `agent_rag_multivector.yaml` - Multi-vector RAG
- `agent_with_memory.yaml` - Long-term memory
- `agent_with_learning.yaml` - Adaptive learning
- `agent_with_knowledge.yaml` - Knowledge base

**By Safety:**
- `agent_guardrails_input.yaml` - Input guardrails
- `agent_guardrails_output.yaml` - Output guardrails
- `agent_guardrails_full.yaml` - Full guardrails
- `agent_hitl_simple.yaml` - Basic HITL
- `agent_hitl_approval.yaml` - Approval workflow

### 3.3 Team Templates (20+)

**By Mode:**
- `team_coordinate.yaml` - Coordination
- `team_route.yaml` - Dynamic routing
- `team_broadcast.yaml` - Broadcast
- `team_tasks.yaml` - DAG dependencies
- `team_cooroutine.yaml` - Coroutines

**By Composition:**
- `team_specialist.yaml` - Specialists
- `team_researcher.yaml` - Parallel researchers
- `team_critic.yaml` - Critic + Generator
- `team_negotiation.yaml` - Negotiation
- `team_hierarchy.yaml` - Hierarchy

### 3.4 Workflow Templates (15+)

**By Pattern:**
- `workflow_linear.yaml` - Sequential steps
- `workflow_parallel.yaml` - Parallel execution
- `workflow_condition.yaml` - Conditional branching
- `workflow_loop.yaml` - Iterative loop
- `workflow_router.yaml` - Dynamic routing
- `workflow_mixed.yaml` - Combined patterns

**By Use Case:**
- `workflow_etl.yaml` - ETL pipeline
- `workflow_approval.yaml` - Approval workflow
- `workflow_review.yaml` - Human review
- `workflow_pipeline.yaml` - Data pipeline
- `workflow_orchestration.yaml` - Complex orchestration

---

## 4. WORKFLOW SYSTEM

### 4.1 Workflow Primitives (Abstracted)

| Primitive | YAML Key | Description |
|-----------|----------|-------------|
| **Step** | `step` | Basic execution unit (Agent, Team, Function, Workflow) |
| **Steps** | `steps` | Sequential execution |
| **Parallel** | `parallel` | Concurrent execution with merged state |
| **Condition** | `condition` | If/else branching (CEL or callable) |
| **Router** | `router` | Dynamic step selection |
| **Loop** | `loop` | Iterative execution (CEL or callable end condition) |

### 4.2 Workflow YAML Example

```yaml
workflow:
  name: "ETL Pipeline"
  description: "Extract, Transform, Load data pipeline"
  
  steps:
    - step: extract
      type: agent
      agent: data_extractor
      execute: true
    
    - step: transform
      type: parallel
      steps:
        - step: validate
          type: agent
          agent: validator
        - step: normalize
          type: agent
          agent: normalizer
    
    - step: load
      type: condition
      condition: "${result.valid == true}"
      if_true: data_loader
      if_false: error_handler
    
    - step: cleanup
      type: function
      function: cleanup_resources
      finally: true
```

### 4.3 CEL Support

Common Expression Language (CEL) for conditions, routers, and loops:

```yaml
condition: "${input.amount > 1000 && input.approved == true}"
router:
  expression: "${input.category}"
  cases:
    "billing": billing_agent
    "support": support_agent
    "*": default_agent
loop:
  end_condition: "${iteration_count < 10 || result.success == true}"
```

---

## 5. DEPENDENCY INJECTION SYSTEM

### 5.1 Purpose

Inject dynamic configuration (user variables, database values) into agents/teams at runtime without modifying YAML.

### 5.2 DI Architecture

**Components:**
- `di_factory` - DI factory in YAML
- `providers` - Data sources (DB, API, Env, File)
- `template_syntax` - `${provider.key}` for injection

### 5.3 Providers

| Provider Type | YAML Key | Description |
|---------------|----------|-------------|
| **Database** | `database` | Query database for values |
| **Env Var** | `env` | Environment variables |
| **API** | `api` | REST API endpoint |
| **File** | `file` | JSON/YAML/TOML files |

### 5.4 DI YAML Example

```yaml
di_factory:
  providers:
    - name: user_db
      type: database
      connection: "${DB_URL}"
      table: users
      key_field: user_id
    
    - name: config_api
      type: api
      url: "${CONFIG_API_URL}"
      headers:
        Authorization: "Bearer ${API_KEY}"
    
    - name: app_config
      type: file
      path: ./config/app.json

agent:
  name: "Personal Assistant"
  instructions: |
    You are a helpful assistant for ${user_db.name} (${user_db.email}).
    Preferences: ${user_db.preferences}
    Language: ${user_db.language}
  tools:
    - tool: user_context
      data:
        user_id: "${user_db.id}"
        tier: "${user_db.tier}"
```

### 5.5 Injection Points

- `agent.instructions` - Template variables in prompts
- `agent.tools[*].parameters` - Tool configuration
- `team.instructions` - Team-level prompts
- `workflow.steps[*].parameters` - Step configuration
- `knowledge.filters` - Dynamic knowledge filters

### 5.6 Resolution Order

1. Database providers (query current user/context)
2. API providers (fetch external config)
3. File providers (load static config)
4. Env var providers (fallback)

---

## 6. CONFIGURATION SYSTEMS

### 6.1 Toolkit (Abstracted)

```yaml
toolkit:
  name: "my_tools"
  tools:
    - tool: web_search
      provider: google
      max_results: 10
    - tool: file_reader
      allowed_paths: [./docs, ./data]
  exclude_tools: [dangerous_tool]
  add_instructions: true
```

### 6.2 Learning (Abstracted)

```yaml
learning:
  type: sqlite
  table: agent_learnings
  add_to_context: true
  auto_save: true
```

### 6.3 Culture (Abstracted)

```yaml
culture:
  type: pgvector
  table: organizational_knowledge
  add_to_context: true
  scope: [brand, policies, guidelines]
```

### 6.4 Evals (Abstracted)

```yaml
evals:
  metrics:
    - accuracy
    - latency
    - cost
  dataset: test_cases.json
  threshold: 0.8
  auto_run: true
```

### 6.5 Context Providers (Abstracted)

```yaml
context_providers:
  - provider: filesystem
    root: ./docs
    mode: agent
  - provider: database
    connection_string: postgres://...
    readonly: true
  - provider: web
    backend: exa
```

### 6.6 Hooks (Abstracted)

```yaml
hooks:
  pre_hooks:
    - hook: validate_input
      function: validate_schema
      blocking: true
    - hook: check_quota
      function: verify_usage_limits
  post_hooks:
    - hook: log_output
      function: write_to_log
    - hook: update_metrics
      function: record_metrics
```

### 6.7 Guardrails (Abstracted)

```yaml
guardrails:
  input:
    - rail: pii_detection
      provider: openai_moderation
      action: mask
      fields: [ssn, credit_card]
    - rail: prompt_injection
      action: block
  output:
    - rail: moderation
      provider: openai_moderation
      action: review
```

### 6.8 Human-in-the-Loop (Abstracted)

```yaml
hitl:
  approvals:
    - tool: send_email
      type: required
      approvers: [supervisor]
      timeout: 3600
    - tool: transfer_funds
      type: multi
      approvers: [manager, director]
      min_required: 2
```

### 6.9 Skills (Abstracted)

```yaml
skills:
  - skill: writing_style
    type: structured_instructions
    content: |
      Always write in a professional tone.
      Use active voice.
  - skill: domain_knowledge
    type: knowledge_reference
    topics: [finance, regulations]
```

### 6.10 Multimodal (Abstracted)

```yaml
multimodal:
  input:
    accept: [text, image, audio, video, file]
    max_size: 50MB
  output:
    generate: [text, image, audio, video, file]
    formats:
      image: [png, jpg]
      audio: [mp3, wav]
```

### 6.11 Context Compression (Abstracted)

```yaml
compression:
  enabled: true
  strategy: semantic
  threshold_tokens: 8000
  priority_sections:
    - knowledge
    - history
```

---

## 7. DEPLOYMENT MODES

### 7.1 Mode Options

| Mode | Description | Wrapper |
|------|-------------|----------|
| **api** | FastAPI endpoint with structured I/O | REST/WebSocket |
| **chatbot** | Interactive CLI/Web UI | Chat interface |
| **hybrid** | Both API and chatbot | Multiple wrappers |

### 7.2 Mode YAML Example

```yaml
agent:
  name: "facturacion"
  role: "Invoice processing agent"
  model: openai/gpt-4o
  instructions: "Process structured invoice requests..."

deployment:
  mode: api  # | chatbot | hybrid
  api:
    endpoint: /facturacion
    method: POST
    streaming: true
  chatbot:
    ui: cli  # | web
```

---

## 8. COGNITIVE PROFILE SCHEMA

### 8.1 Purpose

Define agent/team mission, capabilities, and contracts for inter-team communication.

### 8.2 Cognitive Profile YAML

```yaml
cognitive_profile:
  mission: "Process invoices and generate PDF documents"
  
  capabilities:
    input:
      - structured_invoice_request
    output:
      - invoice_pdf
      - qr_code
      - email_notification
    tools:
      - afip_api
      - pdf_generator
      - email_sender
  
  input_schema:
    type: object
    properties:
      cliente: { type: string }
      monto: { type: number }
      iva: { type: number }
  
  output_schema:
    type: object
    properties:
      factura_pdf: { type: string }
      qr: { type: string }
  
  constraints:
    max_amount: 1000000
    requires_approval: true
```

---

## 9. ROADMAP (12 Weeks - Weekly MVPs)

| Week | MVP | yaml-agno | Meta-Agent/Product | Validation |
|------|-----|-----------|--------------------|------------|
| 1 | yaml-agno Core | Agent config (name, model, instructions, tools[]) + Templates (50+), DI System | — | Create 1 agent from YAML |
| 2 | Teams + Docs Expert | Team config (members[], instructions) + Workflow primitives | **Agno Docs Expert** | Docs Expert helps create 1 Team |
| 3 | Prompting + cognitive_profile | cognitive_profile schema + deployment.mode | **Prompting + Ing. Contexto** | Prompting Expert improves 1 Team |
| 4 | Protocols + Communication | MCP/A2A/ACP layers + Guardrails + HITL | — | 2 teams communicate (Facturas ↔ Profiler) |
| 5 | CodeGraph + Code Expert | CodeGraph integrated + Skills, Multimodal, Compression | **Agno Code Expert** | CodeGraph Expert creates 1 Team |
| 6 | Team Templates | Template system + Facturación AFIP | **Team Facturación** | Team processes 1 real request |
| 7 | Multi-Tenant + Hot-Reload | ConfigDB multi-tenant, hot-reload + Excel Processing | **Team Excel Processing** | 2 clients with same codebase |
| 8 | Orchestrator Integration | Gus/Cloud integration + Email Processing | **Team Email** | Gus coordinates 3 teams |
| 9 | Learning Machine | — | **Learning Machine** | Analyzes 5 teams, suggests improvements |
| 10 | Optimization + Meetings | Model Selector + Meeting Summarization | **Team Meetings** | 4 teams optimized |
| 11 | Docs + Examples | Complete docs, 10+ examples | — | External developer creates 1 team |
| 12 | Release 1.0 | pip installable, tests 100%+ | — | 2 CENF clients in production |

---

## 10. IMPLEMENTATION PRIORITIES

### 10.1 Week 1 - Core
- [ ] Agent YAML schema (name, model, instructions, tools[])
- [ ] Pydantic models for Agent config
- [ ] Factory: YAML → Agent()
- [ ] Templates system (50+ templates with frontmatter)
- [ ] DI System (Database, Env, API, File providers)
- [ ] CLI: `yaml-agno create agent.yaml`
- [ ] Basic tests (TDD, 100%+ coverage)

### 10.2 Week 2 - Teams
- [ ] Team YAML schema (members[], mode, instructions)
- [ ] Factory: YAML → Team()
- [ ] Agno Docs Expert meta-agent
- [ ] MCP integration for Agno Docs
- [ ] Team templates (20+)

### 10.3 Week 3 - Cognitive Profile
- [ ] cognitive_profile schema
- [ ] deployment.mode (api/chatbot/hybrid)
- [ ] Prompting Expert meta-agent
- [ ] Prompting knowledge base

### 10.4 Week 4 - Communication
- [ ] MCP layer (expose tools)
- [ ] A2A layer (agent-to-agent)
- [ ] ACP layer (structured messages)
- [ ] Guardrails system
- [ ] HITL system

---

## 11. TESTING REQUIREMENTS

### 11.1 Strict TDD Mode

- **Coverage**: 100%+ (every line must be covered)
- **Test Runner**: pytest (to be detected during sdd-init)
- **PR Budget**: 200-250 lines max (not 400)
- **Git Workflow**: feature-branch-chain

### 11.2 Test Categories

- Unit tests for each Pydantic model
- Factory tests (YAML → Object)
- Integration tests with Agno
- Template validation tests
- DI provider tests

---

## 12. NON-NEGOTIABLE REQUIREMENTS

1. **MVPs semanales** - Every week must have a functional, demostrable MVP
2. **Strict TDD** - 100%+ test coverage
3. **YAML-first** - All config via YAML, no Python code for users
4. **DI System** - Dynamic variable injection from DB/API/Env
5. **Templates auto-prompted** - Frontmatter describes usage
6. **Interconocimiento cognitivo** - Teams know their I/O schemas
7. **Caja negra** - Client sees I/O, developer sees YAML
8. **CEL + Callables** - Both from day one
9. **Multi-tenant ready** - ConfigDB + hot-reload

---

## CHANGELOG

- **2025-06-13**: v0.1.0 - Initial spec with all architectural decisions
  - Defined what to abstract (YES/NO)
  - Templates system (50+)
  - Workflow primitives (6)
  - DI System (4 providers)
  - Configuration systems (11)
  - Roadmap (12 weeks)
  - Implementation priorities
  - Testing requirements
  - Non-negotiable requirements
