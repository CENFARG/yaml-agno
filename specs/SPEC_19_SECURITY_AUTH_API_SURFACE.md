---
Spec_ID: "SPEC_19"
Title: "Security, Auth and API Surface - JWT, RBAC, Per-User Isolation and Endpoint Catalog"
Version: "0.1.0-MVP"
Maturity_Level: "Semilla"
Status: "Draft"
Target_Agent: "sdd-apply"
Context_Tags: ["#JWT", "#RBAC", "#Scopes", "#PerUserIsolation", "#BasicAuth", "#CORS", "#SecurityHeaders", "#AgentOS", "#API"]
Dependency_Hashes: ["SPEC_06", "SPEC_03", "SPEC_01"]
Last_Updated: "2026-06-14"
---

# SPEC_19_SECURITY_AUTH_API_SURFACE

> **Propósito**: Especificar el modelo de autorización JWT con scopes jerárquicos, RBAC, aislamiento per-user, Basic Auth legacy, CORS, security headers, y el catálogo exhaustivo de endpoints del AgentOS API, todo mapeado desde YAML.

---

## 0. FRONTERA CON SPEC_06 (LECTURA OBLIGATORIA)

Existe una frontera deliberada entre SPEC_06 y SPEC_19. Ambos tocan API, pero en capas distintas.

| Dimensión | SPEC_06 (API and AX) | SPEC_19 (este documento) |
|-----------|----------------------|--------------------------|
| **Alcance** | Contratos REST genéricos de FastAPI + AX function calling | JWT/scopes/isolation + catálogo exhaustivo de endpoints AgentOS |
| **Endpoints cubiertos** | `POST /agents/{name}/run`, health, readiness (6 endpoints) | Catálogo completo: agents, teams, workflows, sessions, memory, knowledge, metrics, evals, approvals, schedules, registry, components, a2a, agui, slack, whatsapp, traces, health |
| **Rate Limiting** | Sí (definido aquí, §1.4) | Referencia SPEC_06 §1.4 (NO duplica) |
| **Auth middleware** | No | Sí (JWTMiddleware, BasicAuth, ScopeEnforcer, RBACManager) |
| **Health checks** | Liveness/readiness (aquí referencia) | Extiende con endpoints del AgentOS API surface |
| **AX schemas** | Sí (JSON schemas function calling) | No |

**Regla de oro**:
- Si la pregunta es "¿cómo implemento un endpoint `/run` o un health check?" → SPEC_06.
- Si la pregunta es "¿cómo valido un JWT, qué scope requiere `/agents/*/runs`, o cómo aíslo datos por usuario?" → SPEC_19.

SPEC_19 **extiende** SPEC_06: reutiliza el patrón FastAPI + el `RateLimiter` de SPEC_06 §1.4 sin redefinirlo. Especifica las políticas de auth/authorization y el catálogo completo de endpoints del AgentOS.

**Referencia cruzada explícita**:
- `RateLimiter` (tenant/IP buckets, 100 req/min tenant, 20 req/min IP): SPEC_06 §1.4.
- Liveness/Readiness probes: SPEC_06 §1.3.
- `AgentRunRequest`/`AgentRunResponse`: SPEC_06 §1.2.
- Persistencia sessions/memoria (modelo filas con `user_id`): SPEC_03, SPEC_04.

---

## 1. MODELOS DE AUTENTICACIÓN

### 1.1 Dos Modos de Seguridad

AgentOS soporta dos modos. yaml-agno los mapea desde `security.auth_mode` en YAML.

| Modo | Cuándo usar | Header | Config |
|------|-------------|--------|--------|
| **Basic Authentication** (`OS_SECURITY_KEY`) | Desarrollo, simple. **Deprecado** para prod. | `Authorization: Bearer <key>` | `OS_SECURITY_KEY` env var |
| **Authorization (JWT + RBAC)** | Producción, multi-tenant, fine-grained. | `Authorization: Bearer <jwt>` | `authorization=True` + `AuthorizationConfig` |

### 1.2 Basic Authentication (Legacy)

```python
# yaml-agno/src/security/basic_auth.py

import os
from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

class BasicAuthMiddleware:
    """
    Validación de OS_SECURITY_KEY.
    Requests sin Authorization: Bearer <key> válido retornan 401.
    DEPRECADO para producción: usar JWT (sección 1.3).
    """

    HEADER_KEY = "Authorization"

    def __init__(self, security_key: str | None = None):
        self.security_key = security_key or os.environ.get("OS_SECURITY_KEY")

    async def __call__(self, request: Request) -> None:
        if not self.security_key:
            # No configurado = sin proteccion (solo dev)
            request.state.authenticated = False
            return

        auth_header = request.headers.get(self.HEADER_KEY, "")
        token = self._extract_bearer(auth_header)

        if token != self.security_key:
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing security key",
                headers={"WWW-Authenticate": "Bearer"},
            )
        request.state.authenticated = True
        request.state.user_id = "anonymous"
        request.state.scopes = ["agent_os:admin"]   # basic auth = acceso total

    @staticmethod
    def _extract_bearer(header: str) -> str | None:
        if not header.startswith("Bearer "):
            return None
        return header[7:]
```

### 1.3 JWT Authorization (Recomendado)

```python
# yaml-agno/src/security/jwt_middleware.py

from typing import Optional, List, Iterable, Dict, Any
from enum import Enum
from fastapi import Request, HTTPException
import jwt

class TokenSource(str, Enum):
    HEADER = "header"      # Authorization: Bearer <token>
    COOKIE = "cookie"      # cookie
    BOTH = "both"          # header primero, cookie fallback

# Rutas excluidas por defecto (no requieren JWT/RBAC)
DEFAULT_EXCLUDED_ROUTES = [
    "/",
    "/health",
    "/liveness",
    "/readiness",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/docs/oauth2-redirect",
]

class JWTMiddleware:
    """
    Middleware de autenticacion JWT con RBAC opcional.
    Replica JWTMiddleware de Agno (agno.os.middleware.jwt).

    Flujo:
    1. Extrae token (header/cookie/both)
    2. Verifica firma contra verification_keys (orden) o JWKS (por kid)
    3. Verifica exp, aud (si verify_audience)
    4. Extrae scopes, user_id (sub), session_id
    5. Si authorization=True: enforcea scopes por ruta
    6. Si user_isolation=True: aplica filas por user_id (no-admin)
    """

    def __init__(
        self,
        verification_keys: Optional[List[str]] = None,
        jwks_file: Optional[str] = None,
        algorithm: str = "RS256",
        validate: bool = True,
        authorization: bool = False,
        token_source: TokenSource = TokenSource.HEADER,
        token_header_key: str = "Authorization",
        cookie_name: str = "access_token",
        scopes_claim: str = "scopes",
        user_id_claim: str = "sub",
        session_id_claim: str = "session_id",
        audience_claim: str = "aud",
        audience: Optional[str | Iterable[str]] = None,
        verify_audience: bool = False,
        scope_mappings: Optional[Dict[str, List[str]]] = None,
        excluded_route_paths: Optional[List[str]] = None,
        admin_scope: str = "agent_os:admin",
        user_isolation: bool = False,
    ):
        self.verification_keys = verification_keys or []
        self.jwks_file = jwks_file
        self.algorithm = algorithm
        self.validate = validate
        self.authorization = authorization
        self.token_source = token_source
        self.token_header_key = token_header_key
        self.cookie_name = cookie_name
        self.scopes_claim = scopes_claim
        self.user_id_claim = user_id_claim
        self.session_id_claim = session_id_claim
        self.audience_claim = audience_claim
        self.audience = audience
        self.verify_audience = verify_audience
        self.scope_mappings = scope_mappings or {}
        self.excluded_route_paths = excluded_route_paths or DEFAULT_EXCLUDED_ROUTES
        self.admin_scope = admin_scope
        self.user_isolation = user_isolation

    async def __call__(self, request: Request) -> None:
        # 1. Excluir rutas publicas
        if self._is_excluded(request.url.path):
            request.state.authenticated = False
            return

        # 2. Extraer token
        token = self._extract_token(request)
        if not token:
            raise HTTPException(status_code=401, detail="Missing JWT token",
                                headers={"WWW-Authenticate": "Bearer"})

        # 3. Verificar y decodificar
        if not self.validate:
            request.state.authenticated = True
            request.state.token = token
            return

        try:
            claims = self._decode(token)
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidAudienceError:
            raise HTTPException(status_code=401, detail="Invalid audience")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid JWT token")

        # 4. Poblar request.state
        scopes = claims.get(self.scopes_claim, [])
        user_id = claims.get(self.user_id_claim)
        session_id = claims.get(self.session_id_claim)

        request.state.authenticated = True
        request.state.user_id = user_id
        request.state.session_id = session_id
        request.state.scopes = scopes
        request.state.audience = claims.get(self.audience_claim)
        request.state.token = token
        request.state.authorization_enabled = self.authorization
        request.state.user_isolation_enabled = self.user_isolation
        request.state.accessible_resource_ids = self._extract_accessible_ids(scopes)
        request.state.is_admin = self.admin_scope in scopes

        # 5. Enforce scopes
        if self.authorization:
            self._enforce_scopes(request, scopes)

    def _decode(self, token: str) -> dict:
        # Intentar JWKS primero (por kid) si esta configurado
        if self.jwks_file:
            key = self._lookup_jwks(token)
            return jwt.decode(token, key=key, algorithms=[self.algorithm],
                              audience=self.audience if self.verify_audience else None)
        # Probar cada verification_key en orden
        last_err = None
        for key in self.verification_keys:
            try:
                return jwt.decode(token, key=key, algorithms=[self.algorithm],
                                  audience=self.audience if self.verify_audience else None)
            except jwt.InvalidTokenError as e:
                last_err = e
        raise last_err or jwt.InvalidTokenError("No verification key available")

    def _lookup_jwks(self, token: str) -> str:
        # leer jwks_file, matchear kid del header del JWT
        unverified = jwt.get_unverified_header(token)
        kid = unverified.get("kid")
        # cargar JWKS y retornar la key correspondiente
        ...  # implementacion real carga y parsea el JWKS
        raise jwt.InvalidTokenError(f"kid {kid} not in JWKS")

    def _extract_token(self, request: Request) -> Optional[str]:
        header = request.headers.get(self.token_header_key, "")
        cookie = request.cookies.get(self.cookie_name)
        if self.token_source == TokenSource.HEADER:
            return self._from_header(header)
        if self.token_source == TokenSource.COOKIE:
            return cookie
        # BOTH
        return self._from_header(header) or cookie

    @staticmethod
    def _from_header(header: str) -> Optional[str]:
        if header.startswith("Bearer "):
            return header[7:]
        return None

    def _is_excluded(self, path: str) -> bool:
        return path in self.excluded_route_paths

    @staticmethod
    def _extract_accessible_ids(scopes: List[str]) -> set[str]:
        """Para resource:<id>:action scopes, colecciona ids accesibles."""
        ids = set()
        for s in scopes:
            parts = s.split(":")
            if len(parts) == 3 and parts[1] not in ("*",):
                ids.add(parts[1])
        return ids

    def _enforce_scopes(self, request: Request, scopes: List[str]) -> None:
        # admin bypass
        if self.admin_scope in scopes:
            return
        required = self._required_scopes_for(request)
        if required and not self._has_any(scopes, required):
            raise HTTPException(status_code=403, detail="Insufficient scopes")

    def _required_scopes_for(self, request: Request) -> List[str]:
        # scope_mappings custom primero, luego defaults del EndpointRegistry
        pattern = f"{request.method} {request.url.path}"
        if pattern in self.scope_mappings:
            return self.scope_mappings[pattern]
        return EndpointRegistry.required_scopes(request.method, request.url.path)

    @staticmethod
    def _has_any(held: List[str], required: List[str]) -> bool:
        if not required:
            return True
        held_set = set(held)
        for r in required:
            if r in held_set:
                return True
            # wildcard agents:*:action
            parts = r.split(":")
            if len(parts) == 3:
                wildcard = f"{parts[0]}:*:{parts[2]}"
                if wildcard in held_set:
                    return True
        return False
```

