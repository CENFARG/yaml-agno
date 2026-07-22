"""Unit tests for ``YamlAgentOS.__init__`` resolution rules (SPEC_06 slice A).

Covers Scenarios 1, 2, 3, 8, 9 of the slice-A spec: dual agent source
(pre-built list vs YAML config path), the ambiguous-call rejection, the
``authorization=False`` slice-A default, and ``**agentos_kwargs`` pass-through.

Verified Agno 2.6.22 behavior: ``AgentOS(agents=[...], authorization=False)``
instantiates cleanly; ``.authorization`` reflects the forwarded value.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agno.agent import Agent
from agno.os import AgentOS
from pydantic import ValidationError

from yaml_agno.api.app import YamlAgentOS

pytestmark = pytest.mark.unit


def _build_test_agent(name: str = "test-agent") -> Agent:
    """Build a minimal real agno.Agent for test fixtures."""
    return Agent(name=name, model="openai:gpt-4o")


class TestYamlAgentOSInit:
    """RED→GREEN tests for the ``YamlAgentOS`` constructor resolution rules."""

    def test_init_accepts_prebuilt_agents(self) -> None:
        """Scenario 1: ``agents=[...]`` is forwarded unchanged to the parent."""
        agent = _build_test_agent(name="forwarded-agent")

        os_app = YamlAgentOS(agents=[agent])

        assert isinstance(os_app, AgentOS)
        assert os_app.agents is not None
        assert len(os_app.agents) == 1
        assert os_app.agents[0] is agent

    def test_init_builds_agents_from_config_path(self, tmp_path: Path) -> None:
        """Scenario 2: ``config_path=`` loads YAML, validates, and builds agents."""
        yaml_file = tmp_path / "agents.yaml"
        yaml_file.write_text(
            """
- name: yaml-agent-1
  model: openai:gpt-4o
  instructions: Be helpful
- name: yaml-agent-2
  model: openai:gpt-4o
            """.strip(),
            encoding="utf-8",
        )

        os_app = YamlAgentOS(config_path=str(yaml_file))

        assert isinstance(os_app, AgentOS)
        assert os_app.agents is not None
        names = sorted(a.name for a in os_app.agents)
        assert names == ["yaml-agent-1", "yaml-agent-2"]

    def test_init_rejects_both_agents_and_config_path(self, tmp_path: Path) -> None:
        """Scenario 3: passing both sources is ambiguous and raises ValueError."""
        yaml_file = tmp_path / "agents.yaml"
        yaml_file.write_text(
            "- name: x\n  model: openai:gpt-4o\n", encoding="utf-8"
        )
        agent = _build_test_agent()

        with pytest.raises(ValueError, match=r"ambiguous|both"):
            YamlAgentOS(agents=[agent], config_path=str(yaml_file))

    def test_init_default_authorization_false(self) -> None:
        """Scenario 8: the slice-A default for authorization is False.

        Agno's ``AgentOS`` requires at least one agent source, so the smallest
        valid call still provides ``agents=[...]``. The authorization default is
        what slice A is asserting here.
        """
        agent = _build_test_agent()
        os_app = YamlAgentOS(agents=[agent])

        assert os_app.authorization is False

    def test_init_forwards_authorization_true(self) -> None:
        """Scenario 8: explicit ``authorization=True`` is forwarded to the parent."""
        agent = _build_test_agent()
        os_app = YamlAgentOS(agents=[agent], authorization=True)

        assert os_app.authorization is True

    def test_init_forwards_extra_agentos_kwargs(self) -> None:
        """Scenario 9: ``**agentos_kwargs`` are forwarded to ``super().__init__``."""
        agent = _build_test_agent()
        os_app = YamlAgentOS(agents=[agent], enable_mcp_server=True, telemetry=False)

        assert os_app.enable_mcp_server is True
        assert os_app.telemetry is False

    def test_init_invalid_yaml_entry_raises_validation_error(
        self, tmp_path: Path
    ) -> None:
        """Scenario 2 (negative): an invalid YAML entry raises ValidationError, not silently skipped."""
        yaml_file = tmp_path / "agents.yaml"
        # Missing required ``model`` field — AgentConfig validation fails.
        yaml_file.write_text("- name: bad-agent\n", encoding="utf-8")

        with pytest.raises(ValidationError):
            YamlAgentOS(config_path=str(yaml_file))
