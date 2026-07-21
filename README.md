# yaml-agno

Declarative YAML-driven agent orchestration built on top of [Agno](https://github.com/agno-agi/agno).
`yaml-agno` lets you define agents, teams, workflows, tools, memory, knowledge,
guardrails and human-in-the-loop interactions as data (YAML) rather than code,
while delegating runtime concerns to Agno's AgentOS. The project is currently in
**Pre-Alpha**: this repository ships the installable package skeleton (21
canonical empty namespaces) plus CI; business capabilities defined in the 34
SPECs land incrementally.

## Install (development)

Requires Python 3.12 or 3.13.

```bash
pip install -e ".[dev]"
```

> **Note:** `core-cenf-py` is a private GitHub repository
> (`CENFARG/core-cenf-py`). The editable install resolves it via
> `git+https://github.com/CENFARG/core-cenf-py.git@v0.1.0`, so your environment
> must have authenticated git access to that repo. In GitHub Actions, this is
> handled by the `GIT_AUTH_TOKEN` secret (see `.github/workflows/ci.yml`).

## Verify

```bash
python -c "import yaml_agno; print(yaml_agno.__version__)"  # 0.1.0
pytest
ruff check .
mypy src/yaml_agno
```

## License

MIT
