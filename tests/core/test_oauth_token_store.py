from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mcp_server.core.errors import AuthError
from mcp_server.core.oauth_token_store import EncryptedTokenStore


class TestEncryptedTokenStore(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "token.json"

    def test_round_trip(self) -> None:
        store = EncryptedTokenStore(self.path, passphrase="hunter2")
        store.save(b'{"refresh_token": "abc"}')
        self.assertEqual(store.load(), b'{"refresh_token": "abc"}')

    def test_exists_before_and_after_save(self) -> None:
        store = EncryptedTokenStore(self.path, passphrase="hunter2")
        self.assertFalse(store.exists())
        store.save(b"x")
        self.assertTrue(store.exists())

    def test_ciphertext_does_not_contain_plaintext(self) -> None:
        secret = b"super-secret-refresh-token-ABC123"
        EncryptedTokenStore(self.path, passphrase="hunter2").save(secret)
        on_disk = self.path.read_bytes()
        self.assertNotIn(secret, on_disk)

    def test_wrong_passphrase_raises_autherror(self) -> None:
        EncryptedTokenStore(self.path, passphrase="right").save(b"payload")
        wrong = EncryptedTokenStore(self.path, passphrase="wrong")
        with self.assertRaises(AuthError):
            wrong.load()

    def test_load_returns_none_when_missing(self) -> None:
        store = EncryptedTokenStore(self.path, passphrase="x")
        self.assertIsNone(store.load())

    def test_empty_passphrase_rejected(self) -> None:
        with self.assertRaises(AuthError):
            EncryptedTokenStore(self.path, passphrase="")

    def test_missing_salt_after_token_raises(self) -> None:
        store = EncryptedTokenStore(self.path, passphrase="hunter2")
        store.save(b"payload")
        # Simulate the salt going missing on disk.
        self.path.with_name(self.path.name + ".salt").unlink()
        with self.assertRaises(AuthError):
            store.load()

    def test_nested_directory_created(self) -> None:
        nested = Path(self._tmp.name) / "deep" / "nest" / "token.json"
        store = EncryptedTokenStore(nested, passphrase="x")
        store.save(b"payload")
        self.assertTrue(nested.exists())


if __name__ == "__main__":
    unittest.main()
