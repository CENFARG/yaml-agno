"""Model configuration schemas (SPEC_14 slice #2).

Five Pydantic V2 types describing how a model is declared in YAML:

    - :class:`ModelStringSpec`  — compact ``"provider:id"`` string form.
    - :class:`ModelExpandedSpec` — expanded mapping form (generation params,
      Agno-native retry fields, fallback chain).
    - :class:`FallbackConfig`   — declarative fallback chain (schema only).
    - :data:`ModelSpec`         — ``Union[ModelStringSpec, ModelExpandedSpec]``.
    - :class:`ProviderResolver` — normalizes a spec by applying provider aliases.

This module is a STANDALONE additive slice: nothing imports it yet. Wiring
``AgentConfig.model`` to :data:`ModelSpec` is a later coordinated change
(SPEC_02 evolution). Provider validation is SSOT-driven (the
``SUPPORTED_PROVIDERS`` frozenset from slice 1), NOT a hardcoded ``Literal``.
Retry fields forward 1:1 to Agno native ``Model`` names — no yaml-agno-only
retry names are exposed.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from yaml_agno.di.provider_capabilities import SUPPORTED_PROVIDERS
from yaml_agno.di.registries import PROVIDER_ALIASES

# Regex shared by ModelStringSpec format validation. "provider:id" with both
# halves non-empty; ":" alone is invalid (AgentConfig.validate_model_format
# invariants mirrored here for slice-2 standalone use).
_PROVIDER_ID_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_]+:[A-Za-z0-9_.\-]+$")


class ModelStringSpec(BaseModel):
    """Model reference in compact string form ``"provider:id"``.

    The scalar variant of the ``ModelSpec`` union. Provider half is validated
    against ``SUPPORTED_PROVIDERS`` (frozenset derived from PROVIDER_REGISTRY,
    slice 1) so an unknown provider fails fast at parse time. Alias expansion
    (``"openai"`` -> ``"openai_chat"``) is performed later by
    :class:`ProviderResolver`, NOT by this validator — the spec keeps the
    user-written provider so error messages reference what the user typed.

    Attributes:
        provider: Provider half (e.g. ``"openai"``, ``"anthropic"``). Validated
            against ``SUPPORTED_PROVIDERS``.
        id: Model identifier (e.g. ``"gpt-4o"``).

    Example:
        >>> spec = ModelStringSpec.model_validate("openai:gpt-4o")
        >>> spec.provider, spec.id
        ('openai', 'gpt-4o')
    """

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., min_length=1, description="Provider id; must be in SUPPORTED_PROVIDERS.")
    id: str = Field(..., min_length=1, description="Model identifier (e.g. 'gpt-4o').")

    # Enable ``ModelStringSpec.model_validate("openai:gpt-4o")``: Pydantic V2
    # otherwise expects a dict. We accept a bare string by parsing it here.
    # The Pydantic V2 union does NOT route a bare str to this method
    # automatically (it validates via the internal schema), so this override is
    # only used for direct ``ModelStringSpec.model_validate(str)`` calls and by
    # :func:`parse_model_spec`. Union dispatch goes through that helper.
    @classmethod
    def model_validate(  # type: ignore[override]
        cls,
        obj: Any,
        *args: Any,
        **kwargs: Any,
    ) -> ModelStringSpec:
        """Accept either a ``"provider:id"`` string or a dict payload."""
        if isinstance(obj, str):
            return cls._from_string(obj)
        return super().model_validate(obj, *args, **kwargs)  # type: ignore[no-any-return]

    @classmethod
    def _from_string(cls, value: str) -> ModelStringSpec:
        """Parse and validate a ``"provider:id"`` string.

        Args:
            value: Bare model string, e.g. ``"openai:gpt-4o"``.

        Returns:
            A validated :class:`ModelStringSpec`.

        Raises:
            ValueError: If the format is wrong or the provider is unknown.
        """
        if not _PROVIDER_ID_RE.match(value):
            raise ValueError(
                f"Invalid model string: {value!r}. Expected 'provider:id' "
                f"(e.g. 'openai:gpt-4o')."
            )
        provider, _, model_id = value.partition(":")
        # NOTE: alias resolution is deferred to ProviderResolver; here we only
        # confirm the provider is a known key or alias target.
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unknown provider: {provider!r}. Supported providers: "
                f"{sorted(SUPPORTED_PROVIDERS)}."
            )
        return cls(provider=provider, id=model_id)


class FallbackConfig(BaseModel):
    """Declarative fallback chain for a model.

    Schema only in this slice. Runtime ``build_fallback_chain`` /
    ``call_with_fallback`` and Circuit Breaker integration ship in slice #4.
    Listed here as a concrete type so :class:`ModelExpandedSpec.fallback` does
    not need a forward reference.

    Attributes:
        fallback_models: Ordered list of fallback model references. Each entry
            is a ``"provider:id"`` string OR a provider:id mapping (the same
            shapes accepted by :data:`ModelSpec`). The first entry is tried
            first after the primary model.
        on_rate_limit / on_context_overflow / on_error: Per-error-class routing
            strategy (Literal ``retry_only | route_fallback |
            retry_then_fallback | fail``). Reserved for slice #4 runtime — the
            value is validated here, not acted on.
        fallback_callback: Optional dotted callable ref invoked on fallback
            (resolved by slice #3 ProviderFactory).
        max_fallback_hops: Max sequential fallback attempts (>= 1, default 3).
        propagate_session: Whether the session carries across fallback hops
            (default True).

    Example:
        >>> FallbackConfig(fallback_models=["anthropic:claude-3-5-sonnet"])
    """

    model_config = ConfigDict(extra="forbid")

    fallback_models: list[str | dict[str, Any]] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Ordered fallback model references (str 'provider:id' or dict).",
    )
    on_rate_limit: Literal["retry_only", "route_fallback", "retry_then_fallback", "fail"] = Field(
        "route_fallback",
        description="Routing strategy on rate-limit errors. Reserved for slice #4.",
    )
    on_context_overflow: Literal["retry_only", "route_fallback", "retry_then_fallback", "fail"] = Field(
        "route_fallback",
        description="Routing strategy on context-overflow errors. Reserved for slice #4.",
    )
    on_error: Literal["retry_only", "route_fallback", "retry_then_fallback", "fail"] = Field(
        "retry_then_fallback",
        description="Routing strategy on generic errors. Reserved for slice #4.",
    )
    fallback_callback: str | None = Field(
        None,
        description="Optional dotted callable ref invoked on fallback (resolved slice #3).",
    )
    max_fallback_hops: int = Field(3, ge=1, description="Max sequential fallback attempts (>= 1).")
    propagate_session: bool = Field(True, description="Whether the session carries across fallback hops.")


class ModelExpandedSpec(BaseModel):
    """Model reference in expanded mapping form.

    The dict variant of the ``ModelSpec`` union. Mirrors the fields the Agno
    base ``Model`` constructor accepts (verified SPEC_05:210 + SPEC_14 iter-4
    notes 551-554, 824-825). Retry fields map 1:1 to Agno native names; no
    yaml-agno-only retry names are exposed (see ADR A3).

    Attributes:
        provider: Provider id; validated against ``SUPPORTED_PROVIDERS``.
        id: Model identifier (e.g. ``"gpt-4o"``).

    Example:
        >>> ModelExpandedSpec(provider="openai", id="gpt-4o", retries=3)
    """

    model_config = ConfigDict(extra="forbid")

    # --- Identity (2 required fields) ---
    provider: str = Field(..., min_length=1, description="Provider id; must be in SUPPORTED_PROVIDERS.")
    id: str = Field(..., min_length=1, description="Model identifier (e.g. 'gpt-4o').")

    # --- Agno base Model passthrough (optional, 2 fields) ---
    name: str | None = Field(None, description="Display name forwarded to Agno Model.name.")
    model_type: str | None = Field(None, description="Agno model_type tag.")

    # --- Structured outputs (2 fields) ---
    supports_native_structured_outputs: bool | None = Field(
        None, description="Agno base flag for native structured outputs."
    )
    supports_json_schema_outputs: bool | None = Field(
        None, description="Agno base flag for JSON-schema outputs."
    )

    # --- Generation params (SPEC_14 §4.1; provider-specific, forwarded as kwargs) ---
    temperature: float | None = Field(None, ge=0.0, le=2.0, description="Sampling temperature (0.0-2.0).")
    max_tokens: int | None = Field(None, ge=1, description="Max tokens to generate (>= 1).")
    top_p: float | None = Field(None, ge=0.0, le=1.0, description="Nucleus sampling probability (0.0-1.0).")
    top_k: int | None = Field(None, ge=0, description="Top-k sampling (>= 0).")
    stop_sequences: list[str] | None = Field(None, description="Stop sequences.")
    seed: int | None = Field(None, description="Deterministic sampling seed.")

    # --- Reasoning (provider-specific; SPEC_14 §3.4) ---
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = Field(
        None, description="Reasoning effort level (provider-specific)."
    )
    thinking: bool | None = Field(None, description="Enable extended thinking (provider-specific).")

    # --- Caching (3 fields) ---
    cache_response: bool | None = Field(None, description="Enable Agno prompt caching.")
    cache_ttl: int | None = Field(None, ge=0, description="Cache TTL in seconds.")
    cache_dir: str | None = Field(None, description="Optional cache directory.")

    # --- Retry (Agno native names; ADR A3) ---
    retries: int | None = Field(None, ge=0, le=10, description="Number of retries (Agno retries).")
    delay_between_retries: float | None = Field(
        None, ge=0.0, description="Seconds between retries (Agno delay_between_retries)."
    )
    exponential_backoff: bool | None = Field(
        None, description="Use exponential backoff (Agno exponential_backoff)."
    )
    retry_with_guidance: bool | None = Field(
        None, description="Retry with guidance prompt (Agno retry_with_guidance)."
    )
    retry_with_guidance_limit: int | None = Field(
        None, ge=0, description="Max guidance retries (Agno retry_with_guidance_limit)."
    )

    # --- Fallback (schema only; runtime slice #4) ---
    fallback: FallbackConfig | None = Field(
        None, description="Fallback chain. Schema only; runtime in slice #4."
    )

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, v: str) -> str:
        """Confirm ``provider`` is a known key in ``SUPPORTED_PROVIDERS``.

        Alias expansion (``"openai"`` -> ``"openai_chat"``) is deferred to
        :class:`ProviderResolver` so the spec retains what the user wrote.
        """
        if v not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unknown provider: {v!r}. Supported providers: "
                f"{sorted(SUPPORTED_PROVIDERS)}."
            )
        return v


# Union exported to consumers (future AgentConfig.model swap). NOTE: Pydantic V2
# does NOT auto-discriminate ``str`` vs ``dict`` for this union — use
# :func:`parse_model_spec` as the entry point (it dispatches by input type).
ModelSpec = ModelStringSpec | ModelExpandedSpec


def parse_model_spec(obj: ModelSpec | str | dict[str, Any]) -> ModelStringSpec | ModelExpandedSpec:
    """Dispatch a YAML model value to the correct spec type by input shape.

    Pydantic V2's ``Union[ModelStringSpec, ModelExpandedSpec]`` cannot
    auto-discriminate a bare ``str`` from a ``dict`` (both can satisfy the
    ``{provider, id}`` shape). This helper is the canonical entry point:

        - ``str``  -> :class:`ModelStringSpec` (compact ``"provider:id"``).
        - ``dict`` -> :class:`ModelExpandedSpec` (expanded mapping).
        - already a spec -> returned unchanged.

    Args:
        obj: A bare model string, a mapping, or an already-parsed spec.

    Returns:
        A validated :class:`ModelStringSpec` or :class:`ModelExpandedSpec`.

    Raises:
        TypeError: If ``obj`` is none of the accepted input shapes.
    """
    if isinstance(obj, str):
        return ModelStringSpec.model_validate(obj)
    if isinstance(obj, dict):
        return ModelExpandedSpec.model_validate(obj)
    if isinstance(obj, (ModelStringSpec, ModelExpandedSpec)):
        return obj
    raise TypeError(f"Unsupported model spec input type: {type(obj).__name__}.")



class ProviderResolver:
    """Normalize a :data:`ModelSpec` by applying provider aliases.

    Stateless resolver. Applies ``PROVIDER_ALIASES`` (slice 1) to the provider
    half of a :class:`ModelStringSpec` or :class:`ModelExpandedSpec`, then
    confirms the canonical id is in ``SUPPORTED_PROVIDERS``. Does NOT import
    Agno or instantiate models — that is the factory's job.

    Aliases handled:
        - ``"openai"`` -> ``"openai_chat"`` (legacy -> canonical SPEC_14).

    Attributes:
        aliases: Mapping applied to the provider half. Defaults to the slice-1
            ``PROVIDER_ALIASES`` constant; injectable for testing.

    Example:
        >>> spec = ModelStringSpec.model_validate("openai:gpt-4o")
        >>> ProviderResolver().resolve(spec).provider
        'openai_chat'
    """

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        """Initialize the resolver.

        Args:
            aliases: Optional override for ``PROVIDER_ALIASES``. Mainly for
                unit tests; production callers leave this ``None``.
        """
        self.aliases = aliases if aliases is not None else dict(PROVIDER_ALIASES)

    def resolve(self, spec: ModelSpec) -> ModelSpec:
        """Return a copy of ``spec`` with its provider canonicalized.

        Args:
            spec: A :class:`ModelStringSpec` or :class:`ModelExpandedSpec`.

        Returns:
            A new spec of the same type with ``provider`` set to the canonical
            id (alias applied if one existed). If the provider was already
            canonical, the input is returned unchanged.

        Raises:
            ValueError: If the canonicalized provider is not in
                ``SUPPORTED_PROVIDERS`` (indicates a stale alias map).
        """
        if isinstance(spec, ModelStringSpec):
            canonical = self._canonical_provider(spec.provider)
            if canonical == spec.provider:
                return spec
            return spec.model_copy(update={"provider": canonical})
        if isinstance(spec, ModelExpandedSpec):
            canonical = self._canonical_provider(spec.provider)
            if canonical == spec.provider:
                return spec
            return spec.model_copy(update={"provider": canonical})
        raise TypeError(f"Unsupported spec type for resolution: {type(spec).__name__}")

    def _canonical_provider(self, provider: str) -> str:
        """Apply the alias map and confirm the canonical id is supported.

        Args:
            provider: The provider half as written by the user.

        Returns:
            The canonical provider id.

        Raises:
            ValueError: If the resolved canonical id is not in
                ``SUPPORTED_PROVIDERS``.
        """
        canonical = self.aliases.get(provider, provider)
        if canonical not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Resolved provider {canonical!r} (from {provider!r}) is not in "
                f"SUPPORTED_PROVIDERS."
            )
        return canonical


__all__ = [
    "FallbackConfig",
    "ModelExpandedSpec",
    "ModelSpec",
    "ModelStringSpec",
    "ProviderResolver",
    "parse_model_spec",
]