### 1.4 Request State tras el Middleware

| Atributo | Tipo | Descripción |
|----------|------|-------------|
| `authenticated` | `bool` | Si el usuario está autenticado |
| `user_id` | `Optional[str]` | User ID del claim `sub` |
| `session_id` | `Optional[str]` | Session ID del claim |
| `scopes` | `List[str]` | Scopes del token |
| `audience` | `Optional[str]` | Claim `aud` |
| `token` | `str` | JWT raw |
| `authorization_enabled` | `bool` | Si RBAC está activo |
| `user_isolation_enabled` | `bool` | Si aislamiento está activo |
| `accessible_resource_ids` | `Set[str]` | IDs de recurso accesibles (listings) |
| `is_admin` | `bool` | Si tiene `admin_scope` |

### 1.5 Respuestas de Error

| Status | Causa |
|--------|-------|
| `401 Unauthorized` | Token ausente o inválido |
| `401 Unauthorized` | Token expirado |
| `401 Unauthorized` | Audience inválido (token no es para este AgentOS) |
| `403 Forbidden` | Scopes insuficientes para la operación |

---

## 2. SCOPES - FORMATO Y CATÁLOGO

### 2.1 Formato Jerárquico de Scopes

Los scopes viven en el claim `scopes` del JWT. Son jerárquicos.

| Formato | Ejemplo | Descripción |
|---------|---------|-------------|
| `resource:action` | `agents:read` | Acceso a todos los recursos de un tipo |
| `resource:<id>:action` | `agents:my-agent:run` | Acceso a un recurso específico |
| `resource:*:action` | `agents:*:read` | Wildcard (equivale a global) |
| `agent_os:admin` | - | Acceso total a todos los endpoints |

**Restricción**: el scoping per-recurso (`resource:<id>:action`) aplica **solo** a `agents`, `teams`, `workflows`. El resto (sessions, memories, knowledge, traces) usa scopes globales únicamente.

### 2.2 Catálogo Completo de Scopes del AgentOS

#### 2.2.1 Scopes del Control Plane (`os.agno.com`)

| Scope | Descripción |
|-------|-------------|
| `os:read` | Ver instancias AgentOS |
| `os:write` | Crear/actualizar instancias AgentOS |
| `os:delete` | Eliminar instancias AgentOS |
| `org:read` | Ver detalles de organización |
| `org:write` | Actualizar organización |
| `org:delete` | Eliminar organización |
| `org:members:read` | Ver miembros |
| `org:members:write` | Invitar/actualizar miembros |
| `org:roles:read` | Ver roles y scopes asignados |
| `org:roles:write` | Crear/actualizar scopes de roles |
| `org:roles:delete` | Eliminar roles |
| `billing:read` | Ver facturación |
| `billing:write` | Actualizar facturación |

#### 2.2.2 AgentOS Scopes (enforced por el servicio desplegado)

**Config**:
| Scope | Endpoint | Descripción |
|-------|----------|-------------|
| `config:read` | `GET /config` | Leer config del OS |
| `config:read` | `GET /models` | Listar modelos disponibles |
| `config:write` | `POST /databases/all/migrate` | Migrar todas las DBs |
| `config:write` | `POST /databases/*/migrate` | Migrar DB específica |

**Registry**:
| Scope | Endpoint | Descripción |
|-------|----------|-------------|
| `registry:read` | `GET /registry` | Ver registry (tools, models, databases) |

**Components** (versionado):
| Scope | Endpoint | Descripción |
|-------|----------|-------------|
| `components:read` | `GET /components`, `GET /components/*`, `GET /components/*/configs*`, `GET /components/*/configs/current` | Listar/ver componentes y configs |
| `components:write` | `POST /components`, `POST /components/*/configs`, `POST /components/*/configs/*/set-current`, `PATCH /components/*`, `PATCH /components/*/configs/*` | Crear/actualizar componentes |
| `components:delete` | `DELETE /components/*`, `DELETE /components/*/configs/*` | Eliminar componentes |

**Agents**:
| Scope | Endpoint | Descripción |
|-------|----------|-------------|
| `agents:read` | `GET /agents`, `GET /agents/*` | Listar/ver agentes |
| `agents:write` | `POST /agents`, `PATCH /agents/*` | Crear/actualizar agentes |
| `agents:delete` | `DELETE /agents/*` | Eliminar agentes |
| `agents:run` | `POST /agents/*/runs`, `POST /agents/*/runs/*/continue`, `POST /agents/*/runs/*/cancel` | Ejecutar, continuar, cancelar runs |

**Teams**:
| Scope | Endpoint | Descripción |
|-------|----------|-------------|
| `teams:read` | `GET /teams`, `GET /teams/*` | Listar/ver teams |
| `teams:write` | `POST /teams`, `PATCH /teams/*` | Crear/actualizar teams |
| `teams:delete` | `DELETE /teams/*` | Eliminar teams |
| `teams:run` | `POST /teams/*/runs`, `POST /teams/*/runs/*/continue`, `POST /teams/*/runs/*/cancel` | Ejecutar/continuar/cancelar |

**Workflows**:
| Scope | Endpoint | Descripción |
|-------|----------|-------------|
| `workflows:read` | `GET /workflows`, `GET /workflows/*` | Listar/ver workflows |
| `workflows:write` | `POST /workflows`, `PATCH /workflows/*` | Crear/actualizar workflows |
| `workflows:delete` | `DELETE /workflows/*` | Eliminar workflows |
| `workflows:run` | `POST /workflows/*/runs`, `POST /workflows/*/runs/*/continue`, `POST /workflows/*/runs/*/cancel` | Ejecutar/continuar/cancelar |

**Sessions**:
| Scope | Endpoint | Descripción |
|-------|----------|-------------|
| `sessions:read` | `GET /sessions`, `GET /sessions/*` | Listar/ver sesiones |
| `sessions:write` | `POST /sessions`, `POST /sessions/*/rename`, `PATCH /sessions/*` | Crear/renombrar/actualizar |
| `sessions:delete` | `DELETE /sessions`, `DELETE /sessions/*` | Eliminar (bulk e individual) |

**Memories**:
| Scope | Endpoint | Descripción |
|-------|----------|-------------|
| `memories:read` | `GET /memories`, `GET /memories/*`, `GET /memory_topics`, `GET /user_memory_stats` | Listar/ver memorias, topics, stats |
| `memories:write` | `POST /memories`, `PATCH /memories/*`, `POST /optimize-memories` | Crear/actualizar/optimize |
| `memories:delete` | `DELETE /memories`, `DELETE /memories/*` | Eliminar memorias |

