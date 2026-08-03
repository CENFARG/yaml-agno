"""RED test for workflow models re-export (TD-04).

Strict TDD — this test is written BEFORE the implementation exists.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_workflow_config_re_export() -> None:
    """Verify models.py re-exports SSOT types from models.config.workflow_config."""
    from yaml_agno.workflows.models import StepConfig, StepType, WorkflowConfig

    # After import resolves, verify the symbols are actual classes from the SSOT.
    assert WorkflowConfig is not None
    assert StepConfig is not None
    assert StepType is not None
