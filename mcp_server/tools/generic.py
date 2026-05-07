"""Generic MCP tools that fan out across every registered SourceAdapter.

These functions are the dependency-injectable "core" of the generic
tools layer. The server (``mcp_server/server.py``) wires them into
FastMCP via small closures that bind the live :class:`CrossSourceAggregator`
instance — keeping the tool logic itself pure and testable with a fake
aggregator.

Three tools mirror the three :class:`SourceAdapter` ABC methods:

- :func:`alfred_search` → :meth:`CrossSourceAggregator.search`
- :func:`alfred_list_recent` → :meth:`CrossSourceAggregator.list_recent`
- :func:`alfred_get` → :meth:`CrossSourceAggregator.get`

All three return JSON-serializable dicts (or lists of dicts) via
:func:`to_jsonable`, ready to hand to MCP without further conversion.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, Sequence

from mcp_server.core.canonical import SearchHit, SourceItem
from mcp_server.core.canonical_serializer import to_jsonable


class _AggregatorProtocol(Protocol):
    """Structural type for the aggregator dependency.

    Defined here (rather than imported) so the tools layer depends on the
    abstraction (DIP) and tests can inject a minimal fake without
    constructing a real :class:`CrossSourceAggregator`.
    """

    async def search(
        self,
        query: str,
        *,
        sources: Sequence[str] | None = None,
        limit_per_source: int = 10,
    ) -> Sequence[SearchHit]: ...

    async def list_recent(
        self,
        *,
        since: datetime,
        sources: Sequence[str] | None = None,
        limit_per_source: int = 20,
    ) -> Sequence[SourceItem]: ...

    async def get(self, source: str, item_id: str) -> SourceItem: ...


async def alfred_search(
    aggregator: _AggregatorProtocol,
    *,
    query: str,
    sources: list[str] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Fan-out free-text search across all (or specified) sources."""
    hits = await aggregator.search(
        query, sources=sources, limit_per_source=limit
    )
    return [to_jsonable(h) for h in hits]


async def alfred_list_recent(
    aggregator: _AggregatorProtocol,
    *,
    since: str,
    sources: list[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Fan-out "what's new since *since*" across all (or specified) sources.

    ``since`` is an ISO 8601 string; it is parsed via
    :meth:`datetime.fromisoformat`. An invalid value raises
    :class:`ValueError`.
    """
    parsed = datetime.fromisoformat(since)
    items = await aggregator.list_recent(
        since=parsed, sources=sources, limit_per_source=limit
    )
    return [to_jsonable(i) for i in items]


async def alfred_get(
    aggregator: _AggregatorProtocol,
    *,
    source: str,
    item_id: str,
) -> dict[str, Any]:
    """Fetch a single item by source-native id."""
    item = await aggregator.get(source, item_id)
    return to_jsonable(item)
