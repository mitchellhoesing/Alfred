"""Build a fully-wired :class:`GoogleCalendarSourceAdapter` from env vars.

The MCP server's startup code (Phase 5) will call
:func:`build_google_calendar_adapter` and register the result on the
shared :class:`AdapterRegistry`. Keeping construction here — not in
``server.py`` — means the adapter wiring is unit-testable without
standing up an MCP server.

Credential loading + env validation are delegated to
:func:`load_google_credentials` in
:mod:`mcp_server.adapters.google_common.google_credentials_factory`,
so this factory only owns the source-specific bits: building the
``calendar v3`` discovery service and wrapping it in the API client and
source adapter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from googleapiclient.discovery import build

from mcp_server.adapters.google_calendar.google_calendar_api_client import (
    GoogleCalendarApiClient,
)
from mcp_server.adapters.google_calendar.google_calendar_source_adapter import (
    GoogleCalendarSourceAdapter,
)
from mcp_server.adapters.google_common.google_credentials_factory import (
    load_google_credentials,
)


def build_google_calendar_adapter(
    env: Mapping[str, str],
    *,
    token_path: Path | None = None,
) -> GoogleCalendarSourceAdapter:
    """Wire env vars + cached credentials → adapter.

    See :func:`load_google_credentials` for the env-var contract and the
    ``ConfigurationError`` cases (missing env vars, no cached token).
    """
    credentials = load_google_credentials(env, token_path=token_path)
    service = build("calendar", "v3", credentials=credentials)
    api_client = GoogleCalendarApiClient(service)
    return GoogleCalendarSourceAdapter(api_client)
