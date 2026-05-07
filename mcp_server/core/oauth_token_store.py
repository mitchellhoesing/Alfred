"""Encrypted-at-rest persistence for OAuth refresh tokens.

The token bytes are encrypted with a Fernet key derived from a user-supplied
passphrase via PBKDF2-HMAC-SHA256. The salt is generated on first save and
stored alongside the token file as ``<path>.salt``. Both files are written
with mode 0o600 on POSIX (best-effort on Windows).

The store is deliberately ``bytes``-in / ``bytes``-out — it knows nothing
about token shapes. The Google adapter is responsible for serializing its
:class:`google.oauth2.credentials.Credentials` to JSON before saving.
"""

from __future__ import annotations

import os
from base64 import urlsafe_b64encode
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from mcp_server.core.errors import AuthError


_PBKDF2_ITERATIONS = 480_000
_SALT_BYTES = 16
_SALT_SUFFIX = ".salt"


class EncryptedTokenStore:
    def __init__(self, path: Path, passphrase: str) -> None:
        if not passphrase:
            raise AuthError("EncryptedTokenStore requires a non-empty passphrase")
        self._path = path
        self._salt_path = path.with_name(path.name + _SALT_SUFFIX)
        self._passphrase = passphrase.encode("utf-8")

    def exists(self) -> bool:
        return self._path.exists()

    def save(self, payload: bytes) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        salt = self._load_or_create_salt()
        ciphertext = Fernet(self._derive_key(salt)).encrypt(payload)
        self._write_private(self._path, ciphertext)

    def load(self) -> bytes | None:
        if not self.exists():
            return None
        if not self._salt_path.exists():
            raise AuthError(
                f"Token file {self._path} exists but salt {self._salt_path} is missing"
            )
        salt = self._salt_path.read_bytes()
        key = self._derive_key(salt)
        try:
            return Fernet(key).decrypt(self._path.read_bytes())
        except InvalidToken as exc:
            raise AuthError(
                "Failed to decrypt token (wrong passphrase or corrupt file)"
            ) from exc

    def _load_or_create_salt(self) -> bytes:
        if self._salt_path.exists():
            return self._salt_path.read_bytes()
        self._salt_path.parent.mkdir(parents=True, exist_ok=True)
        salt = os.urandom(_SALT_BYTES)
        self._write_private(self._salt_path, salt)
        return salt

    def _derive_key(self, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=_PBKDF2_ITERATIONS,
        )
        return urlsafe_b64encode(kdf.derive(self._passphrase))

    @staticmethod
    def _write_private(path: Path, data: bytes) -> None:
        path.write_bytes(data)
        try:
            os.chmod(path, 0o600)
        except OSError:
            # Windows or restricted FS — best-effort only.
            pass
