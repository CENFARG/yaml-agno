"""RED tests for WorkflowConfig + StepConfig schemas.

These tests reference ``yaml_agno.models.config.workflow_config.{WorkflowConfig,StepConfig}``
which do NOT exist yet (RED). They cover the spec scenarios for:
    - GREEN workflow creation + type from string "Parallel" -> StepType.PARALLEL
    - RED invalid step type
    - RED duplicate step ids
    - RED dangling if_true / if_false / cases.value references
    - EDGE cases key collision with step_id OK (keys not validated)
    - RED nested steps on invalid type
    - RED condition/router/loop fields on wrong types
    - EDGE finally alias from YAML dict + finally_ from Python kwarg
    - RED max_iterations=0
"""

import pytest
from agno.workflow.types import StepType
from pydantic import ValidationError

from yaml_agno.models.config.workflow_config import StepConfig, WorkflowConfig

pytestmark = pytest.mark.unit


class TestWorkflowConfigGoldenPaths:
    """GREEN scenarios — valid workflows accepted."""

    def test_workflow_config_creation(self) -> None:
        """Minimal valid workflow: name + 1 step."""
        cfg = WorkflowConfig(
            name="wf1",
            steps=[StepConfig(step="s1")],
        )
        assert cfg.name == "wf1"
        assert len(cfg.steps) == 1

    def test_workflow_config_model_config_extra_forbid(self) -> None:
        """WorkflowConfig declares extra='forbid'."""
        assert WorkflowConfig.model_config.get("extra") == "forbid"

    def test_step_config_default_type_is_step(self) -> None:
        """Default step type is StepType.STEP."""
        s = StepConfig(step="s1")
        assert s.type.value == "Step"

    def test_step_config_type_from_string_parallel(self) -> None:
        """type='Parallel' (string) maps to StepType.PARALLEL."""
        s = StepConfig(step="s1", type="Parallel")
        assert s.type.value == "Parallel"

    def test_workflow_config_user_id_absent(self) -> None:
        """user_id is NOT a declared field on WorkflowConfig (SPEC_04)."""
        assert "user_id" not in WorkflowConfig.model_fields


class TestStepTypeRejected:
    """RED scenario — invalid step type rejected."""

    def test_invalid_step_type_rejected(self) -> None:
        """An invalid step type string is rejected (Agno enum)."""
        with pytest.raises(ValidationError):
            StepConfig(step="s1", type="NotAType")


