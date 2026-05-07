"""AuthProvider that loads, refreshes, and persists Google Credentials.

The provider is the only place in the Google adapters that knows about
the "refresh on expired" lifecycle. API clients and source adapters
depend on the abstract :class:`AuthProvider[Credentials]` (DIP), so they
are unaware of where the credentials live or how they get refreshed.

Refresh policy:

- The first call to :meth:`get_credentials` lazily loads from the store.
- If no credentials are cached on disk, raises :class:`AuthError` with an
  actionable message that tells the operator to run the CLI auth command.
- If the loaded credentials are expired *and* carry a refresh token, the
  provider refreshes them via the injected request factory and saves the
  refreshed Credentials back to disk so the next process startup gets a
  warm token.
- Subsequent calls return the cached, in-memory Credentials. Google's own
  HTTP transport handles mid-process refreshes inside the underlying
  library; we do not chase those updates back to disk because the refresh
  token rarely changes and the next startup will reconcile.
"""

from __future__ import annotations

from typing import Callable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from mcp_server.adapters.google_common.google_credentials_store import (
    GoogleCredentialsStore,
)
from mcp_server.core.auth_provider import AuthProvider
from mcp_server.core.errors import AuthError


_AUTH_HINT = (
    "No cached Google credentials. Run "
    "`python -m mcp_server.adapters.google_common` to authorize."
)


class GoogleCredentialsAuthProvider(AuthProvider[Credentials]):
    """Concrete :class:`AuthProvider` for Google OAuth Credentials."""

    def __init__(
        self,
        store: GoogleCredentialsStore,
        *,
        request_factory: Callable[[], Request] = Request,
    ) -> None:
        self._store = store
        self._request_factory = request_factory
        self._cached: Credentials | None = None

    def get_credentials(self) -> Credentials:
        if self._cached is None:
            self._cached = self._store.load()
        if self._cached is None:
            raise AuthError(_AUTH_HINT)
        if self._cached.expired and self._cached.refresh_token:
            self._cached.refresh(self._request_factory())  # type: ignore[no-untyped-call]
            self._store.save(self._cached)
        return self._cached
