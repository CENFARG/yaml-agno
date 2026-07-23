"""Config-store repositories built on core-cenf GenericRepository (SPEC_03 §7.2).

yaml-agno does NOT subclass a ``BaseRepository`` or manage transactions
directly. Each repository here wraps ``db.get_repository(EntityRecord)`` inside
``async with db.transaction()``, with explicit ``tenant_id`` filters on every
call (no RLS — isolation is application-layer WHERE clauses).
"""
