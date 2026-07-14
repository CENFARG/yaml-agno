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
        # NOTE: skills is now owned by SPEC_30 slice B (TestAgentFactorySkillsWiring)
        # and is not part of this opaque-slots test.
        assert result.tools == []  # cfg had [{"name": "tool1"}] -> ignored
        assert result.knowledge is None  # cfg had {"db": "pg"} -> ignored
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


class TestAgentFactoryToolCallLimit:
    """RED→GREEN tests for SPEC_11 slice D: tool_call_limit forwarding (R5)."""

    def test_agent_factory_forwards_tool_call_limit(self) -> None:
        """Slice D R5: build(cfg with tool_call_limit=10) -> Agent.tool_call_limit == 10.

        Req: tool_call_limit reenviado (GOLDEN).
        """
        cfg = AgentConfig(name="t", model="openai:gpt-4o", tool_call_limit=10)
        result = AgentFactory.build(cfg)
        assert isinstance(result, Agent)
        assert result.tool_call_limit == 10

    def test_agent_factory_tool_call_limit_none_omitted(self) -> None:
        """Slice D R5: build(cfg without tool_call_limit) -> Agent.tool_call_limit is None.

        Req: tool_call_limit=None (default, Agent recibe None).
        """
        cfg = AgentConfig(name="t", model="openai:gpt-4o")
        result = AgentFactory.build(cfg)
        assert isinstance(result, Agent)
        assert result.tool_call_limit is None


class TestAgentFactorySkillsWiring:
    """RED→GREEN tests for SPEC_30 slice B: ``build(cfg)`` skills forwarding.

    When ``cfg.skills`` is non-None, the factory builds a ``Skills`` instance
    via ``SkillsFactory.build`` and forwards it to ``Agent(skills=...)``. When
    ``cfg.skills is None``, behavior is unchanged (``agent.skills is None``).

    Contract tests (R-sysprompt, R-tools): real ``SKILL.md`` fixtures in
    ``tmp_path`` exercise Agno's system-prompt snippet injector and access-tool
    exposer end-to-end. No Agno mocks.
    """

    @staticmethod
    def _write_valid_skill(skill_dir, name="my-skill"):
        """Write a structurally valid ``SKILL.md`` (lowercase, hyphenated name).

        Mirrors the helper in ``tests/unit/skills/test_skills_factory.py`` so
        Agno's ``validate_skill_directory`` passes when ``validate=True``.
        """
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            f"name: {name}\n"
            "description: A test skill.\n"
            "---\n"
            "# My Skill\n"
            "Instructions here.\n",
            encoding="utf-8",
        )

    def test_build_forwards_skills_when_present(self, tmp_path) -> None:
        """Slice B golden: build(cfg with skills) -> agent.skills is a Skills instance.

        Req R-fwd: AgentFactory.build cablea cfg.skills hacia SkillsFactory.build.
        """
        from agno.skills import Skills

        self._write_valid_skill(tmp_path / "my-skill")
        cfg = AgentConfig(
            name="agent-skills",
            model="openai:gpt-4o",
            skills={"path": str(tmp_path), "validate": True},
        )
        result = AgentFactory.build(cfg)
        assert isinstance(result, Agent)
        assert isinstance(result.skills, Skills)

    def test_build_without_skills_keeps_agent_skills_none(self) -> None:
        """Slice B backward-compat: build(cfg without skills) -> agent.skills is None.

        Req R-none: None forwarding produces Agent(skills=None).
        """
        cfg = AgentConfig(name="agent-no-skills", model="openai:gpt-4o")
        result = AgentFactory.build(cfg)
        assert isinstance(result, Agent)
        assert result.skills is None

    def test_build_skills_injects_system_prompt_snippet(self, tmp_path) -> None:
        """Slice B contract (R-sysprompt): agent.skills.get_system_prompt_snippet()
        returns a non-empty XML block (the ``<skills_system>`` injection).
        """
        self._write_valid_skill(tmp_path / "my-skill")
        cfg = AgentConfig(
            name="agent-snippet",
            model="openai:gpt-4o",
            skills={"path": str(tmp_path), "validate": True},
        )
        result = AgentFactory.build(cfg)
        assert result.skills is not None
        snippet = result.skills.get_system_prompt_snippet()
        assert isinstance(snippet, str)
        assert snippet.strip() != ""

    def test_build_skills_exposes_three_access_tools(self, tmp_path) -> None:
        """Slice B contract (R-tools): agent.skills.get_tools() returns the
        three Agno access tools (instructions, reference, script) as Function
        objects.
        """
        from agno.tools.function import Function

        self._write_valid_skill(tmp_path / "my-skill")
        cfg = AgentConfig(
            name="agent-tools",
            model="openai:gpt-4o",
            skills={"path": str(tmp_path), "validate": True},
        )
        result = AgentFactory.build(cfg)
        assert result.skills is not None
        tools = result.skills.get_tools()
        assert len(tools) == 3
        assert all(isinstance(t, Function) for t in tools)
        tool_names = {t.name for t in tools}
        assert tool_names == {
            "get_skill_instructions",
            "get_skill_reference",
            "get_skill_script",
        }

    def test_build_skills_propagates_invalid_skill_error(self, tmp_path) -> None:
        """Slice B error propagation (R-err): an invalid skill dir (BadName
        uppercase) with validate=True propagates SkillValidationError from the
        factory.
        """
        from agno.skills import SkillValidationError

        self._write_valid_skill(tmp_path / "BadName", name="BadName")
        cfg = AgentConfig(
            name="agent-bad",
            model="openai:gpt-4o",
            skills={"path": str(tmp_path), "validate": True},
        )
        with pytest.raises(SkillValidationError):
            AgentFactory.build(cfg)
