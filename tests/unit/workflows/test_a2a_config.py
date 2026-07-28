"""RED tests for A2AConfig (SPEC_05 Slice D).

Strict TDD — these tests are written BEFORE the implementation exists.
Coverage: parse enable_interface + expose entries, parse remote entries,
reject non-a2a protocols, and verify the factory maps to Agno BaseRemote.

Tagged ``@pytest.mark.unit``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Task 3.1 — parse enable_interface and expose entries
# ---------------------------------------------------------------------------


def test_parse_enable_interface_and_expose() -> None:
    """Parse A2A YAML block: enable_interface=True + expose[kind=team,ref=validator_team].

    Scenario: parse enable_interface and expose.
    """
    from yaml_agno.workflows.a2a_config import A2AConfig, A2AExposedEntry

    data = {
        "enable_interface": True,
        "expose": [
            {"kind": "team", "ref": "validator_team"},
            {"kind": "agent", "ref": "chat_agent", "description": "Public chat agent"},
        ],
    }

    cfg = A2AConfig(**data)

    assert cfg.enable_interface is True
    assert len(cfg.expose) == 2

    first = cfg.expose[0]
    assert isinstance(first, A2AExposedEntry)
    assert first.kind == "team"
    assert first.ref == "validator_team"
    assert first.description is None

    second = cfg.expose[1]
    assert second.kind == "agent"
    assert second.ref == "chat_agent"
    assert second.description == "Public chat agent"


def test_parse_expose_workflow_kind() -> None:
    """Expose entry with kind=workflow is accepted."""
    from yaml_agno.workflows.a2a_config import A2AConfig

    data = {
        "enable_interface": False,
        "expose": [{"kind": "workflow", "ref": "pipeline_x"}],
    }
    cfg = A2AConfig(**data)
    assert cfg.expose[0].kind == "workflow"


def test_parse_expose_defaults() -> None:
    """enable_interface defaults to False, expose defaults to empty list."""
    from yaml_agno.workflows.a2a_config import A2AConfig

    cfg = A2AConfig()
    assert cfg.enable_interface is False
    assert cfg.expose == []
    assert cfg.remote == []


def test_parse_expose_invalid_kind() -> None:
    """kind=service raises ValidationError."""
    from yaml_agno.workflows.a2a_config import A2AConfig

    with pytest.raises(ValidationError):
        A2AConfig(
            enable_interface=True,
            expose=[{"kind": "service", "ref": "s1"}],
        )


# ---------------------------------------------------------------------------
# Task 3.2 — parse remote endpoints
# ---------------------------------------------------------------------------


def test_parse_remote_endpoints() -> None:
    """Parse remote entries: name, kind, endpoint, protocol=a2a.

    Scenario: parse remote endpoints.
    """
    from yaml_agno.workflows.a2a_config import A2AConfig, A2ARemoteEntry

    data = {
        "remote": [
            {
                "name": "r1",
                "kind": "team",
                "endpoint": "https://x.example.com",
                "protocol": "a2a",
            },
            {
                "name": "r2",
                "kind": "agent",
                "endpoint": "https://y.example.com",
                "protocol": "a2a",
            },
        ],
    }

    cfg = A2AConfig(**data)

    assert len(cfg.remote) == 2

    first = cfg.remote[0]
    assert isinstance(first, A2ARemoteEntry)
    assert first.name == "r1"
    assert first.kind == "team"
    assert first.endpoint == "https://x.example.com"
    assert first.protocol == "a2a"

    second = cfg.remote[1]
    assert second.name == "r2"
    assert second.kind == "agent"
    assert second.endpoint == "https://y.example.com"
    assert second.protocol == "a2a"


def test_parse_remote_workflow_kind() -> None:
    """Remote entry with kind=workflow is accepted."""
    from yaml_agno.workflows.a2a_config import A2AConfig

    data = {
        "remote": [
            {
                "name": "wf1",
                "kind": "workflow",
                "endpoint": "https://w.example.com",
                "protocol": "a2a",
            },
        ],
    }
    cfg = A2AConfig(**data)
    assert cfg.remote[0].kind == "workflow"


def test_parse_remote_default_protocol_a2a() -> None:
    """protocol defaults to 'a2a' when omitted."""
    from yaml_agno.workflows.a2a_config import A2AConfig

    cfg = A2AConfig(
        remote=[{"name": "r1", "kind": "team", "endpoint": "https://x.example.com"}]
    )
    assert cfg.remote[0].protocol == "a2a"


def test_parse_remote_invalid_kind() -> None:
    """kind=service raises ValidationError."""
    from yaml_agno.workflows.a2a_config import A2AConfig

    with pytest.raises(ValidationError):
        A2AConfig(
            remote=[
                {"name": "r1", "kind": "service", "endpoint": "https://x.example.com"}
            ]
        )


# ---------------------------------------------------------------------------
# Task 3.3 — reject non-a2a protocols
# ---------------------------------------------------------------------------


def test_acp_protocol_rejected() -> None:
    """protocol=acp raises ValidationError.

    Scenario: ACP protocol rejected.
    """
    from yaml_agno.workflows.a2a_config import A2AConfig

    with pytest.raises(ValidationError):
        A2AConfig(
            remote=[
                {
                    "name": "r1",
                    "kind": "team",
                    "endpoint": "https://x.example.com",
                    "protocol": "acp",
                }
            ]
        )


# ---------------------------------------------------------------------------
# Task 3.4 — factory maps to Agno BaseRemote
# ---------------------------------------------------------------------------


def test_factory_maps_to_agno_baseremote() -> None:
    """A2AConfigFactory.build() produces Agno BaseRemote instances.

    Each remote entry → BaseRemote(base_url=endpoint, protocol="a2a").
    """
    from agno.remote import BaseRemote

    from yaml_agno.workflows.a2a_config import A2AConfig, A2AConfigFactory

    cfg = A2AConfig(
        remote=[
            {"name": "r1", "kind": "team", "endpoint": "https://team.example.com"},
            {"name": "r2", "kind": "agent", "endpoint": "https://agent.example.com"},
            {"name": "r3", "kind": "workflow", "endpoint": "https://wf.example.com"},
        ]
    )

    factory = A2AConfigFactory()
    remotes = factory.build(cfg)

    assert len(remotes) == 3
    for r in remotes:
        assert isinstance(r, BaseRemote)
        assert r.protocol == "a2a"

    assert remotes[0].base_url == "https://team.example.com"
    assert remotes[1].base_url == "https://agent.example.com"
    assert remotes[2].base_url == "https://wf.example.com"


def test_factory_empty_remote_returns_empty_list() -> None:
    """No remote entries → empty list."""
    from yaml_agno.workflows.a2a_config import A2AConfig, A2AConfigFactory

    cfg = A2AConfig()  # no remote entries
    factory = A2AConfigFactory()
    assert factory.build(cfg) == []
