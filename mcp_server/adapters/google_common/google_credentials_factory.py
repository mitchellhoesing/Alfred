"""Build a refreshed Google :class:`Credentials` from env vars + cached token.

Both Google adapter factories (Calendar, Gmail) need the same boilerplate
to go from env vars to a usable, refreshed Credentials object: validate
env, decrypt the cached refresh-token file, and refresh if expired. This
module owns that pipeline so each source-specific factory only has to
call ``build("calendar"|"gmail"|..., version, credentials=creds)`` and
wrap the resulting service in the source's API client + adapter.

A single OAuth grant produces one refresh token that covers every Google
scope Alfred uses (see :data:`GOOGLE_OAUTH_SCOPES`). All Google adapters
therefore share the same token file at :data:`DEFAULT_GOOGLE_TOKEN_PATH`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from google.oauth2.credentials import Credentials

from mcp_server.adapters.google_common.google_credentials_auth_provider import (
    GoogleCredentialsAuthProvider,
)
from mcp_server.adapters.google_common.google_credentials_store import (
    GoogleCredentialsStore,
)
from mcp_server.core.errors import ConfigurationError
from mcp_server.core.oauth_token_store import EncryptedTokenStore


DEFAULT_GOOGLE_TOKEN_PATH: Path = Path.home() / ".alfred" / "google_token.json"


def load_google_credentials(
    env: Mapping[str, str],
    *,
    token_path: Path | None = None,
) -> Credentials:
    """Validate env vars, decrypt the cached token, refresh if expired.

    Required env vars:

    - ``GOOGLE_CLIENT_ID`` / ``GOOGLE_CLIENT_SECRET`` — desktop OAuth
      client credentials. Created in the Google Cloud Console.
    - ``ALFRED_TOKEN_PASSPHRASE`` — passphrase used to derive the Fernet
      key that decrypts the cached refresh token on disk.

    Raises:
        ConfigurationError: when a required env var is missing/empty, or
            when no cached credentials exist at ``token_path``. Message
            includes the offending key (env case) or the resolved token
            path + actionable CLI hint (no-creds case).
        AuthError: passes through from :class:`GoogleCredentialsAuthProvider`
            on a failed refresh.
    """
    _required(env, "GOOGLE_CLIENT_ID")
    _required(env, "GOOGLE_CLIENT_SECRET")
    passphrase = _required(env, "ALFRED_TOKEN_PASSPHRASE")

    resolved_path = (
        token_path if token_path is not None else DEFAULT_GOOGLE_TOKEN_PATH
    )
    token_store = EncryptedTokenStore(resolved_path, passphrase=passphrase)
    credentials_store = GoogleCredentialsStore(token_store)

    if not credentials_store.has_credentials():
        raise ConfigurationError(
            f"No cached Google credentials at {resolved_path}. Run "
            f"`python -m mcp_server.adapters.google_common` to authorize."
        )

    auth_provider = GoogleCredentialsAuthProvider(credentials_store)
    return auth_provider.get_credentials()


def _required(env: Mapping[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise ConfigurationError(
            f"Missing required environment variable: {key}"
        )
    return value
