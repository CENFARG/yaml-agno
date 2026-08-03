"""AgentOS factory port — protocol contract for building AgentOS instances.

Slice 1 defines the minimal ``build(config) -> AgentOS`` contract.
Future slices MAY add ``with_interfaces()``, ``with_mcp()``, ``with_resync()``.

@ai-directive: SSOT is specs/SPEC_12_CONTROL_PLANE.md §2.3 (AgentOSFactoryPort).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from agno.os import AgentOS

    from yaml_agno.models.config.agentos_config import AgentOSConfig

__all__ = ["AgentOSFactoryPort"]


class AgentOSFactoryPort(Protocol):
    """Protocol contract for building ``agno.os.AgentOS`` from config.

    Adapters implementing this protocol receive an ``AgentOSConfig``
    aggregate and produce a fully-configured ``AgentOS`` instance.

    Structural subtyping — any class with a matching ``build`` signature
    satisfies this contract without explicit inheritance.
    """

    def build(self, config: AgentOSConfig) -> AgentOS:
        """Build an ``AgentOS`` instance from the validated config.

        Args:
            config: A validated ``AgentOSConfig`` aggregate.

        Returns:
            A constructed ``agno.os.AgentOS`` ready for serving.
        """
        ...