class TestWorkflowStepIdIntegrity:
    """RED scenarios — step id uniqueness + dangling references."""

    def test_duplicate_step_ids_rejected(self) -> None:
        """Two steps with the same step id are rejected."""
        with pytest.raises(ValidationError) as exc:
            WorkflowConfig(
                name="wf1",
                steps=[StepConfig(step="s1"), StepConfig(step="s1")],
            )
        assert "Duplicate step ids" in str(exc.value)

    def test_dangling_if_true_reference_rejected(self) -> None:
        """A Condition step with if_true pointing to a missing step is rejected."""
        with pytest.raises(ValidationError) as exc:
            WorkflowConfig(
                name="wf1",
                steps=[
                    StepConfig(
                        step="c1",
                        type="Condition",
                        condition="x > 0",
                        if_true="missing",
                        if_false="s2",
                    ),
                    StepConfig(step="s2"),
                ],
            )
        assert "non-existent step" in str(exc.value)

    def test_dangling_if_false_reference_rejected(self) -> None:
        """A Condition step with if_false pointing to a missing step is rejected."""
        with pytest.raises(ValidationError) as exc:
            WorkflowConfig(
                name="wf1",
                steps=[
                    StepConfig(
                        step="c1",
                        type="Condition",
                        condition="x > 0",
                        if_true="s2",
                        if_false="missing",
                    ),
                    StepConfig(step="s2"),
                ],
            )
        assert "non-existent step" in str(exc.value)

    def test_dangling_cases_value_reference_rejected(self) -> None:
        """A Router step with a cases VALUE pointing to a missing step is rejected."""
        with pytest.raises(ValidationError) as exc:
            WorkflowConfig(
                name="wf1",
                steps=[
                    StepConfig(
                        step="r1",
                        type="Router",
                        expression="x",
                        cases={"legal_key": "missing_step"},
                    ),
                    StepConfig(step="s2"),
                ],
            )
        assert "non-existent step" in str(exc.value)

    def test_cases_key_collision_with_step_id_ok(self) -> None:
        """EDGE: a cases key that happens to equal a valid step id is OK —
        only values are validated, not keys."""
        cfg = WorkflowConfig(
            name="wf1",
            steps=[
                StepConfig(
                    step="r1",
                    type="Router",
                    expression="x",
                    cases={"s2": "s3"},  # key "s2" is a valid step id, but keys are not validated
                ),
                StepConfig(step="s2"),
                StepConfig(step="s3"),
            ],
        )
        assert cfg.steps[0].cases == {"s2": "s3"}

    def test_valid_condition_references_ok(self) -> None:
        """GREEN: a Condition step referencing existing step ids is accepted."""
        cfg = WorkflowConfig(
            name="wf1",
            steps=[
                StepConfig(
                    step="c1",
                    type="Condition",
                    condition="x > 0",
                    if_true="s2",
                    if_false="s3",
                ),
                StepConfig(step="s2"),
                StepConfig(step="s3"),
            ],
        )
        assert cfg.steps[0].if_true == "s2"


class TestStepTypeSpecificFields:
    """RED scenarios — type-specific fields on incompatible types rejected."""

    def test_nested_steps_on_invalid_type_rejected(self) -> None:
        """steps field only allowed on Parallel/Steps/Condition/Loop."""
        with pytest.raises(ValidationError) as exc:
            StepConfig(step="s1", type="Step", steps=[{"step": "inner"}])
        assert "Nested steps only allowed" in str(exc.value)
        # SPEC_05 slice A: the error message now lists Loop as allowed.
        assert "Loop" in str(exc.value)

    def test_nested_steps_on_parallel_ok(self) -> None:
        """GREEN: steps on Parallel is allowed."""
        s = StepConfig(step="s1", type="Parallel", steps=[{"step": "inner"}])
        assert s.type.value == "Parallel"
        assert len(s.steps) == 1

    def test_condition_fields_on_non_condition_rejected(self) -> None:
        """condition/if_true/if_false only allowed on Condition type."""
        with pytest.raises(ValidationError) as exc:
            StepConfig(step="s1", type="Router", if_true="x")
        assert "only allowed for Condition type" in str(exc.value)

    def test_router_fields_on_non_router_rejected(self) -> None:
        """expression/cases only allowed on Router type."""
        with pytest.raises(ValidationError) as exc:
            StepConfig(step="s1", type="Loop", cases={"k": "v"})
        assert "only allowed for Router type" in str(exc.value)

    def test_loop_fields_on_non_loop_rejected(self) -> None:
        """end_condition/max_iterations only allowed on Loop type."""
        with pytest.raises(ValidationError) as exc:
            StepConfig(step="s1", type="Parallel", max_iterations=5)
        assert "only allowed for Loop type" in str(exc.value)

    def test_router_with_cases_ok(self) -> None:
        """GREEN: Router with expression + cases is accepted (at step level)."""
        s = StepConfig(step="s1", type="Router", expression="x", cases={"a": "b"})
        assert s.type.value == "Router"

    def test_loop_with_iterations_ok(self) -> None:
        """GREEN: Loop with end_condition + max_iterations is accepted."""
        s = StepConfig(
            step="s1", type="Loop", end_condition="done", max_iterations=10
        )
        assert s.type.value == "Loop"
        assert s.max_iterations == 10

    def test_loop_with_body_ok(self) -> None:
        """SPEC_05 slice A: Loop now accepts nested steps."""
        s = StepConfig(
            step="l",
            type="Loop",
            steps=[{"step": "inner", "type": "Step", "agent": "a1"}],
            max_iterations=5,
            end_condition="done == true",
        )
        assert s.type.value == "Loop"
        assert len(s.steps) == 1
        assert s.max_iterations == 5