**Knowledge**:
| Scope | Endpoint | Descripción |
|-------|----------|-------------|
| `knowledge:read` | `GET /knowledge/content`, `GET /knowledge/content/*`, `GET /knowledge/config`, `GET /knowledge/*/sources`, `GET /knowledge/*/sources/*/files`, `POST /knowledge/search` | Listar/ver/buscar knowledge |
| `knowledge:write` | `POST /knowledge/content`, `POST /knowledge/remote-content`, `PATCH /knowledge/content/*` | Añadir/actualizar content |
| `knowledge:delete` | `DELETE /knowledge/content`, `DELETE /knowledge/content/*` | Eliminar content |

**Metrics**:
| Scope | Endpoint | Descripción |
|-------|----------|-------------|
| `metrics:read` | `GET /metrics` | Ver métricas |
| `metrics:write` | `POST /metrics/refresh` | Refrescar métricas |

**Evals**:
| Scope | Endpoint | Descripción |
|-------|----------|-------------|
| `evals:read` | `GET /eval-runs`, `GET /eval-runs/*` | Listar/ver eval runs |
| `evals:write` | `POST /eval-runs`, `PATCH /eval-runs/*` | Crear/actualizar eval runs |
| `evals:delete` | `DELETE /eval-runs` | Eliminar eval runs (bulk) |

**Traces**:
| Scope | Endpoint | Descripción |
|-------|----------|-------------|
| `traces:read` | `GET /traces`, `GET /traces/*`, `GET /trace_session_stats`, `POST /traces/search` | Listar/ver/buscar traces |

**Schedules**:
| Scope | Endpoint | Descripción |
|-------|----------|-------------|
| `schedules:read` | `GET /schedules`, `GET /schedules/*`, `GET /schedules/*/runs`, `GET /schedules/*/runs/*` | Listar/ver schedules y runs |
| `schedules:write` | `POST /schedules`, `PATCH /schedules/*`, `POST /schedules/*/enable`, `POST /schedules/*/disable`, `POST /schedules/*/trigger` | CRUD/enable/disable/trigger |
| `schedules:delete` | `DELETE /schedules/*` | Eliminar schedule |

**Approvals**:
| Scope | Endpoint | Descripción |
|-------|----------|-------------|
| `approvals:read` | `GET /approvals`, `GET /approvals/count`, `GET /approvals/*`, `GET /approvals/*/status` | Listar/contar/ver approvals |
| `approvals:write` | `POST /approvals/*/resolve` | Resolver approval |
| `approvals:delete` | `DELETE /approvals/*` | Eliminar approval |

#### 2.2.3 Scopes de Prerrequisito (gating)

Sin estos, los scopes finos no tienen efecto porque el usuario no puede alcanzar los recursos.

| Scope | Sin él, el usuario no puede |
|-------|------------------------------|
| `org:read` | Acceder a la organización |
| `os:read` | Listar instancias AgentOS |
| `config:read` | Usar cualquier endpoint (la UI carga `/config` al inicio) |

### 2.3 ScopeEnforcer

```python
# yaml-agno/src/security/scope_enforcer.py

from typing import List
from fastapi import Request, HTTPException

class ScopeEnforcer:
    """
    Verifica scopes requeridos contra los scopes del request.state.
    Soporta wildcard agents:*:action y admin bypass.
    """

    def __init__(self, admin_scope: str = "agent_os:admin"):
        self.admin_scope = admin_scope

    def enforce(self, request: Request, required: List[str]) -> None:
        held = getattr(request.state, "scopes", [])
        if self.admin_scope in held:
            return
        if not self._satisfies(held, required):
            raise HTTPException(status_code=403, detail="Insufficient scopes")

    @staticmethod
    def _satisfies(held: List[str], required: List[str]) -> bool:
        if not required:
            return True
        held_set = set(held)
        for r in required:
            if r in held_set:
                return True
            parts = r.split(":")
            if len(parts) == 3:
                wildcard = f"{parts[0]}:*:{parts[2]}"
                base = f"{parts[0]}:{parts[2]}"
                if wildcard in held_set or base in held_set:
                    return True
        return False
```

---

## 3. ROLES Y RBAC

### 3.1 Roles por Defecto

Los roles son bundles de scopes asignados a usuarios. yaml-agno define los tres roles por defecto del control plane y permite roles custom.

| Capabilidad | Owner | Administrator | Member |
|-------------|:-----:|:-------------:|:------:|
| Run agents, teams, workflows | ✓ | ✓ | ✓ |
| Create/update AgentOS resources | ✓ | ✓ | ✓ |
| Delete AgentOS resources | ✓ | ✓ | |
| Create/update AgentOS instances | ✓ | ✓ | ✓ |
| Delete AgentOS instances | ✓ | | |
| Manage members and roles | ✓ | ✓ | |
| Update organization settings | ✓ | ✓ | |
| View billing | ✓ | ✓ | ✓ |
| Update billing | ✓ | | |
| Delete the organization | ✓ | | |

### 3.2 Mapeo Rol → Scopes

```python
# yaml-agno/src/security/rbac.py

from typing import Dict, List, Set
from pydantic import BaseModel, Field

# Roles extendidos de yaml-agno (agrega developer y viewer al modelo Agno)
ROLE_SCOPES: Dict[str, Set[str]] = {
    "owner": {
        "agent_os:admin",
    },
    "administrator": {
        "os:read", "os:write",
        "org:read", "org:write", "org:members:read", "org:members:write",
        "org:roles:read", "org:roles:write",
        "billing:read", "billing:write",
        "config:read", "config:write",
        "registry:read", "components:read", "components:write", "components:delete",
        "agents:read", "agents:write", "agents:delete", "agents:run",
        "teams:read", "teams:write", "teams:delete", "teams:run",
        "workflows:read", "workflows:write", "workflows:delete", "workflows:run",
        "sessions:read", "sessions:write", "sessions:delete",
        "memories:read", "memories:write", "memories:delete",
        "knowledge:read", "knowledge:write", "knowledge:delete",
        "metrics:read", "metrics:write",
        "evals:read", "evals:write", "evals:delete",
        "traces:read",
        "schedules:read", "schedules:write", "schedules:delete",
        "approvals:read", "approvals:write", "approvals:delete",
    },
    "developer": {
        "config:read", "registry:read", "components:read", "components:write",
        "agents:read", "agents:write", "agents:run",
        "teams:read", "teams:write", "teams:run",
        "workflows:read", "workflows:write", "workflows:run",
        "sessions:read", "sessions:write",
        "memories:read", "memories:write",
        "knowledge:read", "knowledge:write",
        "metrics:read", "evals:read", "evals:write", "traces:read",
        "schedules:read", "schedules:write",
        "approvals:read", "approvals:write",
    },
    "member": {
        "config:read",
        "agents:read", "agents:run",
        "teams:read", "teams:run",
        "workflows:read", "workflows:run",
        "sessions:read", "sessions:write",
        "memories:read",
        "knowledge:read",
        "metrics:read", "evals:read", "traces:read",
        "billing:read",
    },
    "viewer": {
        "config:read",
        "agents:read", "teams:read", "workflows:read",
        "sessions:read", "memories:read", "knowledge:read",
        "metrics:read", "evals:read", "traces:read",
    },
}

class RoleMapping(BaseModel):
    role: str
    scopes: List[str] = Field(default_factory=list)
    description: str = ""

class RBACManager:
    """
    Resuelve roles a scopes.
    Permite roles custom definidos en YAML.
    """

    def __init__(self, custom_roles: Dict[str, Set[str]] | None = None):
        self.roles = {**ROLE_SCOPES}
        if custom_roles:
            self.roles.update(custom_roles)

    def scopes_for(self, roles: List[str]) -> Set[str]:
        result: Set[str] = set()
        for r in roles:
            result.update(self.roles.get(r, set()))
        return result

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def list_roles(self) -> List[str]:
        return sorted(self.roles.keys())
```

### 3.3 Custom Roles

```yaml
security:
  rbac:
    roles:
      - name: data_scientist
        scopes:
          - config:read
          - agents:read
          - agents:*:run          # wildcard: correr cualquier agente
          - evals:read
          - evals:write
          - traces:read
        description: "DS con acceso a evals y traces"
      - name: ops_readonly
        scopes:
          - config:read
          - metrics:read
          - traces:read
          - traces:search
        description: "Solo observabilidad"
```

---

## 4. PER-USER DATA ISOLATION

### 4.1 Concepto

La autorización controla **qué operaciones** puede hacer un caller. El aislamiento per-user controla **qué filas** puede ver y escribir. Se activa con `user_isolation=True`.

```python
# yaml-agno/src/security/user_isolation.py

from fastapi import Request

class UserIsolationEnforcer:
    """
    Cuando user_isolation=True, los callers no-admin solo ven/escriben
    filas asociadas a su JWT sub (user_id).

    Operaciones afectadas:
    - Reads (sessions, memories, traces): scoped a caller.user_id
    - Writes: user_id se coacciona al sub del caller
    - Cancel/resume/continue: requieren session_id y verifican ownership
    - WebSocket reconnect: requiere session_id para no-admins
    """

    def __init__(self, admin_scope: str = "agent_os:admin"):
        self.admin_scope = admin_scope

    def effective_user_id(self, request: Request, requested_user_id: str | None) -> str:
        """Coacciona user_id: no-admin no puede atribuir filas a otro usuario."""
        if getattr(request.state, "is_admin", False):
            return requested_user_id or request.state.user_id
        return request.state.user_id   # SIEMPRE el sub del caller

    def can_access_resource(self, request: Request, resource_user_id: str) -> bool:
        if getattr(request.state, "is_admin", False):
            return True
        return resource_user_id == request.state.user_id

    def owns_session(self, request: Request, session_user_id: str) -> bool:
        if getattr(request.state, "is_admin", False):
            return True
        return session_user_id == request.state.user_id
```

