from __future__ import annotations

import unittest
from datetime import datetime
from typing import Sequence

from mcp_server.core.aggregator import CrossSourceAggregator
from mcp_server.core.canonical import SearchHit, SourceItem, Ticket
from mcp_server.core.errors import AdapterError
from mcp_server.core.registry import AdapterRegistry
from mcp_server.core.source_adapter import AdapterCapabilities, SourceAdapter


class _FakeAdapter(SourceAdapter):
    def __init__(
        self,
        name: str,
        *,
        items: Sequence[SourceItem] = (),
        hits: Sequence[SearchHit] = (),
        fail: bool = False,
    ) -> None:
        self._caps = AdapterCapabilities(name, True, True, False)
        self._items = items
        self._hits = hits
        self._fail = fail

    @property
    def capabilities(self) -> AdapterCapabilities:
        return self._caps

    async def list_recent(self, *, since: datetime, limit: int) -> Sequence[SourceItem]:
        if self._fail:
            raise AdapterError(f"{self._caps.source_name} blew up")
        return self._items[:limit]

    async def get(self, item_id: str) -> SourceItem:
        for it in self._items:
            if it.id == item_id:
                return it
        raise AdapterError(f"not found: {item_id}")

    async def search(self, query: str, *, limit: int) -> Sequence[SearchHit]:
        if self._fail:
            raise AdapterError("search blew up")
        return self._hits[:limit]


def _ticket(idx: int) -> Ticket:
    return Ticket(
        id=f"FOO-{idx}",
        source="jira",
        summary=f"bug {idx}",
        status="Open",
        assignee=None,
        reporter=None,
        priority=None,
        updated_at=datetime(2026, 5, 4),
        url=f"https://example.atlassian.net/browse/FOO-{idx}",
        raw={},
    )


class TestCrossSourceAggregator(unittest.IsolatedAsyncioTestCase):
    async def test_search_fans_out_to_all_adapters(self) -> None:
        r = AdapterRegistry()
        r.register(_FakeAdapter("a", hits=(SearchHit("a", "1", "t", "s"),)))
        r.register(_FakeAdapter("b", hits=(SearchHit("b", "2", "t", "s"),)))
        agg = CrossSourceAggregator(r)
        results = await agg.search("anything")
        self.assertEqual({h.source for h in results}, {"a", "b"})

    async def test_search_partial_failure_returns_remaining(self) -> None:
        r = AdapterRegistry()
        r.register(_FakeAdapter("good", hits=(SearchHit("good", "1", "t", "s"),)))
        r.register(_FakeAdapter("bad", fail=True))
        agg = CrossSourceAggregator(r)
        results = await agg.search("anything")
        self.assertEqual([h.source for h in results], ["good"])

    async def test_search_respects_sources_filter(self) -> None:
        r = AdapterRegistry()
        r.register(_FakeAdapter("a", hits=(SearchHit("a", "1", "t", "s"),)))
        r.register(_FakeAdapter("b", hits=(SearchHit("b", "2", "t", "s"),)))
        agg = CrossSourceAggregator(r)
        results = await agg.search("x", sources=["a"])
        self.assertEqual([h.source for h in results], ["a"])

    async def test_list_recent_filters_by_source(self) -> None:
        r = AdapterRegistry()
        r.register(_FakeAdapter("a", items=(_ticket(1),)))
        r.register(_FakeAdapter("b", items=(_ticket(2),)))
        agg = CrossSourceAggregator(r)
        results = await agg.list_recent(since=datetime(2026, 1, 1), sources=["a"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "FOO-1")

    async def test_list_recent_partial_failure_returns_remaining(self) -> None:
        r = AdapterRegistry()
        r.register(_FakeAdapter("good", items=(_ticket(7),)))
        r.register(_FakeAdapter("bad", fail=True))
        agg = CrossSourceAggregator(r)
        results = await agg.list_recent(since=datetime(2026, 1, 1))
        self.assertEqual([it.id for it in results], ["FOO-7"])

    async def test_get_delegates_to_named_adapter(self) -> None:
        r = AdapterRegistry()
        r.register(_FakeAdapter("a", items=(_ticket(7),)))
        agg = CrossSourceAggregator(r)
        item = await agg.get("a", "FOO-7")
        self.assertEqual(item.id, "FOO-7")

    async def test_get_unknown_source_raises(self) -> None:
        r = AdapterRegistry()
        agg = CrossSourceAggregator(r)
        with self.assertRaises(KeyError):
            await agg.get("nope", "x")


if __name__ == "__main__":
    unittest.main()
