"""Concrete :class:`SourceAdapter` for Jira Cloud.

Bridges the async :class:`SourceAdapter` ABC to the sync
:class:`JiraCloudHttpClient` using :func:`asyncio.to_thread`. Each abstract
method has a private sync counterpart so the mapping/JQL logic stays
testable without standing up an event loop.

The adapter exposes one source-specific async method,
:meth:`JiraSourceAdapter.search_jql`, that returns canonical
:class:`Ticket` objects (not :class:`SearchHit`). It is intended to back a
``jira_search_jql`` MCP tool when the server is wired up in Phase 5.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Sequence

from mcp_server.adapters.jira.jira_cloud_http_client import JiraCloudHttpClient
from mcp_server.adapters.jira.jira_issue_mapper import (
    map_issue_to_search_hit,
    map_issue_to_ticket,
)
from mcp_server.adapters.jira.jql_query_builder import (
    JIRA_FIELDS,
    build_recent_jql,
    build_text_search_jql,
)
from mcp_server.core.canonical import SearchHit, Ticket
from mcp_server.core.source_adapter import AdapterCapabilities, SourceAdapter


_CAPABILITIES = AdapterCapabilities(
    source_name="jira",
    supports_search=True,
    supports_time_range=True,
    supports_threading=False,
)


class JiraSourceAdapter(SourceAdapter):
    """Adapter wiring Jira Cloud into Alfred's :class:`SourceAdapter` ABC."""

    def __init__(self, client: JiraCloudHttpClient, *, base_url: str) -> None:
        self._client = client
        self._base_url = base_url

    @property
    def capabilities(self) -> AdapterCapabilities:
        return _CAPABILITIES

    async def list_recent(
        self, *, since: datetime, limit: int
    ) -> Sequence[Ticket]:
        return await asyncio.to_thread(self._list_recent_sync, since, limit)

    async def get(self, item_id: str) -> Ticket:
        return await asyncio.to_thread(self._get_sync, item_id)

    async def search(
        self, query: str, *, limit: int
    ) -> Sequence[SearchHit]:
        return await asyncio.to_thread(self._search_sync, query, limit)

    async def search_jql(
        self, jql: str, *, limit: int
    ) -> Sequence[Ticket]:
        """Run a caller-supplied JQL query and return canonical Tickets.

        The JQL string is passed through to Jira **without escaping** —
        this method is the explicit "trusted JQL passthrough" hatch.
        Callers that want to splice user-supplied data into the query must
        escape it themselves with
        :func:`mcp_server.adapters.jira.jql_query_builder.escape_jql_string`.
        """
        return await asyncio.to_thread(self._search_jql_sync, jql, limit)

    def _list_recent_sync(
        self, since: datetime, limit: int
    ) -> tuple[Ticket, ...]:
        result = self._client.search_issues_jql(
            jql=build_recent_jql(since),
            fields=JIRA_FIELDS,
            limit=limit,
        )
        issues = result.get("issues") or ()
        return tuple(
            map_issue_to_ticket(issue, base_url=self._base_url)
            for issue in issues
        )

    def _get_sync(self, item_id: str) -> Ticket:
        issue = self._client.get_issue(item_id, fields=JIRA_FIELDS)
        return map_issue_to_ticket(issue, base_url=self._base_url)

    def _search_sync(self, query: str, limit: int) -> tuple[SearchHit, ...]:
        result = self._client.search_issues_jql(
            jql=build_text_search_jql(query),
            fields=JIRA_FIELDS,
            limit=limit,
        )
        issues = result.get("issues") or ()
        return tuple(
            map_issue_to_search_hit(issue, base_url=self._base_url)
            for issue in issues
        )

    def _search_jql_sync(self, jql: str, limit: int) -> tuple[Ticket, ...]:
        result = self._client.search_issues_jql(
            jql=jql,
            fields=JIRA_FIELDS,
            limit=limit,
        )
        issues = result.get("issues") or ()
        return tuple(
            map_issue_to_ticket(issue, base_url=self._base_url)
            for issue in issues
        )