### 4.2 Comportamiento por Operación

| Operación | Comportamiento con `user_isolation=True` |
|-----------|------------------------------------------|
| Reads (sessions, memory, traces) | Scoped al `user_id` del caller. Filas de otros usuarios no se retornan |
| Writes (sessions, memories, traces) | `user_id` se coacciona al `sub` del caller. No puede atribuir filas a otro |
| Cancel / resume / continue | Requiere `session_id` y verifica ownership del run |
| WebSocket reconnect | Requiere `session_id` (y `workflow_id`) para no-admins |

### 4.3 Admin Bypass

Un caller con `admin_scope` (default `agent_os:admin`) **bypassa** el aislamiento y ve todos los datos. Customizable con `admin_scope="ops:admin"`.

### 4.4 Requisito de DB

El aislamiento requiere una DB que registre `user_id`. PostgreSQL recomendado para producción (ver SPEC_03). Sin `user_id` en filas, el aislamiento no tiene efecto.

---

## 5. CORS Y SECURITY HEADERS

### 5.1 CORS

```python
# yaml-agno/src/security/cors.py

from fastapi.middleware.cors import CORSMiddleware

DEFAULT_AGNO_ORIGINS = [
    "https://os.agno.com",
]

class CorsConfigurator:
    """
    Configura CORSMiddleware.
    cors_allowed_origins se merguea con los dominios default de Agno.
    """

    def __init__(self, allowed_origins: list[str] | None = None):
        self.allowed_origins = list(set(DEFAULT_AGNO_ORIGINS + (allowed_origins or [])))

    def apply(self, app) -> None:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["*"],
        )
```

### 5.2 Security Headers Middleware

```python
# yaml-agno/src/security/security_headers.py

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Headers de seguridad HTTP estándar.
    HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy.
    """

    DEFAULT_HEADERS = {
        "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        "X-XSS-Protection": "1; mode=block",
    }

    def __init__(self, app, csp: str | None = None, extra: dict | None = None):
        super().__init__(app)
        self.headers = {**self.DEFAULT_HEADERS}
        if csp:
            self.headers["Content-Security-Policy"] = csp
        if extra:
            self.headers.update(extra)

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for k, v in self.headers.items():
            response.headers[k] = v
        return response
```

| Header | Default | Descripción |
|--------|---------|-------------|
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` | HSTS 2 años |
| `X-Content-Type-Options` | `nosniff` | Anti-MIME sniffing |
| `X-Frame-Options` | `DENY` | Anti-clickjacking |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Control de referrer |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` | Deshabilita APIs sensibles |
| `Content-Security-Policy` | configurable | CSP (default none salvo config) |

---

## 6. CATÁLOGO EXHAUSTIVO DE ENDPOINTS

### 6.1 Resumen por Grupo

| Grupo | Qué permite |
|-------|-------------|
| **Runs** | Crear, listar, cancelar, continuar runs pausados, resumir streams. Stream SSE o background jobs |
| **Sessions** | Crear, listar, renombrar, actualizar, eliminar. Scoped por usuario |
| **Memory** | Crear, actualizar, eliminar memorias. Search, filter por topic, stats. Optimize |
| **Knowledge** | Upload files/text/URLs/S3/GCS/SharePoint/GitHub. Vector/keyword/hybrid search |
| **Evals** | Accuracy, agent-as-judge, performance, reliability. List/update/delete |
| **Traces** | Listar, buscar con filter DSL, ver span trees, group por session |
| **Metrics** | Agregados diarios: runs, sessions, users, tokens, breakdown por modelo |
| **Schedules** | CRUD, enable, disable, trigger now. Listar runs históricos |
| **Approvals** | Listar pendientes, resolver, contar por usuario |
| **Components** | Versionar agents/teams/workflows. Drafts, publish, rollback |
| **Database** | Migrar schemas a versión target |
| **Registry** | Ver registry code-defined (tools, models, databases) |
| **A2A** | Agent-to-Agent server |
| **AG-UI** | AG-UI interface |
| **Slack/WhatsApp** | Interfaces de mensajería |
| **Health** | Liveness, readiness, root |

### 6.2 Endpoints Detail (non-run groups ya en §2.2; aquí runs + interfaces)

#### Runs (Agents/Teams/Workflows comparten forma)

| Método | Endpoint | Descripción | Scope |
|--------|----------|-------------|-------|
| POST | `/agents/{id}/runs` | Crear run (multipart: text, files, media) | `agents:run` |
| POST | `/teams/{id}/runs` | Crear run de team | `teams:run` |
| POST | `/workflows/{id}/runs` | Crear run de workflow | `workflows:run` |
| POST | `/agents/{id}/runs/{run_id}/continue` | Continuar run pausado | `agents:run` |
| POST | `/agents/{id}/runs/{run_id}/cancel` | Cancelar run | `agents:run` |
| GET | `/agents/{id}/runs` | Listar runs | `agents:read` |

**Request shape** (multipart/form-data):
```bash
curl -X POST http://localhost:8000/agents/my-agent/runs \
  -F "message=Hello" \
  -F "user_id=alice" \
  -F "session_id=thread-42" \
  -F "stream=false" \
  -F "background=false"
```

**Response shape** (uniforme agent/team/workflow):
```json
{
  "run_id": "run_abc123",
  "session_id": "thread-42",
  "user_id": "alice",
  "agent_id": "my-agent",
  "status": "completed",
  "content": "Hi Alice!",
  "created_at": "2026-04-24T20:15:00Z"
}
```

`stream=true` → Server-Sent Events. `background=true` → run async + poll.

#### Interfaces

| Interfaz | Config | Descripción |
|----------|--------|-------------|
| REST | default on | `/agents/*/runs` etc. |
| SSE | default on | `stream=true` |
| MCP | `enable_mcp_server=True` | Model Context Protocol server |
| WebSocket | opt-in | Streaming bidireccional |
| A2A | `a2a_interface=True` | Agent-to-Agent server |
| AG-UI | opt-in | AG-UI interface |
| Slack | opt-in | Slack interface |
| WhatsApp | opt-in | WhatsApp interface |

### 6.3 EndpointRegistry

