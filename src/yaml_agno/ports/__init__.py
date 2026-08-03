"""Ports — Protocol definitions for the AgentOS control plane.

Clean Architecture: these Protocols define the contracts that adapters
(factories, resolvers, builders) implement. Structural subtyping — no
inheritance required.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from yaml_agno.ports.agentos_ports import AgentOSFactoryPort

if TYPE_CHECKING:
    pass

__all__ = [
    "AgentOSFactoryPort",
]
