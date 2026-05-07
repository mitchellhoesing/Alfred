from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from google.oauth2.credentials import Credentials

from mcp_server.adapters.google_common.google_credentials_auth_provider import (
    GoogleCredentialsAuthProvider,
)
from mcp_server.adapters.google_common.google_credentials_store import (
    GoogleCredentialsStore,
)
from mcp_server.core.errors import AuthError
from mcp_server.core.oauth_token_store import EncryptedTokenStore


_PAST = datetime(2020, 1, 1)
_FUTURE = datetime(2999, 1, 1)


def _make_credentials(*, expiry: datetime | None) -> Credentials:
    return Credentials(
        token="access",
        refresh_token="refresh",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="cid",
        client_secret="cs",
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        expiry=expiry,
    )


class _AuthProviderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        path = Path(self._tmp.name) / "google_token.json"
        token_store = EncryptedTokenStore(path, passphrase="hunter2")
        self.store = GoogleCredentialsStore(token_store)


class TestNoCachedCredentials(_AuthProviderTestCase):
    def test_raises_auth_error_with_actionable_message(self) -> None:
        provider = GoogleCredentialsAuthProvider(self.store)
        with self.assertRaises(AuthError) as cm:
            provider.get_credentials()
        # Message should tell the user how to fix it
        self.assertIn("python -m", str(cm.exception))


class TestCachedNotExpired(_AuthProviderTestCase):
    def test_returns_loaded_credentials(self) -> None:
        original = _make_credentials(expiry=_FUTURE)
        self.store.save(original)
        provider = GoogleCredentialsAuthProvider(self.store)

        creds = provider.get_credentials()
        self.assertEqual(creds.refresh_token, "refresh")

    def test_does_not_refresh_when_not_expired(self) -> None:
        original = _make_credentials(expiry=_FUTURE)
        self.store.save(original)
        provider = GoogleCredentialsAuthProvider(self.store)

        # Patch the refresh method on whichever Credentials is loaded
        loaded_first = provider.get_credentials()
        loaded_first.refresh = MagicMock()  # type: ignore[method-assign]
        provider.get_credentials()  # second call — must not refresh
        loaded_first.refresh.assert_not_called()

    def test_subsequent_calls_return_same_cached_object(self) -> None:
        self.store.save(_make_credentials(expiry=_FUTURE))
        provider = GoogleCredentialsAuthProvider(self.store)
        first = provider.get_credentials()
        second = provider.get_credentials()
        self.assertIs(first, second)


class TestCachedExpired(_AuthProviderTestCase):
    def test_refreshes_and_saves_back(self) -> None:
        self.store.save(_make_credentials(expiry=_PAST))
        provider = GoogleCredentialsAuthProvider(self.store)

        # Manually pre-load so we can mock refresh on the cached instance
        # by triggering one get_credentials cycle:
        # Instead, reach into the provider after first call.
        creds = self.store.load()
        assert creds is not None
        creds.refresh = MagicMock(side_effect=lambda req: setattr(creds, "expiry", _FUTURE))  # type: ignore[method-assign]

        # Inject the pre-mocked credentials directly on the provider
        provider._cached = creds  # type: ignore[attr-defined]

        save_spy = MagicMock(wraps=self.store.save)
        self.store.save = save_spy  # type: ignore[method-assign]

        result = provider.get_credentials()
        self.assertIs(result, creds)
        creds.refresh.assert_called_once()
        save_spy.assert_called_once_with(creds)

    def test_does_not_refresh_when_no_refresh_token(self) -> None:
        # Edge case: an access-only token (no refresh_token) — provider should
        # return it as-is rather than crashing on a None refresh_token.
        creds_no_refresh = Credentials(
            token="just-access",
            refresh_token=None,
            token_uri="https://oauth2.googleapis.com/token",
            client_id="cid",
            client_secret="cs",
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
            expiry=_PAST,
        )
        # Can't go through self.store because from_authorized_user_info
        # requires refresh_token; inject directly.
        provider = GoogleCredentialsAuthProvider(self.store)
        provider._cached = creds_no_refresh  # type: ignore[attr-defined]
        creds_no_refresh.refresh = MagicMock()  # type: ignore[method-assign]

        result = provider.get_credentials()
        self.assertIs(result, creds_no_refresh)
        creds_no_refresh.refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