```python
# yaml-agno/src/api/endpoint_registry.py

from typing import List, Optional
import re

class EndpointRegistry:
    """
    Catalogo de rutas -> scopes requeridos.
    Resuelve el scope de una ruta+metodo dado.
    Soporta wildcards (* y {param}).
    """

    # (method, pattern, scopes)
    _MAPPINGS = [
        # Config
        ("GET",    r"^/config$",                          ["config:read"]),
        ("GET",    r"^/models$",                           ["config:read"]),
        ("POST",   r"^/databases/all/migrate$",            ["config:write"]),
        ("POST",   r"^/databases/[^/]+/migrate$",          ["config:write"]),
        # Registry
        ("GET",    r"^/registry$",                         ["registry:read"]),
        # Components
        ("GET",    r"^/components$",                       ["components:read"]),
        ("GET",    r"^/components/[^/]+$",                 ["components:read"]),
        ("GET",    r"^/components/[^/]+/configs$",         ["components:read"]),
        ("GET",    r"^/components/[^/]+/configs/[^/]+$",   ["components:read"]),
        ("GET",    r"^/components/[^/]+/configs/current$", ["components:read"]),
        ("POST",   r"^/components$",                       ["components:write"]),
        ("POST",   r"^/components/[^/]+/configs$",         ["components:write"]),
        ("POST",   r"^/components/[^/]+/configs/[^/]+/set-current$", ["components:write"]),
        ("PATCH",  r"^/components/[^/]+$",                 ["components:write"]),
        ("PATCH",  r"^/components/[^/]+/configs/[^/]+$",   ["components:write"]),
        ("DELETE", r"^/components/[^/]+$",                 ["components:delete"]),
        ("DELETE", r"^/components/[^/]+/configs/[^/]+$",   ["components:delete"]),
        # Agents
        ("GET",    r"^/agents$",                           ["agents:read"]),
        ("GET",    r"^/agents/[^/]+$",                     ["agents:read"]),
        ("POST",   r"^/agents$",                           ["agents:write"]),
        ("PATCH",  r"^/agents/[^/]+$",                     ["agents:write"]),
        ("DELETE", r"^/agents/[^/]+$",                     ["agents:delete"]),
        ("POST",   r"^/agents/[^/]+/runs$",                ["agents:run"]),
        ("POST",   r"^/agents/[^/]+/runs/[^/]+/continue$", ["agents:run"]),
        ("POST",   r"^/agents/[^/]+/runs/[^/]+/cancel$",   ["agents:run"]),
        # Teams
        ("GET",    r"^/teams$",                            ["teams:read"]),
        ("GET",    r"^/teams/[^/]+$",                      ["teams:read"]),
        ("POST",   r"^/teams$",                            ["teams:write"]),
        ("PATCH",  r"^/teams/[^/]+$",                      ["teams:write"]),
        ("DELETE", r"^/teams/[^/]+$",                      ["teams:delete"]),
        ("POST",   r"^/teams/[^/]+/runs$",                 ["teams:run"]),
        ("POST",   r"^/teams/[^/]+/runs/[^/]+/continue$",  ["teams:run"]),
        ("POST",   r"^/teams/[^/]+/runs/[^/]+/cancel$",    ["teams:run"]),
        # Workflows
        ("GET",    r"^/workflows$",                        ["workflows:read"]),
        ("GET",    r"^/workflows/[^/]+$",                  ["workflows:read"]),
        ("POST",   r"^/workflows$",                        ["workflows:write"]),
        ("PATCH",  r"^/workflows/[^/]+$",                  ["workflows:write"]),
        ("DELETE", r"^/workflows/[^/]+$",                  ["workflows:delete"]),
        ("POST",   r"^/workflows/[^/]+/runs$",             ["workflows:run"]),
        ("POST",   r"^/workflows/[^/]+/runs/[^/]+/continue$", ["workflows:run"]),
        ("POST",   r"^/workflows/[^/]+/runs/[^/]+/cancel$",   ["workflows:run"]),
        # Sessions
        ("GET",    r"^/sessions$",                         ["sessions:read"]),
        ("GET",    r"^/sessions/[^/]+$",                   ["sessions:read"]),
        ("POST",   r"^/sessions$",                         ["sessions:write"]),
        ("POST",   r"^/sessions/[^/]+/rename$",            ["sessions:write"]),
        ("PATCH",  r"^/sessions/[^/]+$",                   ["sessions:write"]),
        ("DELETE", r"^/sessions$",                         ["sessions:delete"]),
        ("DELETE", r"^/sessions/[^/]+$",                   ["sessions:delete"]),
        # Memories
        ("GET",    r"^/memories$",                         ["memories:read"]),
        ("GET",    r"^/memories/[^/]+$",                   ["memories:read"]),
        ("GET",    r"^/memory_topics$",                    ["memories:read"]),
        ("GET",    r"^/user_memory_stats$",                ["memories:read"]),
        ("POST",   r"^/memories$",                         ["memories:write"]),
        ("PATCH",  r"^/memories/[^/]+$",                   ["memories:write"]),
        ("POST",   r"^/optimize-memories$",                ["memories:write"]),
        ("DELETE", r"^/memories$",                         ["memories:delete"]),
        ("DELETE", r"^/memories/[^/]+$",                   ["memories:delete"]),
        # Knowledge
        ("GET",    r"^/knowledge/content$",                ["knowledge:read"]),
        ("GET",    r"^/knowledge/content/[^/]+$",          ["knowledge:read"]),
        ("GET",    r"^/knowledge/config$",                 ["knowledge:read"]),
        ("GET",    r"^/knowledge/[^/]+/sources$",          ["knowledge:read"]),
        ("GET",    r"^/knowledge/[^/]+/sources/[^/]+/files$", ["knowledge:read"]),
        ("POST",   r"^/knowledge/search$",                 ["knowledge:read"]),
        ("POST",   r"^/knowledge/content$",                ["knowledge:write"]),
        ("POST",   r"^/knowledge/remote-content$",         ["knowledge:write"]),
        ("PATCH",  r"^/knowledge/content/[^/]+$",          ["knowledge:write"]),
        ("DELETE", r"^/knowledge/content$",                ["knowledge:delete"]),
        ("DELETE", r"^/knowledge/content/[^/]+$",          ["knowledge:delete"]),
        # Metrics
        ("GET",    r"^/metrics$",                          ["metrics:read"]),
        ("POST",   r"^/metrics/refresh$",                  ["metrics:write"]),
        # Evals
        ("GET",    r"^/eval-runs$",                        ["evals:read"]),
        ("GET",    r"^/eval-runs/[^/]+$",                  ["evals:read"]),
        ("POST",   r"^/eval-runs$",                        ["evals:write"]),
        ("PATCH",  r"^/eval-runs/[^/]+$",                  ["evals:write"]),
        ("DELETE", r"^/eval-runs$",                        ["evals:delete"]),
        # Traces
        ("GET",    r"^/traces$",                           ["traces:read"]),
        ("GET",    r"^/traces/[^/]+$",                     ["traces:read"]),
        ("GET",    r"^/trace_session_stats$",              ["traces:read"]),
        ("POST",   r"^/traces/search$",                    ["traces:read"]),
        # Schedules
        ("GET",    r"^/schedules$",                        ["schedules:read"]),
        ("GET",    r"^/schedules/[^/]+$",                  ["schedules:read"]),
        ("GET",    r"^/schedules/[^/]+/runs$",             ["schedules:read"]),
        ("GET",    r"^/schedules/[^/]+/runs/[^/]+$",       ["schedules:read"]),
        ("POST",   r"^/schedules$",                        ["schedules:write"]),
        ("PATCH",  r"^/schedules/[^/]+$",                  ["schedules:write"]),
        ("POST",   r"^/schedules/[^/]+/enable$",           ["schedules:write"]),
        ("POST",   r"^/schedules/[^/]+/disable$",          ["schedules:write"]),
        ("POST",   r"^/schedules/[^/]+/trigger$",          ["schedules:write"]),
        ("DELETE", r"^/schedules/[^/]+$",                  ["schedules:delete"]),
        # Approvals
        ("GET",    r"^/approvals$",                        ["approvals:read"]),
        ("GET",    r"^/approvals/count$",                  ["approvals:read"]),
        ("GET",    r"^/approvals/[^/]+$",                  ["approvals:read"]),
        ("GET",    r"^/approvals/[^/]+/status$",           ["approvals:read"]),
        ("POST",   r"^/approvals/[^/]+/resolve$",          ["approvals:write"]),
        ("DELETE", r"^/approvals/[^/]+$",                  ["approvals:delete"]),
    ]

    @classmethod
    def required_scopes(cls, method: str, path: str) -> Optional[List[str]]:
        for m, pattern, scopes in cls._MAPPINGS:
            if m == method and re.match(pattern, path):
                return scopes
        return None   # ruta no catalogada: default deny o custom mapping
```

### 6.4 Custom Scope Mappings

```python
# Aditivo a los defaults. Para override, especificar mismo patron.
scope_mappings = {
    "POST /custom/endpoint": ["custom:write"],
    "GET /custom/data":      ["custom:read"],
    "GET /public/stats":     [],   # sin scopes requeridos
}
```

**Nota**: las rutas built-in (`/agents`, `/teams`, `/workflows`) re-chequean scopes contra su namespace nativo. Mapear `GET /agents` a `custom:read` no otorga acceso porque el handler requiere `agents:read`. La libertad total aplica solo a rutas nuevas.

---

## 7. AUDIT TRAIL

### 7.1 Security Audit Log

Todo evento de auth/authorization se registra para auditoría.

```python
# yaml-agno/src/security/audit.py

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from pydantic import BaseModel, Field

class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str           # auth.success | auth.failed | authz.denied | isolation.coerced
    user_id: Optional[str] = None
    method: str = ""
    path: str = ""
    ip_address: Optional[str] = None
    scopes: list[str] = Field(default_factory=list)
    required_scopes: list[str] = Field(default_factory=list)
    status_code: int = 200
    details: dict = Field(default_factory=dict)

class AuditLogger:
    """Persiste eventos de seguridad en tabla audit_events."""

    def __init__(self, db):
        self.db = db

    async def log(self, event: AuditEvent) -> None:
        # INSERT en audit_events (ver SPEC_03)
        ...

# Eventos registrados:
# - auth.success:   JWT valido, request autorizado
# - auth.failed:    401 (token ausente/expirado/invalido/audience)
# - authz.denied:   403 (scopes insuficientes)
# - isolation.coerced: user_id coaccionado al sub del caller
```

### 7.2 Flujo de un Request con Auth

```mermaid
sequenceDiagram
    participant C as Client
    participant R as RateLimiter (SPEC_06)
    participant J as JWTMiddleware
    participant E as ScopeEnforcer
    participant I as UserIsolation
    participant H as Handler
    participant A as AuditLogger

    C->>R: POST /agents/x/runs (Bearer JWT)
    R->>R: check tenant/IP buckets
    R->>J: pass
    J->>J: decode + verify sig/exp/aud
    J->>J: extract scopes, user_id
    J->>E: enforce required scopes
    alt scopes insuficientes
        E-->>C: 403 Forbidden
        E->>A: log authz.denied
    else ok
        E->>I: apply user_isolation
        I->>H: handler(coerced user_id)
        H-->>C: 200 result
        H->>A: log auth.success
    end
```

---

## 8. YAML SCHEMAS DE API SURFACE Y SECURITY

### 8.1 Schema Security Completo

```yaml
# yaml-agno/config/security.yaml
security:
  auth_mode: jwt               # jwt | basic | none

  basic_auth:
    security_key: ${OS_SECURITY_KEY}

  jwt:
    algorithm: RS256           # RS256 | HS256 | ES256 | ...
    verification_keys:
      - ${JWT_VERIFICATION_KEY}
    jwks_file: null            # path a JWKS si se usa
    validate: true
    authorization: true        # enforce scopes
    token_source: header       # header | cookie | both
    cookie_name: access_token
    scopes_claim: scopes
    user_id_claim: sub
    session_id_claim: session_id
    audience_claim: aud
    audience: my-agent-os
    verify_audience: false
    admin_scope: agent_os:admin
    user_isolation: true       # aislar datos por user_id
    excluded_routes:
      - /
      - /health
      - /liveness
      - /readiness
      - /docs
      - /openapi.json
    scope_mappings:
      "POST /custom/endpoint": ["custom:write"]
      "GET /public/stats": []

  cors:
    allowed_origins:
      - https://app.example.com
      - http://localhost:3000

  security_headers:
    csp: "default-src 'self'; script-src 'self'"
    hsts_max_age: 63072000

  audit:
    enabled: true
    log_denials: true
    log_coercions: true
```

