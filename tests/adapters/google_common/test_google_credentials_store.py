from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from google.oauth2.credentials import Credentials

from mcp_server.adapters.google_common.google_credentials_store import (
    GoogleCredentialsStore,
)
from mcp_server.core.oauth_token_store import EncryptedTokenStore


_SCOPES = (
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
)


def _sample_credentials() -> Credentials:
    return Credentials(
        token="access-token-abc",
        refresh_token="refresh-token-xyz",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client-id-1",
        client_secret="client-secret-1",
        scopes=list(_SCOPES),
        expiry=datetime(2026, 5, 4, 14, 0),
    )


class TestGoogleCredentialsStore(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        path = Path(self._tmp.name) / "google_token.json"
        self.token_store = EncryptedTokenStore(path, passphrase="hunter2")
        self.store = GoogleCredentialsStore(self.token_store)

    def test_load_returns_none_when_empty(self) -> None:
        self.assertIsNone(self.store.load())

    def test_has_credentials_false_when_empty(self) -> None:
        self.assertFalse(self.store.has_credentials())

    def test_round_trip_preserves_essential_fields(self) -> None:
        original = _sample_credentials()
        self.store.save(original)
        loaded = self.store.load()

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.refresh_token, original.refresh_token)
        self.assertEqual(loaded.token, original.token)
        self.assertEqual(loaded.client_id, original.client_id)
        self.assertEqual(loaded.client_secret, original.client_secret)
        self.assertEqual(loaded.token_uri, original.token_uri)
        self.assertEqual(set(loaded.scopes), set(original.scopes))

    def test_has_credentials_true_after_save(self) -> None:
        self.store.save(_sample_credentials())
        self.assertTrue(self.store.has_credentials())

    def test_save_writes_encrypted_bytes(self) -> None:
        # Verify the on-disk bytes do NOT contain the refresh token in cleartext.
        creds = _sample_credentials()
        self.store.save(creds)
        on_disk = (Path(self._tmp.name) / "google_token.json").read_bytes()
        self.assertNotIn(b"refresh-token-xyz", on_disk)
        self.assertNotIn(b"access-token-abc", on_disk)

    def test_overwrite_replaces_previous_credentials(self) -> None:
        first = _sample_credentials()
        self.store.save(first)
        second = Credentials(
            token="newer",
            refresh_token="newer-refresh",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="client-id-1",
            client_secret="client-secret-1",
            scopes=list(_SCOPES),
        )
        self.store.save(second)
        loaded = self.store.load()
        assert loaded is not None
        self.assertEqual(loaded.refresh_token, "newer-refresh")


if __name__ == "__main__":
    unittest.main()
