"""Agent configuration schema (YAML root: agent). Single source of truth for the
agent YAML shape. Enums and provider resolution are delegated to Agno and to the
DependencyManager (SPEC_01); this module only defines the YAML schema and validates
syntax that is OWN to yaml-agno (e.g. the DIReference syntax)."""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# PEP 695 type aliases — the ONLY ones; reused everywhere, never redefined.
type Instructions = str
type ModelReference = str
type ToolConfig = dict[str, Any]
type Tag = str


class AgentConfig(BaseModel):
    """Schema for the ``agent:`` YAML root.

    Validates the declarative configuration of a single Agno agent before the
    AgentFactory (SPEC_01) resolves providers via the DependencyManager and builds
    the native ``agno.Agent``.

    Invariants enforced at the boundary:
        - ``name`` is non-empty and uses only safe characters [A-Za-z0-9_-].
        - ``model`` follows the ``provider:id`` string format (Agno model-as-string).

    Note:
        - Provider/model resolution delegated to DependencyManager (SPEC_01 §1.3)
          + Agno model factory (SPEC_14). This schema does NOT enumerate providers.
        - Nested config blocks (tools, knowledge, memory, session, reasoning,
          skills, human_review, culture, persistence) are validated by their own
          schemas in dedicated SPECs and referenced here as opaque dicts.
          AgentConfig is the aggregate that NAMES these slots; it does NOT
          enumerate their internals (DRY/SSOT).
    """

    model_config = ConfigDict(extra="forbid")

    # --- Identity (2 fields) ---
    name: str = Field(..., min_length=1, max_length=100, description="Unique agent name.")
    model: ModelReference = Field(..., description="Model as string 'provider:id' (e.g. openai:gpt-4o). See SPEC_14.")

    # --- Behavior (2 fields) ---
    instructions: Instructions | None = Field(None, max_length=50000, description="System prompt.")
    description: str | None = Field(None, description="Human-readable description.")

    # --- Delegated sub-systems: 9 opaque slots ---
    # tools is list[ToolConfig]; the other 8 are dict[str, Any] | None.
    # Each has a native counterpart in agno.Agent() (verified agent.py:384-503).
    tools: list[ToolConfig] = Field(default_factory=list, max_length=50, description="Tools config. See SPEC_11.")
    knowledge: dict[str, Any] | None = Field(None, description="Knowledge/RAG config. See SPEC_10.")
    memory: dict[str, Any] | None = Field(None, description="Memory config. See SPEC_04.")
    session: dict[str, Any] | None = Field(None, description="Session/storage config. See SPEC_03 + SPEC_13.")
    reasoning: dict[str, Any] | None = Field(None, description="Reasoning/chain-of-thought config. See SPEC_28.")
    skills: dict[str, Any] | None = Field(None, description="Agent skills config. See SPEC_30.")
    human_review: dict[str, Any] | None = Field(None, description="Human-in-the-loop review config. See SPEC_29.")
    culture: dict[str, Any] | None = Field(None, description="Culture/locale/persona config. See SPEC_31.")
    persistence: dict[str, Any] | None = Field(None, description="Persistence config. See SPEC_03.")

    # --- Organization (2 fields) ---
    tags: list[Tag] = Field(default_factory=list, max_length=20, description="Tags for organization.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Free-form metadata.")

    # Total: 13 named fields (2 identity + 2 behavior + 9 opaque + 2 org) + model_config.
    # `user_id` is INTENTIONALLY ABSENT (composite, runtime-only, SPEC_04).

    @field_validator("name")
    @classmethod
    def validate_name_characters(cls, v: str) -> str:
        """Ensure name uses only safe characters [A-Za-z0-9_-]."""
        if not re.match(r"^[A-Za-z0-9_-]+$", v):
            raise ValueError(
                f"Invalid agent name: {v}. Only alphanumeric, underscore and hyphen allowed."
            )
        return v

    @field_validator("model")
    @classmethod
    def validate_model_format(cls, v: str) -> str:
        """Ensure model follows 'provider:id' string format.

        Only SYNTAX is validated; whether the provider is known is resolved
        later by the DependencyManager against the Agno registry.
        """
        if ":" not in v:
            raise ValueError(f"Invalid model format: {v}. Expected 'provider:id'.")
        provider, _, model_id = v.partition(":")
        if not provider or not model_id:
            raise ValueError(f"Invalid model format: {v}. Expected 'provider:id'.")
        return v
