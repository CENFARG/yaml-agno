"""SecretResolver — port SYNC para resolución de API keys (SPEC_14 slice #3).

El ProviderFactory es síncrono (los constructores Agno Model son @dataclass
SYNC). core-cenf SecretManager.get_secret() es async (SPEC_23 §2.4, aún no
entregado). Para evitar acoplar el factory al boundary async, definimos un
Protocol SYNC local: el bootstrap (async) pre-resuelve los secrets una vez por
provider y entrega al factory un callable SYNC (lambda sobre un dict cache).

El default ConfigSecretResolver lee ``config.get_string("secrets.<env>")`` —
NO toca os.environ (SPEC_00 §9.3 @ai-directive). El production wiring (SPEC_23)
reemplaza este resolver por un adaptador async->sync sobre SecretManager.

@ai-directive: NO uses os.environ. NO hagas este resolver async. El factory
    es SYNC por A2.
"""

from __future__ import annotations

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
        """Resolve ``env_name`` to its secret via ``config.get_string``.

        Args:
            env_name: Logical env-var name (e.g. ``"OPENAI_API_KEY"``).

        Returns:
            The secret string, or None if the key is absent from the config.
        """
        key = f"secrets.{env_name.lower()}"
        try:
            value = self._config.get_string(key, default_value=None)
        except ValidationError:
            # ConfigManager.get_string raises ValidationError when the key is
            # absent (default_value=None is treated as "no default"). The
            # SecretResolver contract returns None for a missing secret so the
            # factory can decide whether to proceed (local provider) or fail
            # elsewhere. SPEC_14 slice #3 Scenario: ConfigSecretResolver
            # devuelve None si falta.
            return None
        return str(value)
