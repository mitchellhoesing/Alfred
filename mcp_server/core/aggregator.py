"""Cross-source query fan-out.

Skills and tools that span multiple data sources go through this aggregator
rather than driving adapters individually. Per-adapter failures are caught
and logged so a single bad source does not break a fan-out call.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Sequence

from mcp_server.core.canonical import SearchHit, SourceItem
from mcp_server.core.errors import AdapterError
from mcp_server.core.registry import AdapterRegistry
from mcp_server.core.source_adapter import SourceAdapter


_log = logging.getLogger(__name__)


class CrossSourceAggregator:
    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry

    async def search(
        self,
        query: str,
        *,
        sources: Sequence[str] | None = None,
        limit_per_source: int = 10,
    ) -> tuple[SearchHit, ...]:
        adapters = self._resolve(sources)
        results = await asyncio.gather(
            *(self._safe_search(a, query, limit_per_source) for a in adapters)
        )
        merged: list[SearchHit] = []
        for r in results:
            merged.extend(r)
        return tuple(merged)

    async def list_recent(
        self,
        *,
        since: datetime,
        sources: Sequence[str] | None = None,
        limit_per_source: int = 20,
    ) -> tuple[SourceItem, ...]:
        adapters = self._resolve(sources)
        results = await asyncio.gather(
            *(self._safe_list_recent(a, since, limit_per_source) for a in adapters)
        )
        merged: list[SourceItem] = []
        for r in results:
            merged.extend(r)
        return tuple(merged)

    async def get(self, source: str, item_id: str) -> SourceItem:
        return await self._registry.get(source).get(item_id)

    def _resolve(self, sources: Sequence[str] | None) -> tuple[SourceAdapter, ...]:
        if sources is None:
            return tuple(self._registry.all())
        return tuple(self._registry.get(s) for s in sources)

    @staticmethod
    async def _safe_search(
        adapter: SourceAdapter, query: str, limit: int
    ) -> Sequence[SearchHit]:
        try:
            return await adapter.search(query, limit=limit)
        except AdapterError as exc:
            _log.warning(
                "search failed for source=%s: %s",
                adapter.capabilities.source_name,
                exc,
            )
            return ()

    @staticmethod
    async def _safe_list_recent(
        adapter: SourceAdapter, since: datetime, limit: int
    ) -> Sequence[SourceItem]:
        try:
            return await adapter.list_recent(since=since, limit=limit)
        except AdapterError as exc:
            _log.warning(
                "list_recent failed for source=%s: %s",
                adapter.capabilities.source_name,
                exc,
            )
            return ()