### 8.2 Schema RBAC

```yaml
# (incluido en security.yaml o separado)
rbac:
  roles:
    - name: data_scientist
      scopes:
        - config:read
        - agents:read
        - agents:*:run
        - evals:read
        - evals:write
        - traces:read
      description: "DS con acceso a evals y traces"
    - name: ops_readonly
      scopes:
        - config:read
        - metrics:read
        - traces:read
      description: "Solo observabilidad"

  users:
    - user_id: alice@corp.com
      roles: [administrator]
    - user_id: bob@corp.com
      roles: [developer, data_scientist]
    - user_id: carol@corp.com
      roles: [viewer]
```

### 8.3 Schema API Surface

```yaml
# yaml-agno/config/api.yaml
api:
  version: v1
  base_path: ""                # AgentOS monta en raiz
  interfaces:
    rest: true
    sse: true
    websocket: false
    mcp_server: false          # enable_mcp_server
    a2a: false                 # a2a_interface
    agui: false
    slack: false
    whatsapp: false

  rate_limiting:
    enabled: true
    tenant_limit_per_min: 100  # ver SPEC_06 §1.4
    ip_limit_per_min: 20

  run_defaults:
    stream: false
    background: false
```

### 8.4 Pydantic Models de Config

```python
# yaml-agno/src/config/security_config.py

from typing import Optional, List, Union
from pydantic import BaseModel, Field

class BasicAuthConfig(BaseModel):
    security_key: Optional[str] = None

class JwtConfig(BaseModel):
    algorithm: str = "RS256"
    verification_keys: List[str] = Field(default_factory=list)
    jwks_file: Optional[str] = None
    validate: bool = True
    authorization: bool = False
    token_source: str = "header"
    cookie_name: str = "access_token"
    scopes_claim: str = "scopes"
    user_id_claim: str = "sub"
    session_id_claim: str = "session_id"
    audience_claim: str = "aud"
    audience: Optional[Union[str, List[str]]] = None
    verify_audience: bool = False
    admin_scope: str = "agent_os:admin"
    user_isolation: bool = False
    excluded_routes: List[str] = Field(default_factory=lambda: [
        "/", "/health", "/liveness", "/readiness",
        "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect",
    ])
    scope_mappings: dict[str, List[str]] = Field(default_factory=dict)

class CorsConfig(BaseModel):
    allowed_origins: List[str] = Field(default_factory=list)

class SecurityHeadersConfig(BaseModel):
    csp: Optional[str] = None
    hsts_max_age: int = 63072000

class AuditConfig(BaseModel):
    enabled: bool = True
    log_denials: bool = True
    log_coercions: bool = True

class RoleDef(BaseModel):
    name: str
    scopes: List[str] = Field(default_factory=list)
    description: str = ""

class UserDef(BaseModel):
    user_id: str
    roles: List[str] = Field(default_factory=list)

class RbacConfig(BaseModel):
    roles: List[RoleDef] = Field(default_factory=list)
    users: List[UserDef] = Field(default_factory=list)

class SecurityConfig(BaseModel):
    auth_mode: str = "none"     # jwt | basic | none
    basic_auth: BasicAuthConfig = Field(default_factory=BasicAuthConfig)
    jwt: JwtConfig = Field(default_factory=JwtConfig)
    cors: CorsConfig = Field(default_factory=CorsConfig)
    security_headers: SecurityHeadersConfig = Field(default_factory=SecurityHeadersConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    rbac: RbacConfig = Field(default_factory=RbacConfig)
```

---

## 9. ALGORITMOS JWT SOPORTADOS

| Algoritmo | Tipo | Formato de Key |
|-----------|------|-----------------|
| `RS256` | Asimétrico (RSA) | Public key (PEM) |
| `RS384` | Asimétrico (RSA) | Public key (PEM) |
| `RS512` | Asimétrico (RSA) | Public key (PEM) |
| `HS256` | Simétrico (HMAC) | Shared secret |
| `HS384` | Simétrico (HMAC) | Shared secret |
| `HS512` | Simétrico (HMAC) | Shared secret |
| `ES256` | Asimétrico (ECDSA) | Public key (PEM) |
| `ES384` | Asimétrico (ECDSA) | Public key (PEM) |
| `ES512` | Asimétrico (ECDSA) | Public key (PEM) |

**Multiple issuers**: `verification_keys` es una lista. Se prueba cada key en orden hasta que una verifica. Útil para aceptar tokens del control plane + propio backend simultáneamente. Todas las keys deben usar el mismo `algorithm`.

**JWKS vs verification_keys**: alternativos, no se apilan. Si hay mix, JWKS primero (por `kid`), luego verification_keys como fallback.

---

## 10. BEHAVIOR DELTA - BDD SCENARIOS

### 10.1 JWT Auth

```gherkin
Scenario 1: Golden Path - JWT valido autoriza request
  GIVEN auth_mode=jwt y authorization=true
  AND un JWT firmado con RS256 conteniendo {sub: "alice", scopes: ["agents:run", "agents:read"]}
  WHEN POST /agents/my-agent/runs con header Authorization: Bearer <jwt>
  THEN el JWTMiddleware extrae y verifica la firma
  AND request.state.user_id es "alice"
  AND request.state.scopes contiene "agents:run"
  AND el ScopeEnforcer permite la operacion
  AND el handler ejecuta con user_id coaccionado a "alice"
  AND la respuesta es 200
  Y se loguea audit event auth.success
```

```gherkin
Scenario 2: Token ausente -> 401
  GIVEN auth_mode=jwt
  WHEN POST /agents/my-agent/runs sin header Authorization
  THEN la respuesta es 401 Unauthorized
  AND el detalle menciona "Missing JWT token"
  Y se loguea audit event auth.failed
```

```gherkin
Scenario 3: Token expirado -> 401
  GIVEN un JWT con exp en el pasado
  WHEN el request llega
  THEN la respuesta es 401 Unauthorized
  AND el detalle menciona "Token expired"
```

```gherkin
Scenario 4: Audience invalido -> 401
  GIVEN verify_audience=true y audience="my-agent-os"
  AND un JWT con aud="otro-os"
  WHEN el request llega
  THEN la respuesta es 401 Unauthorized
  AND el detalle menciona "Invalid audience"
```

### 10.2 Scope Enforcement

```gherkin
Scenario 5: Scope suficiente permite
  GIVEN un JWT con scopes ["agents:read"]
  WHEN GET /agents
  THEN el ScopeEnforcer permite (required: agents:read)
  AND la respuesta es 200
```

```gherkin
Scenario 6: Scope insuficiente -> 403
  GIVEN un JWT con scopes ["agents:read"]
  WHEN POST /agents/my-agent/runs (required: agents:run)
  THEN la respuesta es 403 Forbidden
  AND el detalle menciona "Insufficient scopes"
  Y se loguea audit event authz.denied
```

```gherkin
Scenario 7: Wildcard agents:*:run satisface
  GIVEN un JWT con scopes ["agents:*:run"]
  WHEN POST /agents/my-agent/runs
  THEN el ScopeEnforcer permite (wildcard match)
  AND la respuesta es 200
```

```gherkin
Scenario 8: Per-resource scope permite solo ese recurso
  GIVEN un JWT con scopes ["agents:web-agent:run"]
  WHEN POST /agents/web-agent/runs
  THEN la respuesta es 200
  WHEN POST /agents/other-agent/runs
  THEN la respuesta es 403 Forbidden
```

```gherkin
Scenario 9: admin_scope bypassa verificacion
  GIVEN un JWT con scopes ["agent_os:admin"]
  WHEN POST /agents/my-agent/runs
  THEN el ScopeEnforcer bypassa (admin)
  AND la respuesta es 200
  Y user_isolation NO aplica (admin ve todo)
```

### 10.3 Per-User Isolation

```gherkin
Scenario 10: Non-admin solo ve sus sesiones
  GIVEN user_isolation=true
  AND alice (no-admin) pide GET /sessions
  THEN solo se retornan sesiones con user_id="alice"
  AND las sesiones de bob no aparecen
```

```gherkin
Scenario 11: Write coacciona user_id al sub del caller
  GIVEN user_isolation=true
  AND alice (no-admin) hace POST /sessions con body user_id="bob"
  WHEN el UserIsolationEnforcer procesa
  THEN la sesion se persiste con user_id="alice"
  Y se loguea audit event isolation.coerced
```

```gherkin
Scenario 12: Admin bypassa isolation
  GIVEN user_isolation=true
  AND admin hace GET /sessions
  THEN se retornan TODAS las sesiones (sin scope por user_id)
```

```gherkin
Scenario 13: Cancel run requiere ownership
  GIVEN user_isolation=true
  AND alice hace POST /agents/x/runs/r1/cancel
  AND el run r1 pertenece a bob
  THEN la verificacion de ownership falla
  Y la respuesta es 403 Forbidden
```

### 10.4 Basic Auth y CORS

