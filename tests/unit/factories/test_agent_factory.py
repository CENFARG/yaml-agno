"""Unit tests for ``AgentFactory.build`` — SPEC_01 slice #1.

Covers the 13 scenarios of
``openspec/changes/agent-factory-basic/specs/agent-factory-basic/spec.md``:

    - GREEN instancia válida desde config mínima
    - GREEN mapeo de los 4 campos de identidad
    - GREEN name+model minimal
    - GREEN identidad completa
    - GREEN model resuelto a ``Model`` (id/provider) por Agno
    - GREEN slots opacos tolerados (no rompen construcción)
    - EDGE los 9 slots opacos + tags + metadata poblados simultáneamente
    - GREEN ``build()`` no invoca ``run()`` ni ``arun()``
    - GREEN idempotencia (dos agents equivalentes, no la misma instancia)
    - GREEN ``instructions=None`` válido
    - RED delegación de validación a SPEC_02 (Pydantic ValidationError)
    - GREEN import desde el paquete raíz
    - GREEN colección con marker ``@pytest.mark.unit``

Verified Agno behavior (Agno 2.6.22): ``Agent(model="openai:gpt-4o").model`` is a
``Model`` instance (e.g. ``OpenAIResponses``) with ``.id`` and ``.provider``
attributes — NOT the raw string. The factory does model passthrough; Agno resolves.
"""

import pytest
from agno.agent import Agent
from agno.models.base import Model
from pydantic import ValidationError

from yaml_agno.factories import AgentFactory
from yaml_agno.models.config.agent_config import AgentConfig

pytestmark = pytest.mark.unit