class TestStepFinallyAlias:
    """EDGE scenarios — finally_ alias works both ways."""

    def test_finally_alias_from_yaml_dict(self) -> None:
        """Constructing via alias key 'finally' (YAML-loaded dict form) populates finally_."""
        s = StepConfig(step="s1", **{"finally": True})
        assert s.finally_ is True

    def test_finally_field_name_from_python(self) -> None:
        """Constructing via Python kwarg finally_ (field name) populates finally_."""
        s = StepConfig(step="s1", finally_=True)
        assert s.finally_ is True

    def test_finally_default_false(self) -> None:
        """finally_ defaults to False."""
        s = StepConfig(step="s1")
        assert s.finally_ is False


class TestStepMaxIterations:
    """RED scenario — max_iterations minimum is 1 (ge=1)."""

    def test_max_iterations_zero_rejected(self) -> None:
        """max_iterations=0 is rejected (must be >= 1)."""
        with pytest.raises(ValidationError):
            StepConfig(step="s1", type="Loop", max_iterations=0)


class TestStepConfigContract:
    """QUALITY-FEEDBACK §Cobertura — congelar el contrato de schema de StepConfig.

    StepConfig es el modelo con mayor fan-in de la librería (54 callers). Estos
    tests congelan su contrato para que cualquier cambio de schema pase por
    revisión explícita de blast-radius (54 usos).
    """

    def test_minimal_step_config_defaults(self) -> None:
        """Scenario: StepConfig mínimo (solo ``step``) → defaults correctos.

        ``type``=Step, ``execute``=True, ``finally_``=False,
        ``description``/``agent``/``team``/``function``/``workflow``=None,
        ``steps``=[] y ``cases``={}.
        """
        s = StepConfig(step="s1")
        assert s.step == "s1"
        assert s.type is StepType.STEP
        assert s.execute is True
        assert s.finally_ is False
        assert s.description is None
        assert s.agent is None
        assert s.team is None
        assert s.function is None
        assert s.workflow is None
        assert s.steps == []
        assert s.cases == {}
        assert s.condition is None
        assert s.if_true is None
        assert s.if_false is None
        assert s.expression is None
        assert s.end_condition is None
        assert s.max_iterations is None
        assert s.human_review is None

    def test_model_dump_roundtrip_identical(self) -> None:
        """Scenario: round-trip ``model_dump()`` → ``StepConfig(**dump)`` idéntico.

        El contrato de serialización YAML: lo que YAML produce y ``model_dump``
        consume debe reconstruir el mismo modelo (alias ``finally`` resuelto).
        """
        original = StepConfig(
            step="c1",
            type="Condition",
            condition="amount > 1000",
            if_true="approve",
            if_false="reject",
            **{"finally": True},
        )
        dump = original.model_dump()
        rebuilt = StepConfig(**dump)
        assert rebuilt == original
        assert rebuilt.model_dump() == dump
        assert rebuilt.finally_ is True

    def test_type_discriminator_all_8_members(self) -> None:
        """Scenario: discriminador ``type`` con los 8 StepType de Agno.

        Cada miembro del enum ``StepType`` construye la instancia correcta
        (misma instancia de enum, no coerción a string).
        """
        for member in StepType:
            s = StepConfig(step=f"s-{member.value.lower()}", type=member.value)
            assert s.type is member, f"{member.value!r} no resolvió a {member!r}"

    def test_type_discriminator_accepts_member_directly(self) -> None:
        """Scenario: el discriminador también acepta el miembro de enum directo."""
        s = StepConfig(step="s1", type=StepType.PARALLEL)
        assert s.type is StepType.PARALLEL
