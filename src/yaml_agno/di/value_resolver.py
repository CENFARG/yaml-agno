"""ValueResolver — traduce la sintaxis ``${provider.key}`` a valores concretos.

Contract con DIReference (SPEC_02, ya entregado):
    DIReference.resolve(resolved_values: dict[str, Any]) -> str
    espera un dict plano "provider.key" -> value. Este modulo construye ese dict
    consultando providers. MVP: solo env.* (ConfigManager.get_string). Otros
    providers (db/api/file) lanzan NotImplementedError ruidoso (deferidos a
    SPEC_23) — nunca retornan None silenciosamente.

@ai-directive: La sintaxis ${provider.key} es OWN yaml-agno; no existe en Agno.
    Este modulo NO toca DIReference — solo produce el dict que su resolve() come.
"""

from __future__ import annotations

from typing import Any

from core_infrastructure.config.ports import ConfigManager

from yaml_agno.models.value_objects.di_reference import DIReference

__all__ = ["ValueResolver"]

# Providers con implementación; el resto lanza NotImplementedError.
_SUPPORTED_PROVIDERS: frozenset[str] = frozenset({"env"})


class ValueResolver:
    """Resuelve los tokens ``${provider.key}`` de un ``DIReference``.

    Itera los tokens del template, despacha cada ``provider`` al resolver
    correspondiente, y arma el dict ``provider.key -> value`` consumible por
    ``DIReference.resolve()``.

    Attributes:
        _config: ConfigManager para el provider ``env``.

    Example:
        >>> ref = DIReference(template="key is ${env.api_key}")
        >>> vr = ValueResolver(config)
        >>> resolved = vr.resolve(ref)
        >>> resolved
        {'env.api_key': 'sk-...'}
        >>> ref.resolve(resolved)
        'key is sk-...'
    """

    def __init__(self, config: ConfigManager) -> None:
        """Inicializa el resolver con un ConfigManager.

        Args:
            config: ConfigManager usado por el provider ``env`` para
                ``get_string(key)``.
        """
        self._config = config

    def resolve(self, reference: DIReference) -> dict[str, Any]:
        """Resolver todos los tokens de ``reference`` a un dict provider.key.

        Args:
            reference: ``DIReference`` ya validado (SPEC_02).

        Returns:
            Dict plano ``"provider.key" -> valor`` consumible por
            ``DIReference.resolve()``.

        Raises:
            NotImplementedError: Si algún provider no es ``env`` (MVP).
            ValidationError: Si la clave env no existe en el ConfigManager
                (propagado por ``get_string``).
        """
        resolved: dict[str, Any] = {}
        for provider, key in reference.tokens:
            full_key = f"{provider}.{key}"
            resolved[full_key] = self._resolve_provider(provider, key)
        return resolved

    def _resolve_provider(self, provider: str, key: str) -> Any:
        """Despachar un token (provider, key) a su resolver concreto.

        Args:
            provider: Nombre del provider ("env", "db", "api", "file", ...).
            key: Clave dentro del provider.

        Returns:
            El valor resuelto.

        Raises:
            NotImplementedError: Para providers no soportados en el MVP.
        """
        if provider == "env":
            # ConfigManager.get_string: KeyError → ValidationError si no existe.
            return self._config.get_string(key)
        raise NotImplementedError(
            f"ValueResolver MVP supports only {_SUPPORTED_PROVIDERS}; provider {provider!r} is deferred to SPEC_23"
        )
