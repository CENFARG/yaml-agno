"""HTTP middleware package — yaml-agno extensions for AgentOS (SPEC_06).

Provides middleware that AgentOS lacks (rate limiting, tenant context). All
middleware follows the Starlette ``BaseHTTPMiddleware`` pattern and is
registered inside ``YamlAgentOS.get_app()`` after ``super().get_app()``.
"""

from yaml_agno.api.middleware.tenant_context import TenantContextMiddleware

__all__ = ["TenantContextMiddleware"]