```gherkin
Scenario 14: Basic auth con key valido
  GIVEN auth_mode=basic y OS_SECURITY_KEY="secret123"
  WHEN request con Authorization: Bearer secret123
  THEN request.state.authenticated es true
  Y request.state.scopes contiene agent_os:admin (acceso total)
```

```gherkin
Scenario 15: CORS allowed origin
  GIVEN cors.allowed_origins=["https://app.example.com"]
  WHEN OPTIONS preflight desde https://app.example.com
  THEN la respuesta incluye Access-Control-Allow-Origin: https://app.example.com
  Y los dominios default de Agno tambien estan permitidos
```

```gherkin
Scenario 16: Security headers presentes
  GIVEN SecurityHeadersMiddleware activo
  WHEN cualquier response
  THEN incluye Strict-Transport-Security
  AND incluye X-Content-Type-Options: nosniff
  AND incluye X-Frame-Options: DENY
```

---

## 11. TDD MICRO-TASK EXECUTION PROTOCOL

Strict TDD RED/GREEN/REFACTOR.

### TASK_001: BasicAuthMiddleware
- **File**: `yaml-agno/src/security/basic_auth.py`
- **Test**: `tests/unit/security/test_basic_auth.py`
- **RED**:
  ```python
  async def test_basic_auth_valid_key():
      mw = BasicAuthMiddleware(security_key="secret")
      req = FakeRequest(headers={"Authorization": "Bearer secret"})
      await mw(req)
      assert req.state.authenticated is True

  async def test_basic_auth_invalid_key():
      mw = BasicAuthMiddleware(security_key="secret")
      import pytest
      from fastapi import HTTPException
      req = FakeRequest(headers={"Authorization": "Bearer wrong"})
      with pytest.raises(HTTPException) as e:
          await mw(req)
      assert e.value.status_code == 401

  async def test_basic_auth_missing_key():
      mw = BasicAuthMiddleware(security_key="secret")
      req = FakeRequest(headers={})
      with pytest.raises(HTTPException) as e:
          await mw(req)
      assert e.value.status_code == 401
  ```
- **GREEN**: Implementar `BasicAuthMiddleware`.
- **Commit**: `feat(security): add basic auth middleware`

### TASK_002: JWTMiddleware - extraccion y decode
- **File**: `yaml-agno/src/security/jwt_middleware.py`
- **Test**: `tests/unit/security/test_jwt_middleware.py`
- **RED**:
  ```python
  async def test_jwt_valid_populates_state():
      token = make_jwt(sub="alice", scopes=["agents:read"], key=KEY, algorithm="HS256")
      mw = JWTMiddleware(verification_keys=[KEY], algorithm="HS256")
      req = FakeRequest(headers={"Authorization": f"Bearer {token}"})
      await mw(req)
      assert req.state.user_id == "alice"
      assert "agents:read" in req.state.scopes

  async def test_jwt_expired_401():
      token = make_jwt(exp=past_timestamp, key=KEY, algorithm="HS256")
      mw = JWTMiddleware(verification_keys=[KEY], algorithm="HS256")
      req = FakeRequest(headers={"Authorization": f"Bearer {token}"})
      with pytest.raises(HTTPException) as e:
          await mw(req)
      assert e.value.status_code == 401

  async def test_jwt_excluded_route_skips():
      mw = JWTMiddleware(verification_keys=[KEY], algorithm="HS256")
      req = FakeRequest(path="/health", headers={})
      await mw(req)
      assert req.state.authenticated is False
  ```
- **GREEN**: Implementar `JWTMiddleware.__call__`, `_decode`, `_extract_token`.
- **Commit**: `feat(security): add jwt middleware with decode`

### TASK_003: JWTMiddleware - token sources (header/cookie/both)
- **File**: `yaml-agno/src/security/jwt_middleware.py`
- **Test**: `tests/unit/security/test_jwt_token_source.py`
- **RED**:
  ```python
  async def test_token_from_cookie():
      token = make_jwt(sub="alice", key=KEY, algorithm="HS256")
      mw = JWTMiddleware(verification_keys=[KEY], algorithm="HS256",
                         token_source=TokenSource.COOKIE, cookie_name="access_token")
      req = FakeRequest(cookies={"access_token": token})
      await mw(req)
      assert req.state.user_id == "alice"

  async def test_token_both_header_first():
      mw = JWTMiddleware(verification_keys=[KEY], algorithm="HS256",
                         token_source=TokenSource.BOTH)
      # header presente, cookie tambien; header gana
      ...
  ```
- **GREEN**: Implementar `_extract_token` con los 3 modos.
- **Commit**: `feat(security): add jwt token source variants`

### TASK_004: JWTMiddleware - multiple verification keys + audience
- **File**: `yaml-agno/src/security/jwt_middleware.py`
- **Test**: `tests/unit/security/test_jwt_multi_key.py`
- **RED**:
  ```python
  async def test_multi_key_tries_in_order():
      mw = JWTMiddleware(verification_keys=[KEY_A, KEY_B], algorithm="HS256")
      token_b = make_jwt(key=KEY_B, algorithm="HS256", sub="x")
      req = FakeRequest(headers={"Authorization": f"Bearer {token_b}"})
      await mw(req)
      assert req.state.user_id == "x"

  async def test_audience_mismatch_401():
      mw = JWTMiddleware(verification_keys=[KEY], algorithm="HS256",
                         audience="my-os", verify_audience=True)
      token = make_jwt(aud="other-os", key=KEY, algorithm="HS256")
      with pytest.raises(HTTPException) as e:
          await mw(FakeRequest(headers={"Authorization": f"Bearer {token}"}))
      assert e.value.status_code == 401
  ```
- **GREEN**: Implementar loop de keys y verificación de audience.
- **Commit**: `feat(security): add multi-key and audience verification`

### TASK_005: ScopeEnforcer
- **File**: `yaml-agno/src/security/scope_enforcer.py`
- **Test**: `tests/unit/security/test_scope_enforcer.py`
- **RED**:
  ```python
  def test_enforce_sufficient():
      enforcer = ScopeEnforcer()
      req = FakeRequest(scopes=["agents:read"])
      enforcer.enforce(req, ["agents:read"])   # no raise

  def test_enforce_insufficient_403():
      enforcer = ScopeEnforcer()
      req = FakeRequest(scopes=["agents:read"])
      with pytest.raises(HTTPException) as e:
          enforcer.enforce(req, ["agents:run"])
      assert e.value.status_code == 403

  def test_enforce_admin_bypass():
      enforcer = ScopeEnforcer()
      req = FakeRequest(scopes=["agent_os:admin"])
      enforcer.enforce(req, ["agents:run"])   # no raise

  def test_enforce_wildcard():
      enforcer = ScopeEnforcer()
      req = FakeRequest(scopes=["agents:*:run"])
      enforcer.enforce(req, ["agents:my-agent:run"])   # no raise
  ```
- **GREEN**: Implementar `ScopeEnforcer` con wildcard y admin bypass.
- **Commit**: `feat(security): add scope enforcer`

### TASK_006: EndpointRegistry required_scopes
- **File**: `yaml-agno/src/api/endpoint_registry.py`
- **Test**: `tests/unit/api/test_endpoint_registry.py`
- **RED**:
  ```python
  def test_agents_runs_requires_run():
      assert EndpointRegistry.required_scopes("POST", "/agents/x/runs") == ["agents:run"]

  def test_sessions_get_requires_read():
      assert EndpointRegistry.required_scopes("GET", "/sessions") == ["sessions:read"]

  def test_unknown_route_none():
      assert EndpointRegistry.required_scopes("GET", "/nope") is None

  def test_eval_runs_post():
      assert EndpointRegistry.required_scopes("POST", "/eval-runs") == ["evals:write"]

  def test_traces_search():
      assert EndpointRegistry.required_scopes("POST", "/traces/search") == ["traces:read"]
  ```
- **GREEN**: Implementar catálogo de mappings.
- **Commit**: `feat(api): add endpoint scope registry`

### TASK_007: RBACManager scopes_for
- **File**: `yaml-agno/src/security/rbac.py`
- **Test**: `tests/unit/security/test_rbac.py`
- **RED**:
  ```python
  def test_rbac_member_scopes():
      mgr = RBACManager()
      scopes = mgr.scopes_for(["member"])
      assert "agents:read" in scopes
      assert "agents:delete" not in scopes

  def test_rbac_administrator_has_delete():
      scopes = RBACManager().scopes_for(["administrator"])
      assert "agents:delete" in scopes

  def test_rbac_custom_role():
      mgr = RBACManager(custom_roles={"custom": {"config:read"}})
      assert mgr.has_role("custom")
      assert "config:read" in mgr.scopes_for(["custom"])

  def test_rbac_multiple_roles_union():
      scopes = RBACManager().scopes_for(["viewer", "developer"])
      assert "agents:write" in scopes   # de developer
      assert "metrics:read" in scopes   # comun
  ```
- **GREEN**: Implementar `RBACManager` con roles default y custom.
- **Commit**: `feat(security): add rbac manager`

