"""Run Google's installed-app OAuth flow and return fresh Credentials.

Wraps :class:`google_auth_oauthlib.flow.InstalledAppFlow.run_local_server`.
The flow opens a local browser, the user authorizes, and the call blocks
until the local HTTP callback receives the auth code. It is intended to
run **interactively** from the package's CLI entry point
(``python -m mcp_server.adapters.google_common``); the running MCP
server never invokes this path — it only loads cached credentials via the
:class:`GoogleCredentialsAuthProvider`.

The default scope set covers every Google data source Alfred reads. A
single OAuth grant produces one refresh token usable by every Google
adapter, so each source-specific adapter package shares one cached token
file.
"""

from __future__ import annotations

from typing import Sequence, cast

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


GOOGLE_OAUTH_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
)


class GoogleOAuthFlow:
    """Run the desktop installed-app OAuth flow on demand."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        scopes: Sequence[str] = GOOGLE_OAUTH_SCOPES,
        local_server_port: int = 0,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._scopes = list(scopes)
        self._port = local_server_port

    def run(self) -> Credentials:
        flow = InstalledAppFlow.from_client_config(
            client_config={
                "installed": {
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            },
            scopes=self._scopes,
        )
        return cast(Credentials, flow.run_local_server(port=self._port))
