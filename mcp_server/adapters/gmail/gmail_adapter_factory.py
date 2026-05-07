"""Build a fully-wired :class:`GmailSourceAdapter` from env vars.

The MCP server's startup code (Phase 5) will call
:func:`build_gmail_adapter` and register the result on the shared
:class:`AdapterRegistry`. Keeping construction here — not in
``server.py`` — means the adapter wiring is unit-testable without
standing up an MCP server.

Credential loading + env validation are delegated to
:func:`load_google_credentials` in
:mod:`mcp_server.adapters.google_common.google_credentials_factory`,
so this factory only owns the source-specific bits: building the
``gmail v1`` discovery service and wrapping it in the API client and
source adapter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from googleapiclient.discovery import build

from mcp_server.adapters.gmail.gmail_api_client import GmailApiClient
from mcp_server.adapters.gmail.gmail_source_adapter import GmailSourceAdapter
from mcp_server.adapters.google_common.google_credentials_factory import (
    load_google_credentials,
)


def build_gmail_adapter(
    env: Mapping[str, str],
    *,
    token_path: Path | None = None,
) -> GmailSourceAdapter:
    """Wire env vars + cached credentials → adapter.

    See :func:`load_google_credentials` for the env-var contract and the
    ``ConfigurationError`` cases (missing env vars, no cached token).
    """
    credentials = load_google_credentials(env, token_path=token_path)
    service = build("gmail", "v1", credentials=credentials)
    api_client = GmailApiClient(service)
    return GmailSourceAdapter(api_client)
