"""A2A Interface — YAML-driven Agent-to-Agent publishing layer.

SPEC_26: Thin config layer that references (doesn't reimplement) the A2A protocol.
Instantiates agno.os.interfaces.a2a.A2A from YAML declarations.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "A2ADependencyError",
    "A2AInterfaceConfig",
    "A2AInterfaceFactory",
    "A2APrefix",
    "A2AReferenceError",
]

# --- Errors ---


class A2AReferenceError(ValueError):
    """Declared A2A component ref cannot be resolved through registries."""


class A2ADependencyError(ImportError):
    """a2a-sdk is required but not installed."""


# --- Value Objects ---


class A2APrefix(BaseModel):
    """Namespaced route prefix for A2A endpoints.

    Immutable (frozen=True). Must start with '/'. Default: '/a2a'.
    """

    model_config = ConfigDict(frozen=True)

    value: str = "/a2a"

    @model_validator(mode="after")
    def _must_start_with_slash(self) -> A2APrefix:
        if not self.value.startswith("/"):
            raise ValueError("A2A prefix must start with '/'")
        return self


# --- Aggregate ---


class A2AInterfaceConfig(BaseModel):
    """Aggregate root for an A2A interface declaration.

    Requires at least one component (agents, teams, or workflows).
    Rejects extra fields. All fields have safe defaults.
    """

    model_config = ConfigDict(extra="forbid")

    agents: list[str] = Field(default_factory=list)
    teams: list[str] = Field(default_factory=list)
    workflows: list[str] = Field(default_factory=list)
    prefix: A2APrefix = Field(default_factory=A2APrefix)
    tags: list[str] | None = None

    @field_validator("prefix", mode="before")
    @classmethod
    def _coerce_prefix(cls, v: Any) -> A2APrefix:
        """Accept plain strings and coerce them to A2APrefix."""
        if isinstance(v, str):
            return A2APrefix(value=v)
        return v  # type: ignore[no-any-return]

    @model_validator(mode="after")
    def _at_least_one_component(self) -> A2AInterfaceConfig:
        total = len(self.agents) + len(self.teams) + len(self.workflows)
        if total == 0:
            raise ValueError(
                "A2A interface requires at least one agent, team, or workflow"
            )
        return self

    def all_refs(self) -> dict[str, list[str]]:
        """Return all component refs grouped by kind."""
        return {
            "agents": list(self.agents),
            "teams": list(self.teams),
            "workflows": list(self.workflows),
        }


# --- Factory ---


# --- Module-level helpers ---


def _require_a2a_sdk() -> None:
    """Verify a2a-sdk is importable; raise actionable error if not."""
    try:
        import a2a  # noqa: F401
    except ImportError as err:
        raise A2ADependencyError(
            "A2A interface declared but 'a2a-sdk' is not installed. "
            "Install with: pip install a2a-sdk"
        ) from err


class A2AInterfaceFactory:
    """Instantiate agno.os.interfaces.a2a.A2A from a YAML declaration.

    Resolves agent/team/workflow refs through registries, then forwards
    resolved objects to Agno's A2A constructor.
    """

    def build(self, config: A2AInterfaceConfig, registries: Any) -> Any:
        """Resolve refs and instantiate an Agno A2A server interface.

        Args:
            config: Parsed A2A declaration.
            registries: Object with ``.agents.resolve()``, ``.teams.resolve()``,
                ``.workflows.resolve()`` callables.

        Returns:
            An agno.os.interfaces.a2a.A2A instance.

        Raises:
            A2ADependencyError: If a2a-sdk is not installed.
            A2AReferenceError: If any declared ref cannot be resolved.
        """
        _require_a2a_sdk()

        agents = self._resolve_all(registries.agents, config.agents)
        teams = self._resolve_all(registries.teams, config.teams)
        workflows = self._resolve_all(registries.workflows, config.workflows)

        self._assert_no_missing(agents, teams, workflows, config)

        from agno.os.interfaces.a2a import A2A

        return A2A(
            agents=agents or None,
            teams=teams or None,
            workflows=workflows or None,
            prefix=config.prefix.value,
            tags=config.tags,
        )

    @staticmethod
    def _resolve_all(registry: Any, refs: list[str]) -> list[Any]:
        """Resolve a list of ref strings to live objects via a registry.

        Returns ``None`` entries for refs that raise KeyError/LookupError
        (which are then caught by ``_assert_no_missing``).
        """
        resolved: list[Any] = []
        for ref in refs:
            try:
                resolved.append(registry.resolve(ref))
            except (KeyError, LookupError):
                resolved.append(None)
        return resolved

    @staticmethod
    def _assert_no_missing(
        agents: list[Any],
        teams: list[Any],
        workflows: list[Any],
        config: A2AInterfaceConfig,
    ) -> None:
        """Raise A2AReferenceError if any declared ref failed to resolve."""
        refs = config.all_refs()
        resolved_counts = {
            "agents": sum(1 for a in agents if a is not None),
            "teams": sum(1 for t in teams if t is not None),
            "workflows": sum(1 for w in workflows if w is not None),
        }
        for kind, declared in refs.items():
            expected = len(declared)
            actual = resolved_counts[kind]
            if expected != actual:
                raise A2AReferenceError(
                f"A2A {kind} refs: {expected} declared, {actual} resolved. "
                f"Declared: {declared}"
            )
