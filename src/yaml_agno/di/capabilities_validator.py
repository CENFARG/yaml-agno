"""ModelCapabilitiesValidator — validación pure-data, config-time (SPEC_14 #3, A6).

Lee ``PROVIDER_REGISTRY[provider].capabilities`` (DECLARED, no runtime-verificado
— ver provider_capabilities.py docstring) y confirma que la *intención* del
ModelExpandedSpec (reasoning, caching) está soportada por la *declaración* del
provider. NO toca clases Agno. NO hace calls de red.

Reglas (slice #3):
  - ``spec.reasoning_effort`` o ``spec.thinking`` seteados requieren
    ``capabilities.reasoning == True``.
  - ``spec.cache_response`` o ``spec.cache_ttl`` o ``spec.cache_dir`` seteados
    requieren ``capabilities.caching == True``.

El validator devuelve ``list[str]`` de errores (vacía = OK). El caller decide
si es hard-error (ProviderFactory con ``validate_capabilities=True``) o warning.

@ai-directive: Las capabilities son DECLARED, NOT RUNTIME-VERIFIED. Este
    validator confirma intención vs declaración, NO garantiza que la API viva
    lo acepte.
"""

from __future__ import annotations

from yaml_agno.di.provider_capabilities import ProviderCapabilities
from yaml_agno.models.model_spec import ModelExpandedSpec

__all__ = ["ModelCapabilitiesValidator"]


class ModelCapabilitiesValidator:
    """Pure-data validator of ModelExpandedSpec intent vs declared capabilities.

    Stateless. Every method is a staticmethod that reads the spec + the declared
    ProviderCapabilities and returns a list of human-readable error strings.

    Example:
        >>> errors = ModelCapabilitiesValidator.validate(spec, caps)
        >>> if errors:
        ...     raise ValueError(errors)
    """

    @staticmethod
    def validate(spec: ModelExpandedSpec, capabilities: ProviderCapabilities) -> list[str]:
        """Run all declared-capability checks and return the accumulated errors.

        Args:
            spec: The model spec expressing intent.
            capabilities: The declared ProviderCapabilities for the provider.

        Returns:
            List of error strings. Empty list means the spec's intent is fully
            covered by the provider's declared capabilities.
        """
        errors: list[str] = []
        errors.extend(ModelCapabilitiesValidator._check_reasoning(spec, capabilities))
        errors.extend(ModelCapabilitiesValidator._check_caching(spec, capabilities))
        return errors

    @staticmethod
    def _check_reasoning(
        spec: ModelExpandedSpec, capabilities: ProviderCapabilities
    ) -> list[str]:
        """Reasoning intent (reasoning_effort/thinking) requires declared reasoning.

        Args:
            spec: The model spec.
            capabilities: Declared capabilities.

        Returns:
            Error list (empty if OK or if no reasoning intent was expressed).
        """
        if (spec.reasoning_effort is not None or spec.thinking is not None) and not capabilities.reasoning:
            return [
                f"Provider declares reasoning=False but spec sets "
                f"reasoning_effort={spec.reasoning_effort!r} or thinking={spec.thinking!r}."
            ]
        return []

    @staticmethod
    def _check_caching(
        spec: ModelExpandedSpec, capabilities: ProviderCapabilities
    ) -> list[str]:
        """Caching intent (cache_response/cache_ttl/cache_dir) requires declared caching.

        Args:
            spec: The model spec.
            capabilities: Declared capabilities.

        Returns:
            Error list (empty if OK or if no caching intent was expressed).
        """
        caching_intent = (
            spec.cache_response is not None
            or spec.cache_ttl is not None
            or spec.cache_dir is not None
        )
        if caching_intent and not capabilities.caching:
            return [
                f"Provider declares caching=False but spec sets cache_response="
                f"{spec.cache_response!r}, cache_ttl={spec.cache_ttl!r}, or "
                f"cache_dir={spec.cache_dir!r}."
            ]
        return []
