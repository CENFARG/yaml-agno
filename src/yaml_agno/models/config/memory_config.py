"""Memory configuration schema (SPEC_04 leaf).

A pure-Pydantic V2 typed replacement for the opaque
``AgentConfig.memory: dict[str, Any] | None`` slot. Maps the Agno ``Agent``
constructor memory flags + ``system_user_id`` + the nested
session/working/learning/retention blocks declared in SPEC_04 §1.3.

This module is a STANDALONE additive slice: nothing imports it yet, and it
imports nothing from Agno (memory is 100% Agno-native; yaml-agno only
configures it). Wiring ``AgentConfig.memory`` to :class:`MemoryConfig` is a
later coordinated change (Option B opaque until then). Pattern follows
SPEC_14 ``model_spec.py``: ``ConfigDict(extra="forbid")``, separate file,
Google docstrings.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SessionMemoryConfig(BaseModel):
    """Agno session DB configuration (SPEC_04 §1.3 ``memory.session``).

    Attributes:
        storage_type: Agno session storage backend.
        max_messages: Agno native cap on recalled history messages.
    """

    model_config = ConfigDict(extra="forbid")

    storage_type: Literal["sqlite", "postgres", "memory"] = Field(
        ...,
        description="Agno session storage backend (sqlite|postgres|memory).",
    )
    max_messages: int = Field(
        ...,
        ge=0,
        description="Agno native cap on recalled history messages.",
    )


class WorkingMemoryConfig(BaseModel):
    """Working-context configuration (SPEC_04 §1.3 ``memory.working``).

    Attributes:
        max_context_tokens: Max tokens admitted into the working context window.
        compression_threshold: Token count at which SPEC_15 compression triggers.
        include_tool_calls: Whether tool-call transcripts are kept in working memory.
    """

    model_config = ConfigDict(extra="forbid")

    max_context_tokens: int = Field(..., ge=1, description="Max tokens in the working context window.")
    compression_threshold: int = Field(
        ..., ge=0, description="Token count at which SPEC_15 compression triggers."
    )
    include_tool_calls: bool = Field(..., description="Keep tool-call transcripts in working memory.")


class LearnedKnowledgeScopeConfig(BaseModel):
    """Scope for the ``learned_knowledge`` Agno store (SPEC_04 §1.5).

    Attributes:
        scope: Top-level namespace for learned knowledge. MUST be set explicitly
            (NOT inherited; see SPEC_04 §1.5 gotcha).
    """

    model_config = ConfigDict(extra="forbid")

    scope: str = Field(..., min_length=1, description="Namespace for learned_knowledge (set explicitly).")


class EntityMemoryScopeConfig(BaseModel):
    """Scope for the ``entity_memory`` Agno store (SPEC_04 §1.5).

    Attributes:
        scope: Namespace for entity memory. Inherits the top-level learning scope
            when omitted; set explicitly to override.
    """

    model_config = ConfigDict(extra="forbid")

    scope: str = Field(..., min_length=1, description="Namespace for entity_memory (inherits when omitted at runtime).")


class LearningMemoryConfig(BaseModel):
    """Long-term learning configuration (SPEC_04 §1.3 ``memory.learning``).

    Maps to the Agno ``LearningMachine`` (rich, 6 stores) when ``enabled`` is
    true, and to the ``MemoryManager`` / ``UserMemory`` simple path otherwise.

    Attributes:
        enabled: Turn on the Agno ``LearningMachine`` (cross-session learning).
        recall_on_start: Inject recalled learnings when a session starts.
        save_on_decision: Persist decisions through Agno native memory.
        save_on_discovery: Persist discoveries through Agno native memory.
        save_on_bugfix: Persist bug fixes through Agno native memory.
        scope: Top-level namespace inherited by ``entity_memory``.
        learned_knowledge: Explicit ``learned_knowledge`` namespace (NOT inherited).
        entity_memory: ``entity_memory`` namespace (inherits ``scope`` when omitted).
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(..., description="Turn on Agno LearningMachine (cross-session learning).")
    recall_on_start: bool = Field(..., description="Inject recalled learnings when a session starts.")
    save_on_decision: bool = Field(..., description="Persist decisions through Agno native memory.")
    save_on_discovery: bool = Field(..., description="Persist discoveries through Agno native memory.")
    save_on_bugfix: bool = Field(..., description="Persist bug fixes through Agno native memory.")
    scope: str = Field(..., min_length=1, description="Top-level namespace, inherited by entity_memory.")
    learned_knowledge: LearnedKnowledgeScopeConfig = Field(
        ..., description="learned_knowledge namespace (MUST be set explicitly; see §1.5)."
    )
    entity_memory: EntityMemoryScopeConfig = Field(
        ..., description="entity_memory namespace (inherits top-level scope when omitted)."
    )


