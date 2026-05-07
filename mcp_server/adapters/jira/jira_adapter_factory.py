"""Build a fully-wired :class:`JiraSourceAdapter` from environment vars.

The MCP server's startup code (Phase 5) will call :func:`build_jira_adapter`
with ``os.environ`` (or a parsed ``.env``) and register the result on the
shared :class:`AdapterRegistry`. Keeping construction here — not in
``server.py`` — means the adapter wiring is unit-testable without standing
up an MCP server.
"""

from __future__ import annotations

from typing import Mapping

from mcp_server.adapters.jira.jira_cloud_http_client import (
    JiraCloudHttpClient,
    JiraCloudHttpClientConfig,
)
from mcp_server.adapters.jira.jira_source_adapter import JiraSourceAdapter
from mcp_server.core.auth_provider import StaticJiraAuthProvider
from mcp_server.core.errors import ConfigurationError


def build_jira_adapter(env: Mapping[str, str]) -> JiraSourceAdapter:
    """Wire env vars → adapter. Raises :class:`ConfigurationError` on missing.

    Required env vars: ``JIRA_BASE_URL``, ``JIRA_EMAIL``, ``JIRA_API_TOKEN``.
    Empty or whitespace-only values are treated as missing, since they
    almost always indicate a misconfigured ``.env`` file rather than a
    deliberate setting.
    """
    base_url = _required(env, "JIRA_BASE_URL")
    email = _required(env, "JIRA_EMAIL")
    api_token = _required(env, "JIRA_API_TOKEN")
    auth = StaticJiraAuthProvider(email=email, api_token=api_token)
    config = JiraCloudHttpClientConfig(base_url=base_url)
    client = JiraCloudHttpClient(config, auth)
    return JiraSourceAdapter(client, base_url=base_url)


def _required(env: Mapping[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise ConfigurationError(
            f"Missing required environment variable: {key}"
        )
    return value
