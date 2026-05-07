from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from google.oauth2.credentials import Credentials

from mcp_server.adapters.google_common.__main__ import authorize_and_save
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


def _fake_credentials() -> Credentials:
    return Credentials(
        token="bootstrap-access-token",
        refresh_token="bootstrap-refresh-token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client-id",
        client_secret="client-secret",
        scopes=[
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/gmail.readonly",
        ],
        expiry=datetime(2999, 1, 1),
    )


class _BootstrapTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.token_path = Path(self._tmp.name) / "google_token.json"

        self.fake_flow = MagicMock()
        self.fake_flow.run.return_value = _fake_credentials()

        def _factory(*, client_id: str, client_secret: str) -> MagicMock:
            return self.fake_flow

        self.factory = _factory


class TestAuthorizeAndSaveHappyPath(_BootstrapTestCase):
    def test_runs_flow_and_writes_encrypted_credentials(self) -> None:
        result_path = authorize_and_save(
            _full_env(),
            token_path=self.token_path,
            flow_factory=self.factory,
        )

        self.assertEqual(result_path, self.token_path)
        self.fake_flow.run.assert_called_once()

        # The token file exists and is encrypted (no plaintext refresh token).
        self.assertTrue(self.token_path.exists())
        on_disk = self.token_path.read_bytes()
        self.assertNotIn(b"bootstrap-refresh-token", on_disk)

    def test_saved_credentials_round_trip_via_credentials_store(self) -> None:
        authorize_and_save(
            _full_env(),
            token_path=self.token_path,
            flow_factory=self.factory,
        )

        # Re-load the same path with the same passphrase and verify we
        # get back a usable Credentials object.
        token_store = EncryptedTokenStore(
            self.token_path, passphrase="hunter2"
        )
        creds = GoogleCredentialsStore(token_store).load()
        assert creds is not None
        self.assertEqual(creds.refresh_token, "bootstrap-refresh-token")

    def test_creates_parent_directories_if_missing(self) -> None:
        nested_path = Path(self._tmp.name) / "alfred-config" / "tokens" / "g.json"
        self.assertFalse(nested_path.parent.exists())

        authorize_and_save(
            _full_env(),
            token_path=nested_path,
            flow_factory=self.factory,
        )

        self.assertTrue(nested_path.exists())


class TestAuthorizeAndSaveMissingEnvVars(_BootstrapTestCase):
    def test_missing_client_id_raises(self) -> None:
        env = _full_env()
        del env["GOOGLE_CLIENT_ID"]
        with self.assertRaises(ConfigurationError) as cm:
            authorize_and_save(
                env, token_path=self.token_path, flow_factory=self.factory
            )
        self.assertIn("GOOGLE_CLIENT_ID", str(cm.exception))

    def test_missing_passphrase_raises(self) -> None:
        env = _full_env()
        del env["ALFRED_TOKEN_PASSPHRASE"]
        with self.assertRaises(ConfigurationError):
            authorize_and_save(
                env, token_path=self.token_path, flow_factory=self.factory
            )

    def test_oauth_flow_is_not_run_when_env_invalid(self) -> None:
        env = _full_env({"GOOGLE_CLIENT_SECRET": ""})
        with self.assertRaises(ConfigurationError):
            authorize_and_save(
                env, token_path=self.token_path, flow_factory=self.factory
            )
        self.fake_flow.run.assert_not_called()


class TestTokenPathFromEnv(_BootstrapTestCase):
    def test_alfred_google_token_path_env_var_overrides_default(self) -> None:
        custom = Path(self._tmp.name) / "custom_token.json"
        env = _full_env({"ALFRED_GOOGLE_TOKEN_PATH": str(custom)})

        result = authorize_and_save(env, flow_factory=self.factory)

        self.assertEqual(result, custom)
        self.assertTrue(custom.exists())


if __name__ == "__main__":
    unittest.main()
