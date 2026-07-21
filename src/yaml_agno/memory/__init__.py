"""Memory subsystem (SPEC_04 leaf).

Re-exports the single user_id resolver so callers can
``from yaml_agno.memory import resolve_user_id``.
"""

from yaml_agno.memory.user_identity import UserIdentityResolutionError, resolve_user_id

__all__ = ["UserIdentityResolutionError", "resolve_user_id"]
