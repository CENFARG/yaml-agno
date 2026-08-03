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
    """Raised when ``AuthorizationAdapter`` cannot resolve a secret reference.

    The message includes the specific key that failed resolution.
    """
