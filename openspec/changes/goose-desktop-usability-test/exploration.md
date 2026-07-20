# Exploration: Goose Desktop Usability/Stress Test for Novice Agent Users

## Executive Summary

This exploration investigated how to design and execute a usability/stress test of Goose Desktop targeting problems encountered by novice users interacting with AI agents. Goose Desktop is an open-source Electron + React desktop app (Rust backend) that provides chat-based agent interaction through 15+ LLM providers, located at `C:\Dropbox\DOC.RECA\06-Software\goose\`. It serves as the GUI/presentation layer in the CENF ecosystem.

Key findings: agent interfaces present **fundamentally different usability challenges** from traditional apps — loss of direct manipulation, non-deterministic behavior, trust as a UX dimension, and opaque error recovery. The onboarding flow (provider selection), extension/MCP system, and tool approval model are specific high-friction areas for novices. Recommended approach is a **hybrid methodology** combining expert cognitive walkthrough (pre-test) with a full moderated user test of 8-12 novice participants using guided scenarios with embedded stress conditions.

---

## 1. Current State

### What is Goose Desktop

Goose Desktop is an open-source AI agent desktop application under the [Agentic AI Foundation (AAIF)](https://aaif.io/) at the Linux Foundation. It provides:

- **Desktop UI**: Electron + React + TypeScript (`ui/desktop/src/`)
- **Backend**: Rust server binary (`goosed`) with agent loop, provider management, MCP extensions
- **CLI**: Rust CLI (`goose-cli`)
- **API**: ACP protocol for editor integration

In the CENF ecosystem, Goose is the UI/presentation layer through which non-technical users interact with agents built on Agno/yaml-agno infrastructure.

### How It Works Today (User Flow)

1. **Installation & Launch** → Electron app starts → `goosed` binary spawns as subprocess
2. **Onboarding** (`OnboardingGuard.tsx`) → Checks for configured provider → Shows ProviderSelector if none found → User picks a provider + model → Telemetry consent → Navigate to Hub
3. **Hub** (`Hub.tsx`) → Main landing page with session insights → ChatInput for new conversations
4. **Chat Session** (`BaseChat.tsx`, `ChatInput.tsx`) → User types request → Agent processes via LLM provider → Tool calls executed via MCP extensions → Results streamed back
5. **Extensions** → MCP servers provide tools (file system, web, git, etc.)
6. **Recipes** → Reusable agent workflows in YAML/JSON
7. **Settings** → Provider config, extensions, models, appearance, permissions, etc.

### Key Architecture Points

- **Architecture** (from `documentation/docs/goose-architecture/goose-architecture.md`): Three components — Interface (desktop/CLI), Agent (core Rust loop), Extensions (MCP servers)
- **Interactive Loop**: Human Request → Provider Chat → Model Extension Call → Response to Model → Context Revision → Model Response
- **Error Handling**: Errors are caught and sent back to the LLM as tool responses (self-healing loop)
- **i18n**: React-Intl with ICU MessageFormat (from `I18N.md`)
- **UI**: 58 components in `ui/desktop/src/components/`, including onboarding, chat, settings, extensions, recipes, sessions, apps
- **Testing**: Playwright e2e tests, Vitest unit tests, Rust integration tests

---

## 2. Unique Usability Challenges of Agent Interfaces

Unlike traditional apps where the user directly manipulates the UI, agent interfaces invert the control model:

| Dimension | Traditional App | Agent Interface |
|-----------|----------------|-----------------|
| **Control** | User clicks/menus | User types intent, agent executes |
| **Feedback** | Immediate, deterministic | Delayed, non-deterministic |
| **Errors** | User must fix | Agent may self-recover (or compound) |
| **Learning** | Feature discovery through menus | Must ask agent to do it |
| **Trust** | Low (user confirms actions) | High (agent decides tool calls) |
| **Mental model** | App has fixed capabilities | "What CAN this agent do?" is unclear |

### Pain Points Specific to Goose Desktop (from code inspection)

**Onboarding (first-run experience)**:
- Provider selection is the gating step — user must understand "what is a provider? what is a model? why do I need an API key?"
- 15+ providers with different auth models (API key, OAuth, local inference)
- Free credits (Tetrate) add financial confusion
- No orientation on "what is an AI agent" or "what can goose do for me"

**Chat Input (dense affordance space)**:
- File attach, microphone, directory selector, mode selector (normal/code/debug), model selector, extension toggle
- Recipe icon (ChefHat) — powerful feature, opaque concept
- Extension toggle — user must understand MCP ecosystem to use meaningfully

**Trust & Safety**:
- Every tool call requires trust judgment — user sees "Agent wants to run: `rm -rf /`" but may not understand implications
- Mode system (normal/code/debug/adversary) changes agent behavior — user may not understand mode consequences
- Recipe trust dialog — user asked to "trust and execute" without understanding YAML

**Desktop-Specific Factors**:
- Working directory selection
- File system navigation via chat (agent reads/writes files)
- Multiple sessions with context windows
- Window/navigation sidebar with many views (Sessions, Settings, Extensions, Recipes, Skills, Apps, Schedules)
- System tray, updates, diagnostics

---

## 3. Novice User Personas

### Persona A: "The Task Delegator" (Non-Technical Professional)
- **Background**: Uses ChatGPT/Gemini, not technical
- **Mental model**: "Like ChatGPT, but on my computer"
- **Expects**: Conversational interaction, human-like reasoning
- **Blind spots**: Doesn't understand tool vs. model, MCP/extensions, context windows
- **Failure mode**: Gives sensitive task → agent runs shell commands → user panics
- **Onboarding friction**: Provider selection is confusing (API keys? OAuth? what's a provider?)

### Persona B: "The Curious Explorer" (Tech-Adjacent, Not Developer)
- **Background**: IT support, data analyst, power user
- **Mental model**: "A smarter Siri that can do things"
- **Expects**: To ask and receive, minimal configuration
- **Blind spots**: Does not understand providers, model selection, context limits
- **Failure mode**: Stuck at onboarding (provider selection), gives up
- **Onboarding friction**: 15 provider options with different auth flows

### Persona C: "The Power Beginner" (Developer, First Time With Agents)
- **Background**: Software developer, uses Copilot for code
- **Mental model**: "A coding assistant on steroids that can do anything"
- **Expects**: Technical output, file manipulation, git operations
- **Blind spots**: Over-trusts agent, doesn't review code changes
- **Failure mode**: Agent makes destructive changes without user review
- **Onboarding friction**: Wants to configure immediately, skips orientation

---

## 4. Stress Conditions

Conditions designed to reveal agent-specific failure modes:

1. **Context window overflow**: 50+ turn conversation → ask agent to recall early detail
2. **Error recovery chain**: Multi-step task → inject mid-task failure → observe user-agent recovery
3. **Trust traps**: Dangerous operation (delete files, install packages) → observe if user reviews
4. **Extension confusion**: User must "add a tool" → observe how they navigate extension system
5. **Multi-session context**: Start task A → switch to session B → return to A → observe continuity
6. **Ambiguous requests**: Intentionally vague instruction → observe iteration/refinement pattern
7. **Provider failure**: Simulate provider unreachable → observe error recovery strategy

---

## 5. Metrics Framework

### Quantitative
| Metric | Instrument | When |
|--------|-----------|------|
| Task Success Rate (TSR) | Observation | Each task |
| Time-on-Task (ToT) | Screen recording | Each task |
| Error Frequency | Observation coding | Throughout |
| NASA-TLX (6 dimensions) | Post-task survey | After each scenario |
| System Usability Scale (SUS) | Post-test survey | End of test |

### Qualitative
| Measure | Method |
|---------|--------|
| Trust Calibration Index | Ratio: approved dangerous ops to rejected safe ops |
| Mental Model Accuracy | Post-test interview on agent capabilities |
| Affective Response | Frustration markers, surprise, delight (coded from video) |
| Feature Discovery | Did user discover features unprompted? |

### Agent-Specific Metrics
- Tool call approval rate
- Escalation frequency (asks for help)
- Redundant specification rate (over-specifies because doesn't trust)
- Rephrasing ratio (how many times user rewords request)

---

## 6. Approaches Comparison

| Approach | Pros | Cons | Effort |
|----------|------|------|--------|
| **A: Expert Cognitive Walkthrough** | Fast (1-2 days), cheap, catches obvious issues | Misses real user behavior, expert bias | Low |
| **B: Full User Test (recommended)** | Valid data, real mental models, high confidence | Recruitment, scheduling, 2-3 weeks | High |
| **C: In-App Telemetry** | Continuous data, large sample | Privacy concerns, no qualitative insight, needs code changes | Medium |
| **D: Remote Unmoderated** | Larger sample, async, cheaper | No think-aloud, lower quality data | Medium |

### Recommendation: Hybrid (A + B)

1. **Phase 1 — Expert Review** (1 week): 2-3 experts evaluate onboarding + 3 core flows using agent-specific heuristic checklist
2. **Phase 2 — User Test** (3-4 weeks): 2 rounds of 8 novice users each, guided scenario set with embedded stress conditions, think-aloud protocol, NASA-TLX + SUS

Rationale: Agent interfaces are too novel for expert-only evaluation to capture real mental models, but expert pre-screening removes critical blockers before user sessions.

---

## 7. Risks & Gaps

| Risk | Severity | Mitigation |
|------|----------|------------|
| Recruitment difficulty (true novices) | High | Broaden criteria: "no agent framework experience," allow ChatGPT consumers |
| Safety liability during tests | High | Sandboxed test environment (test machine, no real credentials) |
| Stress conditions may overwhelm | Medium | Pilot test first, have abort criteria |
| No built-in usability telemetry | Medium | Human annotation of recordings (time-intensive) |
| Scope creep into feature requests | Medium | Strict report scope: usability findings only, not UX design |

### Gaps Identified
- No existing Goose Desktop user research or usability data found
- No built-in interaction telemetry
- No heuristic checklist for agent-specific interfaces
- Sandboxed build of Goose Desktop does not appear to exist yet for testing purposes

---

## 8. Affected Areas (Goose Desktop Codebase)

- `ui/desktop/src/components/onboarding/OnboardingGuard.tsx` — First-run experience, provider selection
- `ui/desktop/src/components/onboarding/ProviderSelector.tsx` — Provider choice UI
- `ui/desktop/src/components/ChatInput.tsx` — Primary interaction point, dense affordance space
- `ui/desktop/src/components/BaseChat.tsx` — Core chat session UX
- `ui/desktop/src/components/Hub.tsx` — Main landing/navigation
- `ui/desktop/src/components/extensions/` — Extension management UI
- `ui/desktop/src/components/recipes/` — Recipe trust/execution UX
- `ui/desktop/src/components/settings/` — All settings views
- `ui/desktop/src/components/GooseSidebar/` — Navigation sidebar
- `crates/goose/src/agents/agent.rs` — Agent loop (error recovery, tool calls)
- `crates/goose-server/src/main.rs` — Server process management

---

## 9. Deliverable Structure (for Proposal Phase)

The proposal phase should define:

1. **Test Plan**: Objectives, methodology, participant criteria, scenarios, schedule, roles
2. **Scenario Scripts**: 6-8 guided tasks with built-in stress conditions
3. **Consent Form**: Agent-specific disclosures (file system access, command execution, recording)
4. **Pre-Test Questionnaire**: Demographics, AI familiarity, expectations
5. **Post-Test Questionnaire**: NASA-TLX, SUS, mental model probe
6. **Observation Template**: Structured notetaking per category scheme
7. **Analysis Template**: Coding scheme, severity ratings, theme clustering
8. **Report Template**: Executive summary, methodology, findings (per category), severity ratings, recommendations

---

**Status**: success
**Summary**: Exploration of Goose Desktop usability/stress test for novice agent users completed. Identified 4 unique challenge categories, 3 user personas, 7 stress conditions, 4 methodology approaches with clear recommendation, and full deliverable structure.
**Artifacts**: Engram `sdd/goose-desktop-usability-test/explore` | `openspec/changes/goose-desktop-usability-test/exploration.md`
**Next**: sdd-propose
**Risks**: Recruitment of true novices, safety sandbox requirements, no existing telemetry
**Skill Resolution**: fallback-registry — loaded skills via `.atl/skill-registry.md` from yaml-agno project. No exploration-specific skills found beyond sdd-explore itself.
