# Skill Registry — yaml-agno

Generated: 2026-07-06 (refreshed by sdd-init)
Scope: project (yaml-agno) — `C:\Dropbox\DOC.RECA\06-Software\yaml-agno`
Artifact store: HYBRID (engram project=`doc.reca` + `openspec/` files)

## Project Context (resolved by sdd-init)

| Field | Value |
|-------|-------|
| Project name | yaml-agno (pip: `yaml_agno`) |
| Type | Python 3.12+ pip-installable library |
| Framework | Agno v2.6.18 (pip dep, not vendored) |
| Core dep | core-cenf-py (`core_infrastructure`, pip dep, not vendored) |
| Test runner | `python -m pytest` + pytest-asyncio |
| Linter / formatter | ruff |
| Type checker | mypy |
| Coverage target | 100% |
| Strict TDD | **enabled** (RED-GREEN-REFACTOR enforced) |
| Test command | `python -m pytest` |
| Build command | none (pure pip library; pyproject.toml created by first /sdd-new) |
| Artifact store mode | hybrid |
| Engram project key | `doc.reca` |
| sdd-init topic key | `sdd-init/doc.reca` |

### Test markers (planned)
`unit`, `integration`, `e2e`, `slow`, `fast`, `guardrails` — tests under `tests/`.

### Conventions
- Code / docstrings / comments / identifiers: **English**
- Conversation / persona: Spanish (Rioplatense) — user-facing replies only
- YAML-first philosophy (~70% YAML, ~30% Python)
- Build ON TOP of Agno — never reimplement runtime/session/memory/A2A/retry
- Agent = black box with contract (mission + I/O schema + deps)
- Agno API parity: sync AND async public methods, no agents in loops,
  param names identical to Agno

---

## Available User Skills (non-SDD)

25 SKILL.md files indexed from `~/.claude/skills`.

### Code Review & Quality
| Skill | Trigger | Path |
|-------|---------|------|
| judgment-day | dual review, adversarial review, juzgar | `~/.claude/skills/judgment-day/SKILL.md` |
| comment-writer | PR feedback, issue replies, reviews | `~/.claude/skills/comment-writer/SKILL.md` |
| work-unit-commits | implementation, commit splitting, chained PRs | `~/.claude/skills/work-unit-commits/SKILL.md` |

### Git & GitHub
| Skill | Trigger | Path |
|-------|---------|------|
| branch-pr | creating, opening, preparing PRs | `~/.claude/skills/branch-pr/SKILL.md` |
| chained-pr | PRs over 400 lines, stacked PRs, review slices | `~/.claude/skills/chained-pr/SKILL.md` |
| issue-creation | creating GitHub issues, bug reports | `~/.claude/skills/issue-creation/SKILL.md` |

### Skill Management
| Skill | Trigger | Path |
|-------|---------|------|
| skill-creator | new skills, agent instructions | `~/.claude/skills/skill-creator/SKILL.md` |
| skill-improver | improve skills, audit skills, refactor skills | `~/.claude/skills/skill-improver/SKILL.md` |
| skill-registry | update skills, skill registry | `~/.claude/skills/skill-registry/SKILL.md` |
| find-skills | how do I do X, find a skill for X | `~/.claude/skills/find-skills/SKILL.md` |

### Documentation & Templates
| Skill | Trigger | Path |
|-------|---------|------|
| cognitive-doc-design | writing guides, READMEs, RFCs, onboarding | `~/.claude/skills/cognitive-doc-design/SKILL.md` |
| template-skill | (template for new skills) | `~/.claude/skills/template-skill/SKILL.md` |

### File / Office Formats
| Skill | Trigger | Path |
|-------|---------|------|
| docx | Word documents, .docx generation | `~/.claude/skills/docx/SKILL.md` |
| pdf | PDF reading, generation | `~/.claude/skills/pdf/SKILL.md` |
| pptx | PowerPoint, .pptx generation | `~/.claude/skills/pptx/SKILL.md` |
| xlsx | Excel, .xlsx generation | `~/.claude/skills/xlsx/SKILL.md` |
| xlsx-gr | base contable, CENF contabilidad | `~/.claude/skills/xlsx-gr/SKILL.md` |
| markitdown | markdown conversion | `~/.claude/skills/markitdown/SKILL.md` |

### Domain-Specific / Integrations
| Skill | Trigger | Path |
|-------|---------|------|
| go-testing | Go test patterns (other projects) | `~/.claude/skills/go-testing/SKILL.md` |
| mcp-builder | build MCP servers | `~/.claude/skills/mcp-builder/SKILL.md` |
| nvidia | NVIDIA integrations | `~/.claude/skills/nvidia/SKILL.md` |
| web-artifacts-builder | web artifacts | `~/.claude/skills/web-artifacts-builder/SKILL.md` |

---

## SDD Phase Skills

| Skill | Phase | Path |
|-------|-------|------|
| sdd-init | Initialize SDD context | `~/.claude/skills/sdd-init/SKILL.md` |
| sdd-explore | Investigate an idea | `~/.claude/skills/sdd-explore/SKILL.md` |
| sdd-propose | Create change proposal | `~/.claude/skills/sdd-propose/SKILL.md` |
| sdd-spec | Write specifications | `~/.claude/skills/sdd-spec/SKILL.md` |
| sdd-design | Technical design | `~/.claude/skills/sdd-design/SKILL.md` |
| sdd-tasks | Task breakdown | `~/.claude/skills/sdd-tasks/SKILL.md` |
| sdd-apply | Implement tasks (Strict TDD refs inside) | `~/.claude/skills/sdd-apply/SKILL.md` |
| sdd-verify | Validate against specs (Strict TDD refs inside) | `~/.claude/skills/sdd-verify/SKILL.md` |
| sdd-archive | Close a change | `~/.claude/skills/sdd-archive/SKILL.md` |
| sdd-onboard | Guided SDD walkthrough | `~/.claude/skills/sdd-onboard/SKILL.md` |

### Strict TDD references (loaded by sdd-apply / sdd-verify)
- `~/.claude/skills/sdd-apply/strict-tdd.md`
- `~/.claude/skills/sdd-verify/strict-tdd-verify.md`

### Shared SDD conventions (`~/.claude/skills/_shared/`)
| File | Purpose |
|------|---------|
| `sdd-phase-common.md` | boilerplate for every SDD phase |
| `engram-convention.md` | Engram artifact naming |
| `openspec-convention.md` | openspec layout and rules |
| `persistence-contract.md` | read/write rules per mode |
| `skill-resolver.md` | orchestrator skill resolution protocol |
| `SKILL.md` | shared skill entry |

---

## Resolver Notes for Sub-Agents

- **Python library work** (pydantic models, factories, YAML loaders):
  inject `work-unit-commits` + `judgment-day` (review) + relevant SDD phase skill.
- **PR / commit work**: inject `branch-pr` (single PR) or `chained-pr` (>400 lines)
  + `work-unit-commits`.
- **Agno integration**: there is NO standalone `agno` or `core-cenf-py` skill;
  rely on the project's own `specs/` SPECs and `DECISIONES.md` for Agno conventions
  (sync/async parity, no agents in loops, param names identical to Agno).
- **Strict TDD is active**: every `sdd-apply` / `sdd-verify` launch MUST receive
  the Strict TDD instruction (see orchestrator protocol) and load
  `sdd-apply/strict-tdd.md`.
