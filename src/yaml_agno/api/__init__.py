"""HTTP API package — yaml-agno's ``AgentOS`` subclass (SPEC_06).

Re-exports the public ``YamlAgentOS`` class so callers can do
``from yaml_agno.api import YamlAgentOS``.
"""

from yaml_agno.api.app import YamlAgentOS

__all__ = ["YamlAgentOS"]
