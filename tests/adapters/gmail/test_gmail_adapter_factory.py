from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from google.oauth2.credentials import Credentials

from mcp_server.adapters.gmail.gmail_adapter_factory import (
    build_gmail_adapter,
)
from mcp_server.adapters.gmail.gmail_source_adapter import GmailSourceAdapter
from mcp_server.adapters.google_common.google_credentials_store import (
    GoogleCredentialsStore,
)
from mcp_server.core.errors import ConfigurationError
from mcp_server.core.oauth_token_store import EncryptedTokenStore


# Env validation, the no-cached-creds error, and the default token path are
# tested in tests/adapters/google_common/test_google_credentials_factory.py.
# This file only verifies the Gmail-specific wire-up: that the factory
# delegates to load_google_credentials and that errors propagate through.


def _full_env() -> dict[str, str]:
    return {
        "GOOGLE_CLIENT_ID": "client-id",
        "GOOGLE_CLIENT_SECRET": "client-secret",
        "ALFRED_TOKEN_PASSPHRASE": "hunter2",
    }


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
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        expiry=datetime(2999, 1, 1),
    )
    creds_store.save(creds)


class _FactoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.token_path = Path(self._tmp.name) / "google_token.json"


class TestHappyPath(_FactoryTestCase):
    def test_returns_wired_gmail_adapter(self) -> None:
        _save_creds(self.token_path, "hunter2")

        with patch(
            "mcp_server.adapters.gmail.gmail_adapter_factory.build"
        ) as mock_build:
            mock_build.return_value = MagicMock()
            adapter = build_gmail_adapter(
                _full_env(), token_path=self.token_path
            )

        self.assertIsInstance(adapter, GmailSourceAdapter)
        self.assertEqual(adapter.capabilities.source_name, "gmail")

        mock_build.assert_called_once()
        args, kwargs = mock_build.call_args
        self.assertEqual(args[0], "gmail")
        self.assertEqual(args[1], "v1")
        self.assertIn("credentials", kwargs)


class TestErrorPropagation(_FactoryTestCase):
    def test_no_cached_credentials_raises_configuration_error(self) -> None:
        with self.assertRaises(ConfigurationError):
            build_gmail_adapter(_full_env(), token_path=self.token_path)


if __name__ == "__main__":
    unittest.main()