class RetentionMaxAgeConfig(BaseModel):
    """Retention TTLs per store (SPEC_04 §1.3 ``memory.retention.max_age_days``).

    Attributes:
        sessions: Session messages TTL in days (example default 30).
        user_memory: UserMemory/UserMemo TTL in days (example default 180).
        learned_knowledge: learned_knowledge namespace TTL in days (example default 365).
    """

    model_config = ConfigDict(extra="forbid")

    sessions: int = Field(..., ge=0, description="Session messages TTL in days.")
    user_memory: int = Field(..., ge=0, description="UserMemory/UserMemo TTL in days.")
    learned_knowledge: int = Field(..., ge=0, description="learned_knowledge namespace TTL in days.")


class RetentionConfig(BaseModel):
    """Retention configuration (SPEC_04 §1.3 ``memory.retention``).

    Post-MVP configurable job; Agno has no native retention. WARNING (SPEC_04
    §3.4): do NOT use ``MemoryManager.clear()`` / ``db.clear_memories()`` in the
    purge job — they are global nukes with NO user/tenant filter.

    Attributes:
        enabled: Whether the retention purge job is active (post-MVP; non-blocking).
        max_age_days: Per-store TTLs.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(..., description="Enable the retention purge job (post-MVP).")
    max_age_days: RetentionMaxAgeConfig = Field(..., description="Per-store TTLs.")


class MemoryConfig(BaseModel):
    """Typed replacement for the opaque ``memory: dict[str, Any] | None`` slot.

    Mirrors the Agno ``Agent`` constructor memory flags plus ``system_user_id``
    and the nested session/working/learning/retention blocks declared in
    SPEC_04 §1.3. Pure Pydantic V2 — no Agno imports.

    Attributes:
        enable_agentic_memory: Agno agentic memory on/off.
        update_memory_on_run: Persist learnings after each run.
        add_memories_to_context: Inject recalled memories into the prompt.
        num_history_runs: Agno-managed history window (runs).
        num_history_messages: Agno-managed history window (messages).
        system_user_id: Principal part of the composite user_id used when there
            is no human user. Literal string OR a ``{placeholder}`` template
            resolved by :func:`yaml_agno.memory.resolve_user_id` against the
            run ``context``. The tenant_id is prefixed at resolve time.
        session: Agno session DB configuration.
        working: Working-context configuration.
        learning: Long-term learning configuration.
        retention: Retention purge configuration (post-MVP).

    Example:
        >>> MemoryConfig(
        ...     enable_agentic_memory=True,
        ...     update_memory_on_run=True,
        ...     add_memories_to_context=True,
        ...     num_history_runs=5,
        ...     num_history_messages=50,
        ...     system_user_id="agent:my_agent",
        ... )
    """

    model_config = ConfigDict(extra="forbid")

    # --- Agno Agent constructor memory flags (5 fields) ---
    enable_agentic_memory: bool = Field(..., description="Agno agentic memory on/off.")
    update_memory_on_run: bool = Field(..., description="Persist learnings after each run.")
    add_memories_to_context: bool = Field(..., description="Inject recalled memories into the prompt.")
    num_history_runs: int = Field(..., ge=0, description="Agno-managed history window (runs).")
    num_history_messages: int = Field(..., ge=0, description="Agno-managed history window (messages).")

    # --- User identity (1 field) ---
    system_user_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Principal part of the composite user_id (tenant prefixed at resolve "
            "time by resolve_user_id). Literal string OR a {placeholder} template."
        ),
    )

    # --- Nested blocks (4 fields) ---
    session: SessionMemoryConfig | None = Field(None, description="Agno session DB configuration.")
    working: WorkingMemoryConfig | None = Field(None, description="Working-context configuration.")
    learning: LearningMemoryConfig | None = Field(None, description="Long-term learning configuration.")
    retention: RetentionConfig | None = Field(None, description="Retention purge configuration (post-MVP).")


__all__ = [
    "EntityMemoryScopeConfig",
    "LearnedKnowledgeScopeConfig",
    "LearningMemoryConfig",
    "MemoryConfig",
    "RetentionConfig",
    "RetentionMaxAgeConfig",
    "SessionMemoryConfig",
    "WorkingMemoryConfig",
]
