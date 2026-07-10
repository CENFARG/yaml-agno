"""build_fallback_chain — ensambla la cadena de fallback Agno (SPEC_14 #4 DOMAIN).

COMPOSE los slices #2 y #3: parsea cada entrada de
``FallbackConfig.fallback_models`` vía :func:`parse_model_spec`, canonicaliza
el provider vía :class:`ProviderResolver`, y construye cada instancia Agno Model
vía ``factory.build(spec)``. La primaria va en el índice 0; la lista se
trunca a ``max_fallback_hops`` FALLBACK hops (primario + N hops).

Devuelve INSTANCIAS (no specs) — ver ADR A3. El tipo es ``list[Any]`` para no
acoplar el type-checker al tipo ``Model`` de Agno (resuelto dinámicamente vía
``resolve_class``).

Truncación (Open Item #1 — CORRECCIÓN del design literal):
    ``max_fallback_hops`` cuenta los hops FALLBACK (después del primario), NO la
    longitud total. La cadena se trunca a ``chain[:max_fallback_hops + 1]``
    (primario en índice 0 + hasta N fallbacks). El design literal usaba
    ``chain[:max_fallback_hops]`` — off-by-one que producía N entradas en vez de
    N+1. El test RED fijó la expectativa correcta (max_fallback_hops=2 + 2
    fallbacks -> longitud 3).

@ai-directive: NO reimplementes parse_model_spec / ProviderResolver — delega.
    NO construyas instancias directamente — usa factory.build. NO resuelvas
    ``{"alias": name}`` refs (TASK_013 unshipped) — REJECT con NotImplementedError.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yaml_agno.models.model_spec import (
    ModelExpandedSpec,
    ProviderResolver,
    parse_model_spec,
)

# ProviderFactory is only a type hint on the ``factory`` parameter (runtime
# duck-typing). Importing it at module level would create a circular import:
# models.fallback_chain -> di.provider_factory -> di.capabilities_validator ->
# models.model_spec. Guarding it under TYPE_CHECKING breaks the cycle while
# keeping the public re-export from ``yaml_agno.models``.
if TYPE_CHECKING:
    from yaml_agno.di.provider_factory import ProviderFactory

__all__ = ["build_fallback_chain"]


def build_fallback_chain(
    primary: ModelExpandedSpec,
    factory: ProviderFactory,
    *,
    resolver: ProviderResolver | None = None,
) -> list[Any]:
    """Assemble the ordered fallback chain as Agno Model instances.

    Pipeline:
      1. Build the primary model via ``factory.build(primary)`` -> index 0.
      2. If ``primary.fallback is None``, return ``[primary_model]``.
      3. Otherwise iterate ``primary.fallback.fallback_models``; for each entry:
         - dict with a single ``"alias"`` key -> raise ``NotImplementedError``
           (definitions registry = TASK_013, unshipped; A5).
         - ``str | dict`` -> :func:`parse_model_spec` ->
           :meth:`ProviderResolver.resolve` (canonicalize alias) ->
           ``factory.build(spec)`` -> Model instance.
      4. Truncate the resulting list to ``primary.fallback.max_fallback_hops``
         FALLBACK hops (inclusive of the primary): ``chain[:max_fallback_hops + 1]``.

    Args:
        primary: The primary model spec. When ``primary.fallback`` is set, its
            ``fallback_models`` and ``max_fallback_hops`` drive the chain.
        factory: ProviderFactory (slice #3) — builds each Agno Model instance.
        resolver: Optional ProviderResolver for alias canonicalization. Defaults
            to ``ProviderResolver()``; injectable for testing.

    Returns:
        Ordered list of Agno Model instances, primary first. Length is
        ``min(1 + len(fallback_models), max_fallback_hops + 1)`` when a fallback
        config exists, else ``[primary_model]`` (length 1).

    Raises:
        NotImplementedError: If a ``fallback_models`` entry is a dict whose only
            key is ``"alias"`` (definitions registry unshipped; A5).
        KeyError: Propagated from ``factory.build`` on unknown provider.
        ValueError: Propagated from ``parse_model_spec`` / ``ProviderResolver``
            on malformed input or unsupported provider.

    Example:
        >>> primary = ModelExpandedSpec(
        ...     provider="openai", id="gpt-4o",
        ...     fallback=FallbackConfig(fallback_models=["anthropic:claude-3-5-sonnet"]),
        ... )
        >>> chain = build_fallback_chain(primary, factory)
        >>> len(chain)
        2
    """
    active_resolver = resolver if resolver is not None else ProviderResolver()
    primary_model = factory.build(primary)

    if primary.fallback is None:
        return [primary_model]

    chain: list[Any] = [primary_model]
    for entry in primary.fallback.fallback_models:
        if isinstance(entry, dict) and set(entry.keys()) == {"alias"}:
            raise NotImplementedError(
                "Alias-by-name fallback refs ({'alias': ...}) require a "
                "definitions registry (TASK_013, unshipped). Use inline "
                "'provider:id' strings or {provider, id} dicts instead."
            )
        parsed = parse_model_spec(entry)
        resolved = active_resolver.resolve(parsed)
        # ProviderFactory.build expects a ModelExpandedSpec. parse_model_spec
        # returns ModelStringSpec for "provider:id" strings; after alias
        # canonicalization by the resolver, normalize to the expanded form so
        # the factory receives a single concrete type. model_validate over the
        # resolved spec's dump preserves provider/id and satisfies mypy strict.
        expanded = (
            resolved
            if isinstance(resolved, ModelExpandedSpec)
            else ModelExpandedSpec.model_validate(resolved.model_dump())
        )
        chain.append(factory.build(expanded))

    # Open Item #1 (CORRECCIÓN del design): max_fallback_hops cuenta hops
    # FALLBACK (no la longitud total). Primario en índice 0 + hasta N hops.
    max_hops = primary.fallback.max_fallback_hops
    return chain[: max_hops + 1]
