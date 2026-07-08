"""Workflow configuration schema (YAML root: workflow). Single source of truth
for the workflow YAML shape. StepType is imported from Agno (not redefined)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# IMPORTED from Agno — never redefined. 8 members, Capitalized values:
# Function/Step/Steps/Loop/Parallel/Condition/Router/Workflow.
from agno.workflow.types import StepType


class StepConfig(BaseModel):
    """Schema for one step entry in a workflow YAML.

    The YAML ``type`` value must match an ``agno.workflow.types.StepType`` member
    (Capitalized string). Step-specific fields are validated against the step type.

    Note:
        - This schema UNIFIES distinct Agno workflow components (Step, Condition,
          Router, Loop, Parallel, Steps) into one shape discriminated by ``type``.
          The WorkflowFactory (SPEC_01 §4) translates each StepConfig into the
          corresponding Agno component. Fields NOT native to Agno (``execute``,
          ``finally_``, ``function``, ``condition``, ``if_true``, ``if_false``,
          ``expression``, ``cases``) are yaml-agno YAML syntax translated by the
          factory and MUST NOT be assumed to exist on Agno constructors.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # --- Identity (3 fields) ---
    step: str = Field(..., description="Unique step id within the workflow.")
    type: StepType = Field(default=StepType.STEP, description="Agno StepType (Capitalized value).")
    description: str | None = None

    # --- Executor references (4 fields) ---
    agent: str | None = Field(None, description="Referenced AgentConfig name (executor).")
    team: str | None = Field(None, description="Referenced TeamConfig name (executor).")
    # Agno's Step calls this `executor`; yaml-agno surfaces it as `function` in
    # YAML; the WorkflowFactory maps function -> Step(executor=...).
    function: str | None = Field(None, description="Callable reference (maps to Agno Step executor).")
    workflow: str | None = Field(None, description="Nested workflow name (workflow executor).")

    # --- Execution control — yaml-agno OWN syntax (NOT Agno native) ---
    execute: bool = Field(default=True, description="Enable/disable the step (yaml-agno own).")
    finally_: bool = Field(
        default=False,
        alias="finally",  # `finally` is a Python keyword — alias lets YAML use the natural form.
        description="Run always as cleanup (yaml-agno own).",
    )

    # --- Human-in-the-loop review gate (opaque) ---
    human_review: dict[str, Any] | None = Field(None, description="Per-step human-review gate config. See SPEC_29.")

    # --- Type-specific fields (yaml-agno abstraction; factory maps to Agno) ---
    # Nested steps (Parallel/Steps/Condition).
    steps: list[dict[str, Any]] = Field(default_factory=list, description="Nested steps (Parallel/Steps/Condition).")
    # Condition-only.
    condition: str | None = Field(None, description="CEL or callable expression (maps to Agno Condition.evaluator).")
    if_true: str | None = Field(None, description="Step id when condition is true (Agno Condition steps branch).")
    if_false: str | None = Field(None, description="Step id when condition is false (Agno Condition else_steps branch).")
    # Router-only.
    expression: str | None = Field(None, description="CEL expression (maps to Agno Router.selector).")
    cases: dict[str, str] = Field(default_factory=dict, description="value -> step id (maps to Agno Router.choices).")
    # Loop-only.
    end_condition: str | None = Field(None, description="Loop end condition (maps to Agno Loop.end_condition).")
    max_iterations: int | None = Field(None, ge=1, description="Loop max iterations (maps to Agno Loop.max_iterations).")

    # Total: 16 named fields (3 identity + 4 executor + 2 exec-control +
    #        1 human_review + 6 type-specific). The 4 type-specific groups are:
    #        nested-steps, condition, router, loop.

    @model_validator(mode="after")
    def validate_type_specific_fields(self) -> "StepConfig":
        """Ensure type-specific fields are only set for the matching step type.

        4 categories:
            1. Nested steps (Parallel, Steps, Condition).
            2. Condition-only (condition, if_true, if_false).
            3. Router-only (expression, cases).
            4. Loop-only (end_condition, max_iterations).
        """
        t = self.type
        # (1) Nested steps apply to Parallel, Steps and Condition.
        if self.steps and t not in (StepType.PARALLEL, StepType.STEPS, StepType.CONDITION):
            raise ValueError("Nested steps only allowed for Parallel/Steps/Condition types.")
        # (2) Condition-only fields.
        if any(v is not None for v in (self.condition, self.if_true, self.if_false)) and t != StepType.CONDITION:
            raise ValueError("condition/if_true/if_false only allowed for Condition type.")
        # (3) Router-only fields.
        if (self.expression is not None or self.cases) and t != StepType.ROUTER:
            raise ValueError("expression/cases only allowed for Router type.")
        # (4) Loop-only fields.
        if (self.end_condition is not None or self.max_iterations is not None) and t != StepType.LOOP:
            raise ValueError("end_condition/max_iterations only allowed for Loop type.")
        return self


class WorkflowConfig(BaseModel):
    """Schema for the ``workflow:`` YAML root.

    Invariants enforced at the boundary:
        - ``name`` is non-empty.
        - step ids are unique.
        - branch references (if_true/if_false/cases.values()) point to existing step ids.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=100, description="Unique workflow name.")
    description: str | None = None
    steps: list[StepConfig] = Field(..., min_length=1, description="Workflow steps.")
    metadata: dict[str, Any] = Field(default_factory=dict)

    # NOTE: `user_id` is INTENTIONALLY ABSENT (composite, runtime-only, SPEC_04).

    @model_validator(mode="after")
    def validate_steps_integrity(self) -> "WorkflowConfig":
        """Ensure step ids are unique AND branch references are valid.

        Walks ``if_true``, ``if_false``, and EVERY value in ``cases`` (NOT the keys —
        keys are router selector values, not step ids). A branch ref pointing to
        a non-existent step id is a dangling reference.
        """
        step_ids = [s.step for s in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Duplicate step ids detected in workflow.")
        valid = set(step_ids)
        for s in self.steps:
            for ref in (s.if_true, s.if_false, *s.cases.values()):
                if ref and ref not in valid:
                    raise ValueError(f"Branch references non-existent step: {ref}")
        return self
