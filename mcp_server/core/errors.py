"""Domain exceptions for Alfred. Adapters raise AdapterError or its subclasses."""

from __future__ import annotations


class AlfredError(Exception):
    """Base exception for every error raised inside Alfred."""


class ConfigurationError(AlfredError):
    """Required configuration is missing or invalid (env var, file, etc.)."""


class AuthError(AlfredError):
    """Authentication or credential decryption failed."""


class AdapterError(AlfredError):
    """A SourceAdapter failed while talking to its upstream API."""


class RateLimitError(AdapterError):
    """The upstream API rate-limited the adapter.

    ``retry_after_seconds`` carries the value of the HTTP ``Retry-After``
    header when the adapter could parse one, so callers (or future retry
    middleware) can back off without re-parsing the response.
    """

    retry_after_seconds: int | None

    def __init__(
        self, message: str, *, retry_after_seconds: int | None = None
    ) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ItemNotFoundError(AdapterError):
    """SourceAdapter.get() was called with an unknown item id."""
