"""User identity resolution for yaml-agno (SPEC_04 leaf).

THE single ``user_id`` resolver for ALL of yaml-agno (HTTP + non-HTTP). Returns
the composite ``"{tenant_id}:{principal_id}"`` — never a bare principal, never
``None``. ``TenantContextMiddleware`` (SPEC_06) calls this instead of building
the composite inline.

Verified against Agno v2.6.18: ``MemoryManager`` coerces ``user_id=None`` to the
literal string ``"default"`` in every method (``agno/memory/manager.py:177,191,
205,239``), causing cross-talk between anonymous runs. This module exists to
make that fall-through impossible.
"""

from typing import Any


class UserIdentityResolutionError(RuntimeError):
    """Raised when user_id cannot be resolved and Agno's 'default' is disallowed."""


def resolve_user_id(memory_cfg: Any,
                    principal_id: str | None,
                    tenant_id: str | None,
                    context: dict[str, Any] | None = None) -> str:
    """Resolve the effective Agno user_id as the composite "{tenant_id}:{principal_id}".

    This is THE single resolver used everywhere in yaml-agno (HTTP requests via
    TenantContextMiddleware, and autonomous/workflow runs). The composite format
    lives ONLY here; callers MUST NOT build ``f"{tenant}:{user}"`` inline.

    Selection of the principal:
      1. ``principal_id`` (the human user id, when a human is present).
      2. ``memory_cfg.system_user_id``, after expanding derivation templates such
         as ``"workflow:{workflow_id}"`` or ``"agent:{agent_id}"`` against
         ``context``.
      3. Nothing else — there is NO silent fallback to Agno's ``"default"``.

    Args:
        memory_cfg: YAML ``memory:`` block (SPEC_02 *Config). Carries
            ``system_user_id`` (a literal string or a ``{placeholder}`` template)
            used as the principal when no human is present.
        principal_id: Human user id when the run has one; ``None`` otherwise
            (the ``system_user_id`` is then used as the principal).
        tenant_id: Tenant id. For HTTP requests it comes from the JWT/header
            (TenantContextMiddleware, SPEC_06); for autonomous/workflow runs it
            comes from the agent/workflow YAML ``tenant_id`` field.
        context: Optional dict used to expand templates (``workflow_id``,
            ``agent_id``, etc.).

    Returns:
        The composite ``"{tenant_id}:{principal_id}"`` string (never ``None``,
        never a bare principal).

    Raises:
        UserIdentityResolutionError: if ``tenant_id`` is missing, or if neither a
            human principal nor a ``system_user_id`` resolves. The caller MUST
            surface this at config-build/run time rather than passing
            ``user_id=None`` to Agno.
    """
    if not tenant_id:
        raise UserIdentityResolutionError(
            "tenant_id is required to build the composite user_id "
            "'{tenant_id}:{principal_id}'. For HTTP requests it comes from the "
            "TenantContextMiddleware (SPEC_06); for autonomous runs set the "
            "agent/workflow YAML 'tenant_id' field. Refusing to build a "
            "tenant-less user_id (would break tenant isolation)."
        )

    if principal_id:
        resolved_principal = principal_id
    else:
        template = getattr(memory_cfg, "system_user_id", None)
        if not template:
            raise UserIdentityResolutionError(
                "No principal resolves (no human user and no "
                "memory.system_user_id). Refusing to fall through to Agno's "
                "shared 'default' memory bucket; set memory.system_user_id or "
                "pass an explicit principal_id."
            )
        if "{" in template and "}" in template:
            if context is None:
                raise UserIdentityResolutionError(
                    f"system_user_id template {template!r} needs a context dict "
                    f"(workflow_id/agent_id/...) to expand."
                )
            try:
                resolved_principal = template.format(**context)
            except KeyError as exc:
                raise UserIdentityResolutionError(
                    f"system_user_id template {template!r} references missing "
                    f"key {exc}. Provide it in the run context."
                ) from exc
        else:
            resolved_principal = template

    return f"{tenant_id}:{resolved_principal}"


__all__ = ["UserIdentityResolutionError", "resolve_user_id"]
