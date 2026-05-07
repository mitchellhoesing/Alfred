"""Interactive OAuth bootstrap for Alfred's Google adapters.

Run once before starting the MCP server::

    python -m mcp_server.adapters.google_common

Reads ``GOOGLE_CLIENT_ID``, ``GOOGLE_CLIENT_SECRET``, and
``ALFRED_TOKEN_PASSPHRASE`` from the environment (``.env`` is loaded if
present), opens the user's browser to authorize the requested scopes
(:data:`GOOGLE_OAUTH_SCOPES`, covering Calendar + Gmail read-only), and
writes an encrypted refresh-token file to ``~/.alfred/google_token.json``
(or wherever ``ALFRED_GOOGLE_TOKEN_PATH`` points).

The CLI logic lives in :func:`authorize_and_save` so tests can drive it
with a fake OAuth flow.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping, Protocol

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials

from mcp_server.adapters.google_common.google_credentials_factory import (
    DEFAULT_GOOGLE_TOKEN_PATH,
)
from mcp_server.adapters.google_common.google_credentials_store import (
    GoogleCredentialsStore,
)
from mcp_server.adapters.google_common.google_oauth_flow import GoogleOAuthFlow
from mcp_server.core.errors import ConfigurationError
from mcp_server.core.oauth_token_store import EncryptedTokenStore


_TOKEN_PATH_ENV = "ALFRED_GOOGLE_TOKEN_PATH"


class _OAuthFlowFactory(Protocol):
    def __call__(self, *, client_id: str, client_secret: str) -> GoogleOAuthFlow: ...


def authorize_and_save(
    env: Mapping[str, str],
    *,
    token_path: Path | None = None,
    flow_factory: _OAuthFlowFactory | None = None,
) -> Path:
    """Run the installed-app OAuth flow and persist the resulting credentials.

    ``flow_factory`` is injectable for tests; production callers leave
    it unset so a real :class:`GoogleOAuthFlow` is constructed.

    Returns the path the encrypted credentials were written to. Raises
    :class:`ConfigurationError` if any required env var is missing.
    """
    client_id = _required(env, "GOOGLE_CLIENT_ID")
    client_secret = _required(env, "GOOGLE_CLIENT_SECRET")
    passphrase = _required(env, "ALFRED_TOKEN_PASSPHRASE")

    resolved = (
        token_path
        if token_path is not None
        else _path_from_env_or_default(env)
    )
    resolved.parent.mkdir(parents=True, exist_ok=True)

    factory = flow_factory if flow_factory is not None else _default_flow_factory
    flow = factory(client_id=client_id, client_secret=client_secret)
    credentials: Credentials = flow.run()

    token_store = EncryptedTokenStore(resolved, passphrase=passphrase)
    GoogleCredentialsStore(token_store).save(credentials)
    return resolved


def _default_flow_factory(
    *, client_id: str, client_secret: str
) -> GoogleOAuthFlow:
    return GoogleOAuthFlow(client_id=client_id, client_secret=client_secret)


def _path_from_env_or_default(env: Mapping[str, str]) -> Path:
    raw = env.get(_TOKEN_PATH_ENV, "").strip()
    return Path(raw) if raw else DEFAULT_GOOGLE_TOKEN_PATH


def _required(env: Mapping[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise ConfigurationError(
            f"Missing required environment variable: {key}"
        )
    return value


def main() -> None:
    load_dotenv()
    print("Starting Google OAuth flow. A browser window will open...")
    saved_path = authorize_and_save(dict(os.environ))
    print(f"Saved encrypted credentials to {saved_path}")


if __name__ == "__main__":
    try:
        main()
    except ConfigurationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
