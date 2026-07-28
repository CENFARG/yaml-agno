"""Contract test — ensure yaml_agno.workflows does NOT introduce a
proprietary workflow runtime (TASK_008 negative assertion, SPEC_05 §4.3).

Agno owns the runtime: Workflow.run, session, memory, state-machine.
yaml-agno builds on top — never reimplements.
"""

from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.unit

FORBIDDEN_CLASSES = {"WorkflowExecution", "WorkflowState", "WorkflowStateMachine"}


def test_no_workflow_execution_state_machine() -> None:
    """Verify that yaml_agno.workflows does NOT expose runtime classes.

    Uses ``inspect.getmembers`` on ``yaml_agno.workflows`` to check for
    the presence of ``WorkflowExecution``, ``WorkflowState``, and
    ``WorkflowStateMachine``. None of them must be present as module
    attributes.
    """
    import yaml_agno.workflows as wf_mod

    members = dict(inspect.getmembers(wf_mod, inspect.isclass))
    found = FORBIDDEN_CLASSES & set(members.keys())

    assert found == set(), (
        f"yaml_agno.workflows exposes forbidden runtime classes: {found}. "
        "Agno owns the workflow runtime — yaml-agno must never reimplement "
        "WorkflowExecution, WorkflowState, or WorkflowStateMachine."
    )
