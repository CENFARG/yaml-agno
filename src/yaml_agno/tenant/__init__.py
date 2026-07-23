"""yaml-agno tenant resolution package (SPEC_03 §5).

Provides the ``TenantResolver`` which parses the composite user_id built by
``resolve_user_id()`` (SPEC_04) into its ``tenant_id`` and ``principal_id``
components. This is a parsing-only utility — it never builds a composite and
never does I/O.
"""