### TASK_008: UserIsolationEnforcer
- **File**: `yaml-agno/src/security/user_isolation.py`
- **Test**: `tests/unit/security/test_user_isolation.py`
- **RED**:
  ```python
  def test_coerce_user_id_non_admin():
      enforcer = UserIsolationEnforcer()
      req = FakeRequest(state=State(user_id="alice", is_admin=False))
      assert enforcer.effective_user_id(req, requested_user_id="bob") == "alice"

  def test_coerce_user_id_admin_passes_through():
      enforcer = UserIsolationEnforcer()
      req = FakeRequest(state=State(user_id="admin", is_admin=True))
      assert enforcer.effective_user_id(req, requested_user_id="bob") == "bob"

  def test_can_access_resource_owner():
      enforcer = UserIsolationEnforcer()
      req = FakeRequest(state=State(user_id="alice", is_admin=False))
      assert enforcer.can_access_resource(req, "alice") is True
      assert enforcer.can_access_resource(req, "bob") is False

  def test_can_access_resource_admin():
      enforcer = UserIsolationEnforcer()
      req = FakeRequest(state=State(user_id="admin", is_admin=True))
      assert enforcer.can_access_resource(req, "bob") is True
  ```
- **GREEN**: Implementar `UserIsolationEnforcer`.
- **Commit**: `feat(security): add user isolation enforcer`

### TASK_009: CorsConfigurator
- **File**: `yaml-agno/src/security/cors.py`
- **Test**: `tests/unit/security/test_cors.py`
- **RED**:
  ```python
  def test_cors_merges_with_agno_defaults():
      c = CorsConfigurator(allowed_origins=["https://app.example.com"])
      assert "https://os.agno.com" in c.allowed_origins
      assert "https://app.example.com" in c.allowed_origins

  def test_cors_dedup():
      c = CorsConfigurator(allowed_origins=["https://os.agno.com"])
      assert c.allowed_origins.count("https://os.agno.com") == 1
  ```
- **GREEN**: Implementar `CorsConfigurator`.
- **Commit**: `feat(security): add cors configurator`

### TASK_010: SecurityHeadersMiddleware
- **File**: `yaml-agno/src/security/security_headers.py`
- **Test**: `tests/unit/security/test_security_headers.py`
- **RED**:
  ```python
  async def test_security_headers_present():
      app = build_test_app(SecurityHeadersMiddleware)
      resp = await app.get("/anything")
      assert resp.headers["X-Content-Type-Options"] == "nosniff"
      assert resp.headers["X-Frame-Options"] == "DENY"
      assert "Strict-Transport-Security" in resp.headers

  async def test_csp_custom():
      app = build_test_app(SecurityHeadersMiddleware, csp="default-src 'self'")
      resp = await app.get("/anything")
      assert resp.headers["Content-Security-Policy"] == "default-src 'self'"
  ```
- **GREEN**: Implementar `SecurityHeadersMiddleware`.
- **Commit**: `feat(security): add security headers middleware`

### TASK_011: AuditLogger
- **File**: `yaml-agno/src/security/audit.py`
- **Test**: `tests/unit/security/test_audit.py`
- **RED**:
  ```python
  async def test_audit_log_persists():
      logger = AuditLogger(db=FakeDb())
      event = AuditEvent(event_type="auth.success", user_id="alice",
                         method="POST", path="/agents/x/runs", status_code=200)
      await logger.log(event)
      assert len(logger.db.events) == 1
      assert logger.db.events[0].event_type == "auth.success"

  def test_audit_event_defaults():
      e = AuditEvent(event_type="authz.denied")
      assert e.id is not None
      assert e.timestamp is not None
  ```
- **GREEN**: Implementar `AuditEvent` y `AuditLogger`.
- **Commit**: `feat(security): add audit logger`

### TASK_012: SecurityConfig y JwtConfig Pydantic
- **File**: `yaml-agno/src/config/security_config.py`
- **Test**: `tests/unit/config/test_security_config.py`
- **RED**:
  ```python
  def test_security_config_jwt_parse():
      cfg = SecurityConfig.model_validate({
          "auth_mode": "jwt",
          "jwt": {
              "algorithm": "RS256",
              "verification_keys": ["KEY"],
              "authorization": True,
              "user_isolation": True,
          },
      })
      assert cfg.auth_mode == "jwt"
      assert cfg.jwt.authorization is True
      assert cfg.jwt.user_isolation is True

  def test_jwt_excluded_routes_defaults():
      cfg = JwtConfig()
      assert "/health" in cfg.excluded_routes
      assert "/openapi.json" in cfg.excluded_routes
  ```
- **GREEN**: Implementar modelos de config.
- **Commit**: `feat(config): add security config models`

### TASK_013: Integración end-to-end JWT + scope + isolation
- **File**: `tests/integration/security/test_e2e_auth.py`
- **Test**: mismo archivo
- **RED**:
  ```python
  async def test_e2e_jwt_scope_isolation(client_with_security):
      # alice con agents:run y user_isolation
      token = make_jwt(sub="alice", scopes=["agents:run", "sessions:read"],
                       key=KEY, algorithm="HS256")
      resp = await client_with_security.post(
          "/agents/x/runs",
          headers={"Authorization": f"Bearer {token}"},
          data={"message": "hi", "user_id": "bob"},   # intenta atribuir a bob
      )
      assert resp.status_code == 200
      # verificar que la sesion se creo con user_id="alice" (coaccionado)
      sess = await client_with_security.get("/sessions",
              headers={"Authorization": f"Bearer {token}"})
      assert all(s["user_id"] == "alice" for s in sess.json())

  async def test_e2e_forbidden_missing_scope(client_with_security):
      token = make_jwt(sub="alice", scopes=["agents:read"],   # solo read
                       key=KEY, algorithm="HS256")
      resp = await client_with_security.post("/agents/x/runs",
              headers={"Authorization": f"Bearer {token}"})
      assert resp.status_code == 403
  ```
- **GREEN**: Cablear middleware + enforcer + isolation en la app FastAPI.
- **Commit**: `feat(security): wire auth pipeline end to end`

---

## 12. SUPUESTOS TÉCNICOS ADOPTADOS

### [Decisión 1] JWT como auth de producción; Basic Auth solo dev
`OS_SECURITY_KEY` está deprecado para producción. JWT con RS256 (asimétrico) es el default porque permite verificación con public key sin exponer el secreto de firma.

### [Decisión 2] Scopes jerárquicos con wildcard solo en agents/teams/workflows
El scoping per-recurso (`resource:<id>:action`) es poderoso pero complejo. Limitarlo a los tres recursos "runneables" mantiene el modelo manejable. Sessions/memories/knowledge/traces usan scopes globales + aislamiento per-user.

### [Decisión 3] user_isolation opt-in
Off por defecto porque requiere DB con `user_id` en filas. On en producción multi-tenant. El `sub` del JWT es la fuente de verdad del `user_id`.

### [Decisión 4] Admin bypass explicito
`agent_os:admin` bypassa scopes Y isolation. Es deliberado: los ops necesitan ver todo para debugging. Customizable via `admin_scope`.

### [Decisión 5] CORS merged con defaults Agno
`cors_allowed_origins` se mergea con los dominios default de Agno (`os.agno.com`). Esto permite que el dashboard de Agno funcione sin config adicional.

### [Decisión 6] Rate limiting delegado a SPEC_06
No se redefine el `RateLimiter`. Se referencia SPEC_06 §1.4 (100 req/min tenant, 20 req/min IP). Esto evita duplicación.

### [Decisión 7] Audit trail siempre on para denegaciones
`auth.failed`, `authz.denied`, e `isolation.coerced` se loguean siempre (incluso con `audit.enabled=false` para esos tres). Los éxitos son configurables.

---

## 13. PREGUNTAS DE CALIBRACIÓN ESTRATÉGICA

### [Pregunta 1] ¿Key rotation strategy?
`verification_keys` es una lista, pero la rotación real (revocar key vieja) requiere proceso.
Implica:
- **JWKS + kid**: rotación automática, requiere endpoint JWKS.
- **Lista manual**: simple, propenso a ventanas de vulnerabilidad.
Trade-off: automatización vs simplicidad operacional.

### [Pregunta 2] ¿Token lifetime?
¿JWT de corta duración (15 min) + refresh, o larga duración (24h)?
Implica:
- **Corto + refresh**: más seguro, más complejidad.
- **Largo**: más simple, mayor ventana si se compromete.
Los docs no especifican; depende del IDP.

### [Pregunta 3] ¿Custom scope mappings para IDP de terceros?
WorkOS usa `permissions`, Auth0 `scope`, Okta `scp`. ¿Mapear automáticamente o requerir config explicita?
Implica:
- **Auto-detect**: menos config, magia.
- **Explicit `scopes_claim`**: más control, más verbosidad.

### [Pregunta 4] ¿Granularidad del audit trail?
¿Loguear todos los `auth.success` o solo denegaciones?
Implica:
- **Todo**: trazabilidad completa, alto volumen de log.
- **Solo denegaciones**: suficiente para forense, bajo volumen.

### [Pregunta 5] ¿RBAC dinámico vs estático?
¿Los roles custom se cargan de YAML (estático, reinicio para cambiar) o de DB/control plane (dinámico)?
Implica: flexibilidad vs simplicidad. El control plane de Agno maneja roles dinámicamente; self-hosted puede usar YAML.

### [Pregunta 6] ¿WebSocket auth?
Los docs mencionan que el reconnect de WebSocket requiere `session_id` para no-admins. ¿Validar JWT en handshake WS o en cada frame?
Implica: complejidad vs granularidad.

---

*¿Deseas profundizar la especificación técnica al **Nivel 6** de algún componente (ej. JWKS lookup, CSP avanzada, o el mapeo de un IDP específico como WorkOS/Auth0) o autorizar la ejecución de estas tareas por parte del equipo de agentes?*
