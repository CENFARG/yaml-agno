"""DIReference value object. Validates the OWN yaml-agno syntax ``${provider.key}``
used to inject dynamic values into YAML fields. This syntax does not exist in
Agno, so it is the single value object defined by yaml-agno."""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DIReference(BaseModel):
    """Value object for a yaml-agno dependency-injection reference.

    Represents a string containing one or more ``${provider.key}`` templates that
    are resolved at runtime by the DIFactory (SPEC_00 DI System) against the
    configured providers (database, env, api, file).

    Invariant:
        - ``template`` contains at least one well-formed ``${provider.key}`` token.

    Attributes:
        template: The raw string with ``${provider.key}`` tokens.

    Example:
        >>> ref = DIReference(template="Hello ${user_db.name}")
        >>> ref.tokens
        [('user_db', 'name')]
        >>> ref.resolve({"user_db.name": "Alice"})
        'Hello Alice'
    """

    # frozen=True: value object is immutable after construction. Hashable, safe
    # to share across configs. This is the ONLY frozen model in this change.
    model_config = ConfigDict(frozen=True)

    template: str = Field(..., description="String with ${provider.key} tokens.")

    @field_validator("template")
    @classmethod
    def validate_format(cls, v: str) -> str:
        """Ensure template contains at least one ``${provider.key}`` token.

        Regex: ``\\$\\{[a-z_]+(\\.[a-z0-9_]+)*\\}``
          - provider segment: lowercase letters + underscore.
          - key segments: dot-separated, lowercase letters/digits/underscore.
          - one or more tokens must be present.
        """
        if not re.search(r"\$\{[a-z_]+(\.[a-z0-9_]+)*\}", v):
            raise ValueError(f"Invalid DI reference format: {v}. Expected ${{provider.key}}.")
        return v

    @property
    def tokens(self) -> list[tuple[str, str]]:
        """Extract all (provider, key) tokens found in the template.

        Returns:
            A list of (provider, full_key) tuples, in order of appearance.
            Example: ``"Hello ${user_db.name} ${env.API_KEY}"`` ->
                     ``[("user_db", "name"), ("env", "API_KEY")]``
        """
        return [
            (m.group(1), m.group(2))
            for m in re.finditer(r"\$\{([a-z_]+)\.([a-z0-9_.]+)\}", self.template)
        ]

    def resolve(self, resolved_values: dict[str, Any]) -> str:
        """Replace every ``${provider.key}`` token with its resolved value.

        SELF-CONTAINED: does NOT touch DI infrastructure. The caller (DIFactory
        in SPEC_00) is responsible for producing ``resolved_values`` by querying
        providers (DB/env/api/file). This method only does string replacement.

        Args:
            resolved_values: Mapping of ``"provider.key"`` -> resolved value.

        Returns:
            The template with all tokens substituted by their string values.

        Raises:
            KeyError: If a token has no resolved value in ``resolved_values``.
        """
        out = self.template
        for provider, key in self.tokens:
            full_key = f"{provider}.{key}"
            if full_key not in resolved_values:
                raise KeyError(f"Unresolved DI reference: ${{{full_key}}}")
            out = out.replace(f"${{{full_key}}}", str(resolved_values[full_key]))
        return out
