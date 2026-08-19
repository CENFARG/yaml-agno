"""AgentOS Control-Plane error types (SPEC_12 Slice 3).

Two pure exception classes with no logic. Covered implicitly by the
tasks that raise them — no separate test file needed.
"""

from __future__ import annotations

__all__ = ["AuthorizationBuildError", "ResyncBlockedError"]


class ResyncBlockedError(Exception):
    """Raised when ``resync_now()`` is blocked by an OPEN CircuitBreaker.

    The CircuitBreaker is in OPEN state and no HALF_OPEN probe is available.
    """


class AuthorizationBuildError(Exception):
    """Raised when ``AuthorizationConfig`` cannot be built fail-fast (VQ011).

    Covers every rejection in the authorization build contract
    (``agentos-authorization-build``, SPEC_12 Slice 3 / SPEC_19 §4 R1):

        - Unknown ``settings.config`` key (whitelist rejection listing the
          seven fields accepted by agno 2.8.7: ``verification_keys``,
          ``jwks_file``, ``algorithm``, ``verify_audience``, ``audience``,
          ``admin_scope``, ``user_isolation``).
        - ``settings.basic_auth`` present while enabled — agno 2.8.7's
          ``AuthorizationConfig`` has no basic-auth sink; pointer to the
          ``BasicAuthMiddleware`` (SPEC_19 §1.2, S5a.2) future sink.
        - Explicit ``user_isolation`` in ``settings.config`` — a security
          invariant always set to ``True`` by the adapter, never settable
          from YAML.
        - Unresolvable ``${SECRET:KEY}`` reference (secret callable raising
            ``KeyError`` or returning ``None``), or a residual reference in
            the legacy path where no resolution is available.

    The message always names the offending key/field and gives an actionable
    pointer, so a security config that would otherwise be silently ignored
    fails loudly at build time instead.
    """