class TestAgentFactoryBuild:
    """RED→GREEN tests for ``AgentFactory.build(cfg) -> agno.Agent``."""

    def test_build_returns_agno_agent_instance(self) -> None:
        """Scenario: GREEN — Instancia válida retornada desde config mínima.

        ``build(AgentConfig(name, model))`` returns an ``agno.Agent`` instance.
        """
        cfg = AgentConfig(name="agent-01", model="openai:gpt-4o")
        result = AgentFactory.build(cfg)
        assert isinstance(result, Agent)

    def test_build_maps_all_four_identity_fields(self) -> None:
        """Scenario: GREEN — El retorno mapea los cuatro campos de identidad.

        name, instructions, description map directly; model is resolved by Agno
        to a ``Model`` instance.
        """
        cfg = AgentConfig(
            name="agent-01",
            model="openai:gpt-4o",
            instructions="Sé útil",
            description="A test agent",
        )
        result = AgentFactory.build(cfg)
        assert result.name == cfg.name
        assert result.instructions == cfg.instructions
        assert result.description == cfg.description
        assert isinstance(result.model, Model)

    def test_build_minimal_config_maps_name_and_model(self) -> None:
        """Scenario: GREEN — Config mínima mapea name y model.

        ``result.name == "my-agent"`` and ``result.model.id == "gpt-4o"``.
        """
        cfg = AgentConfig(name="my-agent", model="openai:gpt-4o")
        result = AgentFactory.build(cfg)
        assert result.name == "my-agent"
        assert result.model.id == "gpt-4o"

    def test_build_full_identity_no_translation(self) -> None:
        """Scenario: GREEN — Identidad completa mapea los cuatro campos.

        Each of the 4 mapped fields equals the cfg value without transformation.
        """
        cfg = AgentConfig(
            name="a",
            model="openai:gpt-4o",
            instructions="Sé útil",
            description="d",
        )
        result = AgentFactory.build(cfg)
        assert result.name == "a"
        assert result.instructions == "Sé útil"
        assert result.description == "d"
        assert result.model.id == "gpt-4o"

    def test_build_model_is_model_instance_with_id_and_provider(self) -> None:
        """Scenario: GREEN — ``agent.model`` es una instancia de ``Model``.

        Agno resolves the ``provider:id`` string to a ``Model`` instance in the
        constructor. The factory passes the string through; Agno resolves.
        """
        cfg = AgentConfig(name="x", model="openai:gpt-4o")
        result = AgentFactory.build(cfg)
        assert isinstance(result.model, Model)
        assert result.model.id == "gpt-4o"
        assert result.model.provider == "OpenAI"

    def test_build_tolerates_opaque_slots_present(self) -> None:
        """Scenario: GREEN — Slots opacos presentes no rompen la construcción.

        ``memory`` and ``tools`` populated do not raise; they are ignored.
        """
        cfg = AgentConfig(
            name="a1",
            model="openai:gpt-4o",
            memory={"driver": "sqlite"},
            tools=[{"name": "t"}],
        )
        result = AgentFactory.build(cfg)
        assert isinstance(result, Agent)

    def test_build_all_opaque_slots_tags_metadata_populated(self) -> None:
        """Scenario: EDGE — Todos los slots opacos poblados simultáneamente.

        The 9 opaque slots + tags + metadata populated; factory ignores all 11
        and returns a valid ``agno.Agent``.
        """
        cfg = AgentConfig(
            name="a1",
            model="openai:gpt-4o",
            tools=[{"name": "tool1"}],
            knowledge={"db": "pg"},
            memory={"backends": ["db"]},
            session={"storage": "sqlite"},
            reasoning={"effort": "high"},
            skills={"list": ["s1"]},
            human_review={"enabled": True},
            culture={"locale": "es-AR"},
            persistence={"mode": "auto"},
            tags=["prod", "eu"],
            metadata={"owner": "team-foo"},
        )
        result = AgentFactory.build(cfg)
        assert isinstance(result, Agent)
        # Non-forwarding: the factory MUST NOT pass opaque slots/tags/metadata
        # to Agent(). For attributes Agent exposes, assert they hold Agno's
        # DEFAULTS, not the populated cfg values (proves they were ignored).
        assert result.tools == []  # cfg had [{"name": "tool1"}] -> ignored
        assert result.knowledge is None  # cfg had {"db": "pg"} -> ignored
        assert result.skills is None  # cfg had {"list": ["s1"]} -> ignored
        assert result.metadata is None  # cfg had {"owner": "team-foo"} -> ignored

    def test_build_does_not_invoke_run_or_arun(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Scenario: GREEN — ``build()`` no invoca ``run()`` ni ``arun()``.

        Construction is pure field mapping; neither ``run`` nor ``arun`` is called.
        """
        run_calls: list[str] = []
        arun_calls: list[str] = []

        def _spy_run(self: Agent, *args: object, **kwargs: object) -> object:
            run_calls.append("run")
            raise AssertionError("Agent.run must not be called during build()")

        async def _spy_arun(self: Agent, *args: object, **kwargs: object) -> object:
            arun_calls.append("arun")
            raise AssertionError("Agent.arun must not be called during build()")

        monkeypatch.setattr(Agent, "run", _spy_run, raising=False)
        monkeypatch.setattr(Agent, "arun", _spy_arun, raising=False)

        cfg = AgentConfig(name="x", model="openai:gpt-4o")
        AgentFactory.build(cfg)

        assert run_calls == []
        assert arun_calls == []

    def test_build_is_idempotent_on_equal_configs(self) -> None:
        """Scenario: GREEN — Dos llamadas producen agents equivalentes.

        Two ``build()`` calls on structurally-equal configs produce distinct
        instances with equal identity attributes (same ``Model`` type + same id).
        """
        cfg_a = AgentConfig(name="dup", model="openai:gpt-4o", instructions="hi")
        cfg_b = AgentConfig(name="dup", model="openai:gpt-4o", instructions="hi")
        agent_a = AgentFactory.build(cfg_a)
        agent_b = AgentFactory.build(cfg_b)
        assert agent_a is not agent_b
        assert agent_a.name == agent_b.name
        assert type(agent_a.model) is type(agent_b.model)
        assert agent_a.model.id == agent_b.model.id

    def test_build_accepts_instructions_none(self) -> None:
        """Scenario: GREEN — Config con ``instructions=None``.

        ``Agent(instructions=None)`` is the Agno default; factory passes it through.
        """
        cfg = AgentConfig(name="x", model="openai:gpt-4o", instructions=None)
        result = AgentFactory.build(cfg)
        assert isinstance(result, Agent)
        assert result.instructions is None

    def test_invalid_agent_config_raises_before_build(self) -> None:
        """Scenario: RED — La fábrica delega validación a SPEC_02.

        An invalid ``AgentConfig`` (empty name + bad model) raises Pydantic
        ``ValidationError`` at construction, before ``build()`` is ever reached.
        """
        with pytest.raises(ValidationError):
            AgentConfig(name="", model="bad")  # type: ignore[arg-type]


class TestAgentFactoryImportContract:
    """Scenario: GREEN — Import desde el paquete raíz."""

    def test_agent_factory_importable_from_factories_package(self) -> None:
        """``from yaml_agno.factories import AgentFactory`` succeeds at runtime."""
        from yaml_agno.factories import AgentFactory as Factory

        assert Factory is not None
        assert Factory is AgentFactory

    def test_agent_factory_build_is_callable(self) -> None:
        """``AgentFactory.build`` is callable (static method)."""
        assert callable(AgentFactory.build)


class TestAgentFactoryToolsWiring:
    """RED→GREEN tests for SPEC_11 slice C: ``build(cfg, resolver=None)``.

    When ``resolver`` is provided and ``cfg.tools`` is non-empty, the factory
    builds a ``ToolFactory(resolver)``, resolves the opaque dicts, and forwards
    the result to ``Agent(tools=...)``. When ``resolver is None``, behavior is
    unchanged (``tools=[]``).
    """

    def test_build_forwards_tools_when_resolver(self) -> None:
        """Slice C: build(cfg, resolver) -> Agent.tools non-empty.

        Req: AgentFactory wiring — resolver + tools.
        """
        import importlib
        from typing import Any

        class _RealResolver:
            def resolve_class(self, module_path: str, class_name: str) -> Any:
                module = importlib.import_module(module_path)
                return getattr(module, class_name)

        cfg = AgentConfig(
            name="t",
            model="openai:gpt-4o",
            tools=[{"kind": "builtin", "name": "calculator"}],
        )
        result = AgentFactory.build(cfg, resolver=_RealResolver())  # type: ignore[arg-type]
        assert isinstance(result, Agent)
        assert len(result.tools) == 1
        from agno.tools.calculator import CalculatorTools

        assert isinstance(result.tools[0], CalculatorTools)

    def test_build_without_resolver_keeps_tools_empty(self) -> None:
        """Slice C: build(cfg) without resolver -> agent.tools == [].

        Req: AgentFactory sin resolver — tools=[] (backward compat).
        """
        cfg = AgentConfig(
            name="t",
            model="openai:gpt-4o",
            tools=[{"kind": "builtin", "name": "calculator"}],
        )
        result = AgentFactory.build(cfg)
        assert isinstance(result, Agent)
        assert result.tools == []
