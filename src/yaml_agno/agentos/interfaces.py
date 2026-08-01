"""InterfaceRegistry — resolves InterfaceSpec entries to Agno BaseInterface subclasses.

TASK_003 — SPEC_12 Slice 2, PR 1. Implements map-based dispatch for 5 interface
types (AGUI, Slack, WhatsApp, Telegram, A2A) with credential validation and
lazy Agno imports for optional dependencies.

Design (sdd/control-plane-s2/design):
    - Map-based dispatch: ``{InterfaceType.AGUI: self._build_agui, ...}``
    - Lazy imports: Agno interface classes imported only when requested.
    - Credential validation: required keys per type checked pre-build.
    - ``${SECRET:KEY}`` patterns resolved via optional secret_manager callable.
    - Error hierarchy: InterfaceCredentialError + InterfaceBuildError extend ValueError.
    - Credential maps are ``ClassVar`` (not per-instance state).

@ai-directive: SSOT is specs/SPEC_12_CONTROL_PLANE.md §4 (InterfaceRegistry).
    Build ON TOP of Agno — wrap BaseInterface subclasses, don't reimplement.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "InterfaceBuildError",
    "InterfaceCredentialError",
    "InterfaceRegistry",
    "InterfaceSpec",
    "InterfaceType",
]

# ═══════════════════════════════════════════════════════════════════════════
# Value Objects
# ═══════════════════════════════════════════════════════════════════════════


class InterfaceType(StrEnum):
    """Supported AgentOS interface types.

    Maps to Agno BaseInterface subclasses:
        AGUI      → agno.os.interfaces.agui.AGUI
        SLACK     → agno.os.interfaces.slack.Slack
        WHATSAPP  → agno.os.interfaces.whatsapp.Whatsapp
        TELEGRAM  → agno.os.interfaces.telegram.Telegram
        A2A       → agno.os.interfaces.a2a.A2A
    """

    AGUI = "agui"
    SLACK = "slack"
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    A2A = "a2a"


class InterfaceSpec(BaseModel):
    """Pydantic V2 model for a single interface declaration.

    Fields:
        type: Interface type (agui, slack, whatsapp, telegram, a2a).
        target: Agent/team/workflow reference name.
        config: Type-specific configuration (credentials, webhook URLs, etc.).
    """

    model_config = ConfigDict(extra="forbid")

    type: InterfaceType
    target: str
    config: dict[str, Any] = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════
# Error Hierarchy
# ═══════════════════════════════════════════════════════════════════════════


class InterfaceCredentialError(ValueError):
    """Raised when required credentials are missing for an interface type."""


class InterfaceBuildError(ValueError):
    """Raised when an interface cannot be built (unknown type, missing dep, etc.)."""


# ═══════════════════════════════════════════════════════════════════════════
# Lazy Import Helpers (module-level for test mocking)
# ═══════════════════════════════════════════════════════════════════════════


def _import_agui():
    """Lazy-import the AGUI interface class (requires ``ag_ui``)."""
    from agno.os.interfaces.agui import AGUI

    return AGUI


def _import_slack():
    """Lazy-import the Slack interface class (requires ``slack_sdk``)."""
    from agno.os.interfaces.slack import Slack

    return Slack


def _import_whatsapp():
    """Lazy-import the WhatsApp interface class (no extra deps)."""
    from agno.os.interfaces.whatsapp import Whatsapp

    return Whatsapp


def _import_telegram():
    """Lazy-import the Telegram interface class (requires ``pyTelegramBotAPI``)."""
    from agno.os.interfaces.telegram import Telegram

    return Telegram


def _import_a2a():
    """Lazy-import the A2A interface class (requires ``a2a-sdk``)."""
    from agno.os.interfaces.a2a import A2A

    return A2A


# ═══════════════════════════════════════════════════════════════════════════
# InterfaceRegistry
# ═══════════════════════════════════════════════════════════════════════════


class InterfaceRegistry:
    """Resolves ``InterfaceSpec`` entries to Agno ``BaseInterface`` subclasses.

    Map-based dispatch with per-type credential validation and lazy imports.
    Constructor-injected ``secret_manager`` resolves ``${SECRET:KEY}`` patterns.

    Example:
        >>> registry = InterfaceRegistry(secret_manager=my_resolver)
        >>> spec = InterfaceSpec(type="agui", target="researcher")
        >>> iface = registry.build(spec, resolve_target=my_registry.get)
    """

    # Per-type required credential config keys (ClassVar — design invariant).
    _credential_keys: ClassVar[dict[InterfaceType, list[str]]] = {
        InterfaceType.AGUI: [],
        InterfaceType.SLACK: ["bot_token", "app_token", "signing_secret"],
        InterfaceType.WHATSAPP: ["phone_number_id", "access_token", "verify_token"],
        InterfaceType.TELEGRAM: ["token"],
        InterfaceType.A2A: [],
    }

    def __init__(self, secret_manager: Callable[[str], str] | None = None) -> None:
        """Initialize the registry.

        Args:
            secret_manager: Optional callable ``(key: str) -> str`` that resolves
                ``${SECRET:KEY}`` references in interface config values.
                If None, ``${SECRET:...}`` values are left unresolved (treated as
                literal strings).
        """
        self._secret_manager = secret_manager
        self._builders: dict[InterfaceType, Callable[..., Any]] = {
            InterfaceType.AGUI: self._build_agui,
            InterfaceType.SLACK: self._build_slack,
            InterfaceType.WHATSAPP: self._build_whatsapp,
            InterfaceType.TELEGRAM: self._build_telegram,
            InterfaceType.A2A: self._build_a2a,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, spec: InterfaceSpec, resolve_target: Callable[[str], Any]) -> Any:
        """Build a single interface from its spec.

        Pipeline:
            1. Resolve credentials (``${SECRET:...}`` → real values).
            2. Validate required credential keys are present.
            3. Resolve the target ref via ``resolve_target``.
            4. Dispatch to the per-type builder.

        Args:
            spec: The interface specification.
            resolve_target: Callable ``(ref: str) -> Any`` resolving agent/team/
                workflow reference names to live objects.

        Returns:
            An Agno ``BaseInterface`` subclass instance.

        Raises:
            InterfaceCredentialError: Required credential keys are missing.
            InterfaceBuildError: The interface type has no registered builder
                or the Agno dependency is not installed.
        """
        config = self._resolve_credential_refs(spec.config)
        self._validate_credentials(spec.type, config)

        target = resolve_target(spec.target)

        builder = self._builders.get(spec.type)
        if builder is None:
            raise InterfaceBuildError(
                f"No builder registered for interface type {spec.type.value!r}. "
                f"Available types: {[t.value for t in self._builders]}."
            )

        return builder(target, config)

    def build_all(
        self, specs: list[InterfaceSpec], resolve_target: Callable[[str], Any]
    ) -> list[Any]:
        """Build all interface specs.

        Args:
            specs: List of interface specifications.
            resolve_target: Callable resolving ref strings to live objects.

        Returns:
            List of Agno ``BaseInterface`` subclass instances.
        """
        return [self.build(spec, resolve_target) for spec in specs]

    # ------------------------------------------------------------------
    # Credential Resolution
    # ------------------------------------------------------------------

    def _resolve_credential_refs(self, config: dict[str, Any]) -> dict[str, Any]:
        """Resolve ``${SECRET:KEY}`` patterns in config values.

        If no ``secret_manager`` is configured, ``${SECRET:...}`` values are
        left as-is (the caller receives the literal string).

        Args:
            config: Raw config dict from ``InterfaceSpec``.

        Returns:
            A new dict with resolved secret references (or originals if no resolver).
        """
        resolved: dict[str, Any] = {}
        for key, value in config.items():
            if isinstance(value, str) and value.startswith("${SECRET:") and value.endswith("}"):
                if self._secret_manager is not None:
                    secret_key = value[len("${SECRET:") : -1]
                    resolved[key] = self._secret_manager(secret_key)
                else:
                    resolved[key] = value
            else:
                resolved[key] = value
        return resolved

    # ------------------------------------------------------------------
    # Credential Validation
    # ------------------------------------------------------------------

    @classmethod
    def _validate_credentials(cls, interface_type: InterfaceType, config: dict[str, Any]) -> None:
        """Verify all required credential keys are present and non-empty.

        Uses the class-level ``_credential_keys`` map. Types with no required
        keys (AGUI, A2A) always pass.

        Args:
            interface_type: The interface type to validate for.
            config: Resolved config dict (post-secret resolution).

        Raises:
            InterfaceCredentialError: One or more required keys are missing.
        """
        required = cls._credential_keys.get(interface_type, [])
        missing = [k for k in required if k not in config or not config[k]]
        if missing:
            raise InterfaceCredentialError(
                f"Missing required credentials for interface type "
                f"{interface_type.value!r}: {missing}. "
                f"Required keys: {required}."
            )

    # ------------------------------------------------------------------
    # Per-Type Builders
    # ------------------------------------------------------------------

    def _build_agui(self, target: Any, config: dict[str, Any]) -> Any:
        """Build an AGUI interface (no credentials required)."""
        AGUI = _import_agui()  # noqa: N806
        return AGUI(agent=target)

    def _build_slack(self, target: Any, config: dict[str, Any]) -> Any:
        """Build a Slack interface with bot_token, app_token, signing_secret."""
        Slack = _import_slack()  # noqa: N806
        return Slack(
            agent=target,
            token=config["bot_token"],
            signing_secret=config["signing_secret"],
        )

    def _build_whatsapp(self, target: Any, config: dict[str, Any]) -> Any:
        """Build a WhatsApp interface with phone_number_id, access_token, verify_token."""
        Whatsapp = _import_whatsapp()  # noqa: N806
        return Whatsapp(
            agent=target,
            phone_number_id=config["phone_number_id"],
            access_token=config["access_token"],
            verify_token=config["verify_token"],
        )

    def _build_telegram(self, target: Any, config: dict[str, Any]) -> Any:
        """Build a Telegram interface with token."""
        Telegram = _import_telegram()  # noqa: N806
        return Telegram(agent=target, token=config["token"])

    def _build_a2a(self, target: Any, config: dict[str, Any]) -> Any:
        """Build an A2A interface (no credentials, supports plural agents/teams/workflows)."""
        A2A = _import_a2a()  # noqa: N806
        return A2A(agents=[target])
