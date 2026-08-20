"""No-network Model subclass for integration testing (S5a.1).

Public extension point subclassing agno.models.base.Model that returns
deterministic canned replies without any network calls or API keys.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

from agno.models.base import Model
from agno.models.response import ModelResponse


class StaticReplyModel(Model):
    """A deterministic, no-network Model subclass for integration tests."""

    def __init__(
        self,
        id: str = "static-reply",
        canned_reply: str = "canned reply",
        **kwargs: Any,
    ) -> None:
        super().__init__(id=id, name="StaticReplyModel", provider="Static", **kwargs)
        self.canned_reply = canned_reply

    def invoke(self, *args: Any, **kwargs: Any) -> ModelResponse:
        """Return synchronous canned response."""
        return ModelResponse(content=self.canned_reply)

    async def ainvoke(self, *args: Any, **kwargs: Any) -> ModelResponse:
        """Return asynchronous canned response."""
        return ModelResponse(content=self.canned_reply)

    def invoke_stream(self, *args: Any, **kwargs: Any) -> Iterator[ModelResponse]:
        """Yield synchronous canned streaming response."""
        yield ModelResponse(content=self.canned_reply)

    async def ainvoke_stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[ModelResponse]:
        """Yield asynchronous canned streaming response."""
        yield ModelResponse(content=self.canned_reply)

    def _parse_provider_response(self, response: Any, **kwargs: Any) -> ModelResponse:
        """Parse provider response into ModelResponse."""
        return ModelResponse(content=self.canned_reply)

    def _parse_provider_response_delta(self, delta: Any, **kwargs: Any) -> ModelResponse:
        """Parse streaming provider response delta into ModelResponse."""
        return ModelResponse(content=self.canned_reply)
