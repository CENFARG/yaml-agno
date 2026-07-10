"""ProviderFactory — traduce ModelExpandedSpec en instancia Agno Model (SPEC_14 #3).

COMPOSE alrededor de AgnoResolver (A1): delega la carga de la clase nativa a
``resolver.resolve_class(module_path, class_name)`` (el punto de escape público
en agno_resolver.py:184-199) y AGREGA:

  1. ``_compose_kwargs(spec, cls)`` — filtra dinámicamente contra
     ``dataclasses.fields(cls)`` para forwardear solo los campos que la clase
     destino declara (A3). Evita TypeError al pasar ``top_k`` a OpenAIChat.
  2. Resolución del ``api_key`` vía un ``SecretResolver`` SYNC inyectado (A2) —
     el factory NO toca os.environ ni el SecretManager async.
  3. (Opcional) ``ModelCapabilitiesValidator`` pre-check contra caps declaradas.

El factory es SYNC (A2): los constructores Agno Model son @dataclass SYNC y
resuelven el cliente HTTP lazily, así que el api_key puede pasarse al
constructor sin bloqueo.

@ai-directive: NO uses os.environ. NO reimplementes importlib/allowlist —
    delega a AgnoResolver.resolve_class. NO inventes nombres de retry (slice #2
    ya expone los Agno-native: retries, delay_between_retries, etc.).
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from yaml_agno.di.agno_resolver import AgnoResolver
from yaml_agno.di.provider_capabilities import PROVIDER_REGISTRY
from yaml_agno.di.secret_resolver import SecretResolver

# ModelExpandedSpec is only a type hint (runtime duck-typing via attribute
# access). Module-level import would create a circular import:
# models.model_spec -> di.provider_capabilities -> di.__init__ ->
# di.provider_factory -> models.model_spec (partially initialized).
if TYPE_CHECKING:
    from yaml_agno.models.model_spec import ModelExpandedSpec

__all__ = ["ModelConstructionError", "ProviderFactory"]


class ModelConstructionError(Exception):
    """Raised when a provider class cannot be instantiated from a spec.

    Wraps the underlying TypeError/ValueError from the Agno constructor with
    context about which provider and model id failed, so the caller (bootstrap
    or config-load) can surface a clear error instead of a raw Agno traceback.
    """

    def __init__(self, provider: str, model_id: str, cause: Exception) -> None:
        """Initialize with provider/id context and the wrapped cause.

        Args:
            provider: Provider id (e.g. ``"openai_chat"``).
            model_id: Model id (e.g. ``"gpt-4o"``).
            cause: The underlying exception from the constructor.
        """
        self.provider = provider
        self.model_id = model_id
        self.cause = cause
        super().__init__(
            f"Failed to construct Agno Model for provider={provider!r} "
            f"id={model_id!r}: {type(cause).__name__}: {cause}"
        )


class ProviderFactory:
    """Builds Agno Model instances from ModelExpandedSpec (SPEC_14 slice #3).

    Delegates class resolution to ``AgnoResolver.resolve_class`` (A1) and adds
    kwargs composition, secret resolution, and (optional) capability validation.
    Sync by design (A2): matches Agno's @dataclass Model constructors.

    Attributes:
        _resolver: AgnoResolver (class-loading + allowlist).
        _secret_resolver: SYNC SecretResolver for api_key.
        _validate_capabilities: When True, run ModelCapabilitiesValidator before
            constructing and raise on declared-cap mismatch.

    Example:
        >>> factory = ProviderFactory(resolver, secret_resolver)
        >>> spec = ModelExpandedSpec(provider="openai", id="gpt-4o", temperature=0.7)
        >>> model = factory.build(spec)
        >>> model.id
        'gpt-4o'
    """

    def __init__(
        self,
        resolver: AgnoResolver,
        secret_resolver: SecretResolver,
        *,
        validate_capabilities: bool = False,
    ) -> None:
        """Initialize the factory with its two injected dependencies.

        Args:
            resolver: AgnoResolver — provides ``resolve_class(module, name)``.
            secret_resolver: SYNC SecretResolver (A2). The bootstrap pre-resolves
                secrets async and hands a sync callable here.
            validate_capabilities: When True, ``build`` runs the pure-data
                ModelCapabilitiesValidator and raises if the spec asks for a
                capability the provider does not declare. Default False (warning
                path); enable for strict config-load validation.
        """
        self._resolver = resolver
        self._secret_resolver = secret_resolver
        self._validate_capabilities = validate_capabilities

    def build(self, spec: ModelExpandedSpec) -> Any:
        """Construct an Agno Model instance from ``spec``.

        Pipeline (see design data-flow diagram):
          1. Look up PROVIDER_REGISTRY[spec.provider] -> entry.
          2. Resolve the class via ``resolver.resolve_class``.
          3. Compose kwargs (filtered against the resolved class's dataclass
             fields).
          4. If ``entry.api_key_env`` is set, resolve it via secret_resolver and
             inject as ``api_key``.
          5. (Optional) capability pre-check.
          6. Instantiate ``cls(id=spec.id, **kwargs)``.

        Args:
            spec: A validated ModelExpandedSpec (slice #2). ``spec.provider``
                MUST be a canonical PROVIDER_REGISTRY key (apply
                ProviderResolver first if the spec may carry an alias).

        Returns:
            An Agno Model INSTANCE (e.g. ``OpenAIChat(id="gpt-4o", ...)``).

        Raises:
            KeyError: If ``spec.provider`` is not in PROVIDER_REGISTRY.
            ModelConstructionError: If the Agno constructor raises (wrapped).
        """
        if spec.provider not in PROVIDER_REGISTRY:
            raise KeyError(f"Unknown provider: {spec.provider!r}")

        entry = PROVIDER_REGISTRY[spec.provider]
        cls = self._resolver.resolve_class(entry.module_path, entry.class_name)
        kwargs = self._compose_kwargs(spec, cls)

        # Secret resolution (A2): local providers (ollama, llamacpp, ...) have
        # api_key_env=None and never reach the resolver. Cloud/gateway providers
        # get their key injected as api_key= kwarg (filtered in step 3 only if
        # the class declares it — all cloud Agno Models do).
        if entry.api_key_env is not None:
            api_key = self._secret_resolver(entry.api_key_env)
            if api_key is not None:
                kwargs["api_key"] = api_key

        # Optional capability pre-check (A6). Imported lazily to avoid a circular
        # import (capabilities_validator imports PROVIDER_REGISTRY too, which is
        # fine, but lazy keeps the module-import graph acyclic under strict TDD).
        if self._validate_capabilities:
            from yaml_agno.di.capabilities_validator import ModelCapabilitiesValidator

            errors = ModelCapabilitiesValidator.validate(spec, entry.capabilities)
            if errors:
                raise ModelConstructionError(
                    spec.provider,
                    spec.id,
                    ValueError(f"capability mismatches: {errors}"),
                )

        try:
            return cls(id=spec.id, **kwargs)
        except (TypeError, ValueError) as exc:
            raise ModelConstructionError(spec.provider, spec.id, exc) from exc

    def _compose_kwargs(self, spec: ModelExpandedSpec, cls: type) -> dict[str, Any]:
        """Build the constructor kwargs dict, filtered against ``cls`` fields.

        Agno Model is a @dataclass (base.py v2.6.22). ``dataclasses.fields(cls)``
        returns the exact set of constructor parameters the concrete subclass
        accepts. We dump the spec (excluding None and the positional `id`) and
        keep only the keys present in that set. This silently drops
        provider-specific fields the target class does not declare — e.g.
        ``top_k`` when building OpenAIChat, ``reasoning_effort`` when building
        Claude (A3).

        Args:
            spec: The validated ModelExpandedSpec.
            cls: The resolved Agno Model subclass (a @dataclass).

        Returns:
            Dict of constructor kwargs safe to splat as ``cls(id=..., **kwargs)``.

        Raises:
            TypeError: If ``cls`` is not a dataclass (defensive — all Agno Models
                are dataclasses; surfaces a non-Agno class slipped into the
                registry). Re-raised as ModelConstructionError by the caller.
        """
        # ``id`` is passed positionally by build(); never include it in kwargs.
        # ``fallback`` is schema-only (slice #4 runtime); never forward it.
        # ``provider`` is a yaml-agno routing key, not an Agno constructor arg.
        # ``thinking`` is excluded due to a type mismatch: ModelExpandedSpec.thinking
        #   is ``bool | None`` but Claude.thinking is ``Dict[str, Any]``. Forwarding
        #   a bool to a dict-typed field would either TypeError (if the field is
        #   present, as on Claude) or silently drop (if absent, as on OpenAIChat).
        #   Users wanting extended thinking configure it via ``provider_kwargs``
        #   in a future slice. (Open Item #1 resolution, tasks.md.)
        excluded: set[str] = {"id", "fallback", "provider", "thinking"}
        candidates = spec.model_dump(exclude_none=True, exclude=excluded)

        # Defensive: confirm cls is a dataclass before introspecting. If a
        # non-dataclass slips into PROVIDER_REGISTRY, raise explicitly rather
        # than letting dataclasses.fields emit an opaque TypeError.
        if not dataclasses.is_dataclass(cls):
            raise TypeError(
                f"Cannot compose kwargs: {cls.__name__!r} is not a dataclass. "
                f"PROVIDER_REGISTRY entries MUST point at Agno Model subclasses."
            )

        allowed = {f.name for f in dataclasses.fields(cls)}
        return {key: value for key, value in candidates.items() if key in allowed}
