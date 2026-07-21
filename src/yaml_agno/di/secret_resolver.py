"""SecretResolver — port SYNC para resolución de API keys (SPEC_14 slice #3).

El ProviderFactory es síncrono (los constructores Agno Model son @dataclass
SYNC). core-cenf SecretManager.get_secret() es async (SPEC_23 §2.4, aún no
entregado). Para evitar acoplar el factory al boundary async, definimos un
Protocol SYNC local: el bootstrap (async) pre-resuelve los secrets una vez por
provider y entrega al factory un callable SYNC (lambda sobre un dict cache).

El default ConfigSecretResolver lee ``config.get_string("secrets.<env>")`` y,
si la config no tiene el valor (FIX 4 — resolver-bootstrap-fix), cae a
``os.environ.get(env_name)`` como fallback. SPEC_00 §9.3 prohibe ``os.environ``
en **código de aplicación**, pero SecretResolver ES la capa de infraestructura
que abstrae el acceso a secrets — centralizar el fallback de env aquí mantiene
el acceso a ``os.environ`` en UN solo lugar. El production wiring (SPEC_23)
reemplaza este resolver por un adaptador async->sync sobre SecretManager y el
fallback de env desaparece con él.

@ai-directive: NO hagas este resolver async. El factory es SYNC por A2. El
    acceso a os.environ vive aquí (capa de infra), no en app code.
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.config.ports import ConfigManager

__all__ = ["ConfigSecretResolver", "SecretResolver"]


@runtime_checkable
class SecretResolver(Protocol):
    """Callable SYNC que resuelve un nombre de env-var a su valor de API key.

    Es el contrato que ProviderFactory consume. NO es el SecretManager async de
    core-cenf — es la adapter SYNC que el bootstrap construye tras pre-resolver.

    Calling convention:
        resolver("OPENAI_API_KEY") -> "sk-..."  |  None  (si no hay secret)
    """

    def __call__(self, env_name: str) -> str | None:
        """Return the secret value for ``env_name``, or None if not configured.

        Args:
            env_name: Logical env-var name (e.g. ``"OPENAI_API_KEY"``). Matches
                ``ProviderRegistryEntry.api_key_env``.

        Returns:
            The secret string, or None if the secret is not configured (e.g.
            local providers like ollama that have ``api_key_env=None`` never
            reach the resolver at all).
        """
        ...


class ConfigSecretResolver:
    """Default SecretResolver backed by ``ConfigManager.get_string``.

    Reads ``secrets.<env_name_lower>`` from the config namespace. ``env_name`` is
    lowercased to match typical YAML key conventions (``secrets.openai_api_key``).

    Attributes:
        _config: ConfigManager port (never os.environ).

    Example:
        >>> resolver = ConfigSecretResolver(config)
        >>> resolver("OPENAI_API_KEY")  # reads config["secrets.openai_api_key"]
        'sk-...'
    """

    def __init__(self, config: ConfigManager) -> None:
        """Initialize the resolver with a ConfigManager.

        Args:
            config: ConfigManager port. MUST expose ``secrets.*`` keys for the
                providers the app uses.
        """
        self._config = config

    def __call__(self, env_name: str) -> str | None:
        """Resolve ``env_name`` to its secret, config first, env fallback.

        Order (FIX 4 — resolver-bootstrap-fix):
          1. ``config.get_string("secrets.<env_lower>")`` (authoritative).
          2. On miss / ValidationError: ``os.environ.get(env_name)``.
          3. If both miss: None.

        ConfigManager remains the source of truth; the env fallback only fires
        on a config miss. SPEC_00 §9.3 bans os.environ in app code, but this
        resolver IS the infrastructure layer that abstracts secret sources —
        centralizing the fallback here keeps os.environ access in ONE place.

        Args:
            env_name: Logical env-var name (e.g. ``"OPENAI_API_KEY"``).

        Returns:
            The secret string, or None if neither config nor env has it.
        """
        key = f"secrets.{env_name.lower()}"
        try:
            value = self._config.get_string(key, default_value=None)
        except ValidationError:
            # ConfigManager.get_string raises ValidationError when the key is
            # absent (default_value=None is treated as "no default"). Fall
            # through to the env fallback below.
            value = None
        if value is not None:
            return str(value)
        # FIX 4: env fallback (infrastructure-layer escape hatch). Config
        # missed; consult the process environment before giving up.
        return os.environ.get(env_name)
