"""Persist :class:`google.oauth2.credentials.Credentials` through Alfred's
encrypted token store.

:class:`mcp_server.core.oauth_token_store.EncryptedTokenStore` is bytes-in
/ bytes-out — it knows nothing about token shapes. This module owns the
JSON serialization of :class:`Credentials`. Splitting these two concerns
means the encryption layer stays generic (reusable for any future source)
and the Google-specific shape lives next to the rest of the Google
adapter machinery, shared by every Google data source.
"""

from __future__ import annotations

import json
from typing import cast

from google.oauth2.credentials import Credentials

from mcp_server.core.oauth_token_store import EncryptedTokenStore


class GoogleCredentialsStore:
    """Typed wrapper that round-trips ``Credentials`` through encrypted bytes."""

    def __init__(self, token_store: EncryptedTokenStore) -> None:
        self._token_store = token_store

    def save(self, credentials: Credentials) -> None:
        payload_str: str = credentials.to_json()  # type: ignore[no-untyped-call]
        self._token_store.save(payload_str.encode("utf-8"))

    def load(self) -> Credentials | None:
        payload = self._token_store.load()
        if payload is None:
            return None
        info = json.loads(payload.decode("utf-8"))
        return cast(
            Credentials,
            Credentials.from_authorized_user_info(info),  # type: ignore[no-untyped-call]
        )

    def has_credentials(self) -> bool:
        return self._token_store.exists()
