"""TenantResolver — parses the composite user_id (SPEC_03 §5.2, slice D).

PARSES the ``{tenant_id}:{principal_id}`` composite that ``resolve_user_id()``
(SPEC_04) has ALREADY built. This is a yaml-agno domain addition; Agno has no
tenant concept.

The composite format is owned by SPEC_04: ``{tenant_id}:{principal_id}``. This
module NEVER builds a composite and NEVER derives a tenant from a raw Agno
``user_id``. It only extracts the tenant_id prefix (and the principal_id suffix)
so they can be used as the explicit ``WHERE tenant_id = ?`` filter on
``yamlagno_*`` config rows and as the telemetry ``set_tenant_id`` value.

Single-seam rule: ``resolve_user_id()`` BUILDS the composite;
``TenantResolver`` only CONSUMES it. Never invert.
"""

from __future__ import annotations


class TenantResolver:
    """Parse tenant_id and principal_id out of the composite user_id.

    The composite is ``{tenant_id}:{principal_id}`` (built by
    ``resolve_user_id()``, SPEC_04). This class splits on the FIRST colon only,
    so principal IDs that contain colons (e.g. ``workflow:agent-1``) are
    preserved in their entirety.

    This class performs pure parsing — no I/O, no side effects, and it does NOT
    validate that the tenant exists in ``yamlagno_tenants``. Callers that need
    existence use the repository (SPEC_03 §7.2).
    """

    def extract_tenant(self, composite_user_id: str) -> str:
        """Return the tenant_id parsed from the composite user_id.

        The composite is ``{tenant_id}:{principal_id}`` (SPEC_04). This method
        returns the substring before the first ``":"``.

        Args:
            composite_user_id: The already-resolved composite user_id from
                ``resolve_user_id()`` (SPEC_04). Must contain a ``":"`` separator.

        Returns:
            The tenant_id prefix of the composite (may be empty if the composite
            starts with ``":"``).

        Raises:
            ValueError: If the composite does not contain ``":"``.
        """
        if ":" not in composite_user_id:
            raise ValueError(
                f"composite_user_id {composite_user_id!r} does not contain a ':' "
                f"separator. Expected format '{{tenant_id}}:{{principal_id}}' "
                f"as built by resolve_user_id() (SPEC_04)."
            )
        tenant, _, _ = composite_user_id.partition(":")
        return tenant

    def extract_principal(self, composite_user_id: str) -> str:
        """Return the principal_id parsed from the composite user_id.

        The composite is ``{tenant_id}:{principal_id}`` (SPEC_04). This method
        returns everything AFTER the first ``":"`` — principal IDs may contain
        embedded colons (e.g. ``workflow:agent-1``).

        Args:
            composite_user_id: The already-resolved composite user_id from
                ``resolve_user_id()`` (SPEC_04). Must contain a ``":"`` separator.

        Returns:
            The principal_id suffix of the composite (everything after the first
            colon; may be empty if the composite ends with ``":"``).

        Raises:
            ValueError: If the composite does not contain ``":"``.
        """
        if ":" not in composite_user_id:
            raise ValueError(
                f"composite_user_id {composite_user_id!r} does not contain a ':' "
                f"separator. Expected format '{{tenant_id}}:{{principal_id}}' "
                f"as built by resolve_user_id() (SPEC_04)."
            )
        _, _, principal = composite_user_id.partition(":")
        return principal


__all__ = ["TenantResolver"]
