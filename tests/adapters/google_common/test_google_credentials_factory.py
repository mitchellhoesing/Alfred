from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from google.oauth2.credentials import Credentials

from mcp_server.adapters.google_common.google_credentials_factory import (
    DEFAULT_GOOGLE_TOKEN_PATH,
    load_google_credentials,
)
from mcp_server.adapters.google_common.google_credentials_store import (
    GoogleCredentialsStore,
)
from mcp_server.core.errors import ConfigurationError
from mcp_server.core.oauth_token_store import EncryptedTokenStore


def _full_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    base = {
        "GOOGLE_CLIENT_ID": "client-id",
        "GOOGLE_CLIENT_SECRET": "client-secret",
        "ALFRED_TOKEN_PASSPHRASE": "hunter2",
    }
    if overrides:
        base.update(overrides)
    return base


def _save_creds(token_path: Path, passphrase: str) -> None:
    """Pre-populate an encrypted Credentials file at ``token_path``."""
    token_store = EncryptedTokenStore(token_path, passphrase=passphrase)
    creds_store = GoogleCredentialsStore(token_store)
    creds = Credentials(
        token="access",
        refresh_token="refresh",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client-id",
        client_secret="client-secret",
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        expiry=datetime(2999, 1, 1),
    )
    creds_store.save(creds)


class _TestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.token_path = Path(self._tmp.name) / "google_token.json"


class TestMissingEnvVars(_TestCase):
    def test_missing_client_id_raises(self) -> None:
        env = _full_env()
        del env["GOOGLE_CLIENT_ID"]
        with self.assertRaises(ConfigurationError) as cm:
            load_google_credentials(env, token_path=self.token_path)
        self.assertIn("GOOGLE_CLIENT_ID", str(cm.exception))

    def test_missing_client_secret_raises(self) -> None:
        env = _full_env()
        del env["GOOGLE_CLIENT_SECRET"]
        with self.assertRaises(ConfigurationError) as cm:
            load_google_credentials(env, token_path=self.token_path)
        self.assertIn("GOOGLE_CLIENT_SECRET", str(cm.exception))

    def test_missing_passphrase_raises(self) -> None:
        env = _full_env()
        del env["ALFRED_TOKEN_PASSPHRASE"]
        with self.assertRaises(ConfigurationError) as cm:
            load_google_credentials(env, token_path=self.token_path)
        self.assertIn("ALFRED_TOKEN_PASSPHRASE", str(cm.exception))

    def test_empty_value_treated_as_missing(self) -> None:
        env = _full_env({"GOOGLE_CLIENT_ID": ""})
        with self.assertRaises(ConfigurationError) as cm:
            load_google_credentials(env, token_path=self.token_path)
        self.assertIn("GOOGLE_CLIENT_ID", str(cm.exception))

    def test_whitespace_only_value_treated_as_missing(self) -> None:
        env = _full_env({"GOOGLE_CLIENT_SECRET": "   "})
        with self.assertRaises(ConfigurationError):
            load_google_credentials(env, token_path=self.token_path)


class TestNoCachedCredentials(_TestCase):
    def test_raises_with_actionable_message(self) -> None:
        with self.assertRaises(ConfigurationError) as cm:
            load_google_credentials(_full_env(), token_path=self.token_path)
        msg = str(cm.exception)
        self.assertIn("python -m", msg)
        self.assertIn(str(self.token_path), msg)


class TestHappyPath(_TestCase):
    def test_returns_credentials_loaded_from_disk(self) -> None:
        _save_creds(self.token_path, "hunter2")

        creds = load_google_credentials(
            _full_env(), token_path=self.token_path
        )

        self.assertIsInstance(creds, Credentials)
        self.assertEqual(creds.refresh_token, "refresh")
        self.assertEqual(creds.client_id, "client-id")


class TestDefaultTokenPath(unittest.TestCase):
    def test_default_path_under_home_alfred_dir(self) -> None:
        self.assertEqual(
            DEFAULT_GOOGLE_TOKEN_PATH,
            Path.home() / ".alfred" / "google_token.json",
        )


if __name__ == "__main__":
    unittest.main()
