"""A2AConfig: YAML ``a2a:`` block → Agno remote mapping (SPEC_05 Slice D).

Thin YAML config surface that maps onto Agno's native A2A (Agent-to-Agent)
support. Never defines a custom wire protocol, never introduces ``TeamMessage``
or an ACP adapter. The single mapping class is ``BaseRemote`` with
``protocol="a2a"``.

``enable_interface=True`` requires the optional ``a2a-sdk`` extra:
``pip install a2a-sdk``. The ``agno.os.interfaces.a2a.A2A`` import fails
without it (verified in Agno 2.8.3).
"""

from __future__ import annotations

from typing import Literal

from agno.remote import BaseRemote
from pydantic import BaseModel, ConfigDict, Field

__all__ = ["A2AConfig", "A2AConfigFactory", "A2AExposedEntry", "A2ARemoteEntry"]

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

_Kind = Literal["agent", "team", "workflow"]
"""Allowed remote/expose entity kinds — the three Agno primitives."""

_A2AProtocol = Literal["a2a"]
"""The only allowed protocol — ``a2a``. Anything else is rejected."""


class A2AExposedEntry(BaseModel):
    """Describes an entity that should be advertised via the A2A interface.

    Corresponds to Agno's ``a2a_interface`` exposure list. The consumer
    (OS layer) uses ``kind`` + ``ref`` to locate the actual Agno object
    by name.
    """

    model_config = ConfigDict(extra="forbid")

    kind: _Kind = Field(..., description="Entity kind: agent, team, or workflow.")
    ref: str = Field(
        ..., min_length=1, description="Reference name of the Agno entity to expose."
    )
    description: str | None = Field(
        None, description="Optional human-readable description for discovery."
    )


class A2ARemoteEntry(BaseModel):
    """Describes a remote Agno entity reachable via A2A.

    Maps to ``BaseRemote(base_url=endpoint, protocol="a2a")``. The
    ``protocol`` field is constrained to ``Literal["a2a"]`` — no other
    protocol is accepted.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="Logical name for this remote.")
    kind: _Kind = Field(..., description="Entity kind: agent, team, or workflow.")
    endpoint: str = Field(
        ..., min_length=1, description="Base URL of the remote Agno instance."
    )
    protocol: _A2AProtocol = Field(
        default="a2a",
        description="Communication protocol — only 'a2a' is accepted.",
    )


class A2AConfig(BaseModel):
    """Schema for the ``a2a:`` YAML block.

    Parses ``enable_interface``, ``expose`` entries, and ``remote`` entries.
    Defaults::

        enabled_interface=False    expose=[]    remote=[]

    No other keys are allowed (``extra="forbid"``).
    """

    model_config = ConfigDict(extra="forbid")

    enable_interface: bool = Field(
        default=False,
        description="When True, the Agno OS A2A interface is enabled. "
        "Requires ``a2a-sdk`` extra (``pip install a2a-sdk``).",
    )
    expose: list[A2AExposedEntry] = Field(
        default_factory=list,
        description="Entities to expose via the A2A interface.",
    )
    remote: list[A2ARemoteEntry] = Field(
        default_factory=list,
        description="Remote Agno entities to connect to via A2A.",
    )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class A2AConfigFactory:
    """Build Agno ``BaseRemote`` instances from ``A2AConfig.remote`` entries.

    Each remote entry maps ONE-TO-ONE onto::

        BaseRemote(base_url=endpoint, protocol="a2a")

    The ``kind`` field on ``A2ARemoteEntry`` is metadata — the factory
    does not dispatch to different Agno classes because all remote kinds
    use ``BaseRemote`` with ``protocol="a2a"`` in Agno 2.8.3.
    """

    def build(self, config: A2AConfig) -> list[BaseRemote]:
        """Build a list of ``BaseRemote`` instances from the config.

        Args:
            config: Parsed ``A2AConfig`` with optional ``remote`` entries.

        Returns:
            List of ``BaseRemote`` instances (empty if no remote entries).
        """
        return [
            BaseRemote(base_url=entry.endpoint, protocol=entry.protocol)  # type: ignore[abstract]
            for entry in config.remote
        ]
