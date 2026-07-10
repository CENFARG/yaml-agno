"""CacheKeyBuilder — clave sha256 determinista (SPEC_14 #4 DOMAIN).

Deriva una clave de 64 chars (hex sha256) sobre la identidad del spec + los
hashes que el caller provee. Es una CLAVE de dedup/observabilidad (trazas
SPEC_09), NO un cache store — Agno ``cache_response`` es nativo y yaml-agno NO
agrega capa de cache (SPEC_14 §5.4, ADR A4).

El builder NO serializa messages/tools/response_model: el caller (runtime
SPEC_09) los hashea y los pasa como strings. Esto evita scope-creep de
serialización de esquemas Agno en el dominio (R4).

@ai-directive: NO agregues get/set/invalidate — no es un CacheManager. NO
    serialices mensajes/tools — el caller los hashea. Usa SIEMPRE
    sort_keys=True + separators compactos para estabilidad cross-plataforma.
"""

from __future__ import annotations

import hashlib
import json

from yaml_agno.models.model_spec import ModelExpandedSpec

__all__ = ["CacheKeyBuilder"]

# Prefijo corto y estable para distinguir esta clave de otros hashes en trazas.
# NO cambia entre versiones: alterarlo rompe la determinismo cross-versión.
_PREFIX = "ya:ck:v1:"


class CacheKeyBuilder:
    """Build a deterministic sha256 hex digest for a model invocation.

    Stateless. The digest is over a stable JSON serialization of:
      - ``spec.model_dump(exclude_none=True)`` (provider, id, temperature, ...)
      - the caller-supplied ``messages_hash``, ``tool_defs_hash``,
        ``response_model_hash``.

    Serialization is ``json.dumps(..., sort_keys=True, separators=(",", ":"))``
    so key ordering and whitespace never affect the digest.

    Example:
        >>> key_a = CacheKeyBuilder.build(spec, messages_hash="abc")
        >>> key_b = CacheKeyBuilder.build(spec, messages_hash="abc")
        >>> key_a == key_b
        True
    """

    @staticmethod
    def build(
        spec: ModelExpandedSpec,
        *,
        messages_hash: str,
        tool_defs_hash: str = "",
        response_model_hash: str = "",
    ) -> str:
        """Return a 64-char sha256 hex digest identifying this invocation.

        Args:
            spec: The model spec — provider, id, and generation params feed the
                digest (``None`` fields excluded so optional unset values do not
                change the key).
            messages_hash: Caller-supplied hash of the serialized messages. The
                caller is responsible for stable ordering (e.g. sort by role).
            tool_defs_hash: Caller-supplied hash of the tool definitions. Empty
                string when no tools are bound.
            response_model_hash: Caller-supplied hash of the response model
                schema. Empty string for free-form completions.

        Returns:
            A string of the form ``"ya:ck:v1:<64 hex chars>"``. Deterministic:
            identical inputs always produce identical output.
        """
        payload = {
            "spec": spec.model_dump(exclude_none=True),
            "messages_hash": messages_hash,
            "tool_defs_hash": tool_defs_hash,
            "response_model_hash": response_model_hash,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return f"{_PREFIX}{digest}"
