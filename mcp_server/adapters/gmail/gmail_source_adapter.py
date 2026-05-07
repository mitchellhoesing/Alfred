"""Concrete :class:`SourceAdapter` for Gmail.

Bridges the async :class:`SourceAdapter` ABC to the sync
:class:`GmailApiClient` via :func:`asyncio.to_thread`. Each ABC method
has a private sync counterpart so the mapping logic is testable without
spinning up an event loop.

Gmail's ``users.messages.list`` returns thin id objects (``id`` +
``threadId`` only). To populate a :class:`Message` the adapter follows
up with one ``users.messages.get`` per result. The API cost is
``1 + N`` calls per ``list_recent`` / ``search``; for v1 limits (≤25)
this is acceptable. Batching can be added later via
``BatchHttpRequest`` without changing the public surface.

The Gmail-specific :meth:`get_thread` is exposed via the
``gmail_get_thread`` MCP tool (see :mod:`mcp_server.tools.specific`); it
lives on the concrete adapter rather than the ABC so threading does not
pollute non-threaded sources like Calendar or Jira.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Sequence

from mcp_server.adapters.gmail.gmail_api_client import GmailApiClient
from mcp_server.adapters.gmail.gmail_message_mapper import (
    map_message_to_canonical,
    map_message_to_search_hit,
)
from mcp_server.core.canonical import Message, SearchHit
from mcp_server.core.source_adapter import AdapterCapabilities, SourceAdapter


_CAPABILITIES = AdapterCapabilities(
    source_name="gmail",
    supports_search=True,
    supports_time_range=True,
    supports_threading=True,
)


class GmailSourceAdapter(SourceAdapter):
    """Adapter wiring Gmail into Alfred's :class:`SourceAdapter` ABC."""

    def __init__(self, client: GmailApiClient) -> None:
        self._client = client

    @property
    def capabilities(self) -> AdapterCapabilities:
        return _CAPABILITIES

    async def list_recent(
        self, *, since: datetime, limit: int
    ) -> Sequence[Message]:
        return await asyncio.to_thread(self._list_recent_sync, since, limit)

    async def get(self, item_id: str) -> Message:
        return await asyncio.to_thread(self._get_sync, item_id)

    async def search(
        self, query: str, *, limit: int
    ) -> Sequence[SearchHit]:
        return await asyncio.to_thread(self._search_sync, query, limit)

    async def get_thread(self, thread_id: str) -> Sequence[Message]:
        """Return every message in *thread_id*, oldest first.

        Source-specific (not on the :class:`SourceAdapter` ABC). Exposed
        via the ``gmail_get_thread`` MCP tool. Raises
        :class:`mcp_server.core.errors.ItemNotFoundError` for an unknown
        thread id.
        """
        return await asyncio.to_thread(self._get_thread_sync, thread_id)

    def _list_recent_sync(
        self, since: datetime, limit: int
    ) -> tuple[Message, ...]:
        listing = self._client.list_messages(
            q=f"after:{since.strftime('%Y/%m/%d')}", max_results=limit
        )
        ids = listing.get("messages") or ()
        return tuple(
            map_message_to_canonical(self._client.get_message(item["id"]))
            for item in ids
        )

    def _get_sync(self, item_id: str) -> Message:
        return map_message_to_canonical(self._client.get_message(item_id))

    def _search_sync(self, query: str, limit: int) -> tuple[SearchHit, ...]:
        listing = self._client.list_messages(q=query, max_results=limit)
        ids = listing.get("messages") or ()
        return tuple(
            map_message_to_search_hit(self._client.get_message(item["id"]))
            for item in ids
        )

    def _get_thread_sync(self, thread_id: str) -> tuple[Message, ...]:
        body = self._client.get_thread(thread_id)
        msgs = body.get("messages") or ()
        return tuple(map_message_to_canonical(m) for m in msgs)
