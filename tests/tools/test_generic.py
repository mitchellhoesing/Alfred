from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Sequence

from mcp_server.core.canonical import (
    Event,
    Person,
    SearchHit,
    SourceItem,
)
from mcp_server.tools.generic import (
    alfred_get,
    alfred_list_recent,
    alfred_search,
)


_UTC = timezone.utc


def _event(eid: str = "evt_1") -> Event:
    return Event(
        id=eid,
        source="google_calendar",
        title="Standup",
        start=datetime(2026, 5, 5, 9, 0, tzinfo=_UTC),
        end=datetime(2026, 5, 5, 9, 30, tzinfo=_UTC),
        attendees=(),
        location=None,
        description=None,
        raw=MappingProxyType({}),
    )


def _hit(item_id: str = "h1", source: str = "gmail") -> SearchHit:
    return SearchHit(
        source=source,
        item_id=item_id,
        title="t",
        snippet="s",
        url=None,
        relevance=None,
    )


class _FakeAggregator:
    def __init__(self) -> None:
        self.search_response: tuple[SearchHit, ...] = ()
        self.list_recent_response: tuple[SourceItem, ...] = ()
        self.get_response: SourceItem | Exception | None = None
        self.last_search_kwargs: dict[str, Any] | None = None
        self.last_list_recent_kwargs: dict[str, Any] | None = None
        self.last_get_args: tuple[str, str] | None = None

    async def search(
        self,
        query: str,
        *,
        sources: Sequence[str] | None = None,
        limit_per_source: int = 10,
    ) -> tuple[SearchHit, ...]:
        self.last_search_kwargs = {
            "query": query,
            "sources": sources,
            "limit_per_source": limit_per_source,
        }
        return self.search_response

    async def list_recent(
        self,
        *,
        since: datetime,
        sources: Sequence[str] | None = None,
        limit_per_source: int = 20,
    ) -> tuple[SourceItem, ...]:
        self.last_list_recent_kwargs = {
            "since": since,
            "sources": sources,
            "limit_per_source": limit_per_source,
        }
        return self.list_recent_response

    async def get(self, source: str, item_id: str) -> SourceItem:
        self.last_get_args = (source, item_id)
        if isinstance(self.get_response, Exception):
            raise self.get_response
        if self.get_response is None:
            raise AssertionError("get_response not configured")
        return self.get_response


class TestAlfredSearch(unittest.IsolatedAsyncioTestCase):
    async def test_returns_list_of_search_hit_dicts(self) -> None:
        agg = _FakeAggregator()
        agg.search_response = (_hit("h1"), _hit("h2", source="jira"))

        result = await alfred_search(agg, query="standup", limit=5)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["item_id"], "h1")
        self.assertEqual(result[1]["item_id"], "h2")
        self.assertEqual(result[1]["source"], "jira")

    async def test_passes_query_sources_and_limit_through(self) -> None:
        agg = _FakeAggregator()
        await alfred_search(
            agg, query="standup", sources=["jira"], limit=7
        )
        self.assertEqual(
            agg.last_search_kwargs,
            {"query": "standup", "sources": ["jira"], "limit_per_source": 7},
        )

    async def test_default_sources_is_none_meaning_all(self) -> None:
        agg = _FakeAggregator()
        await alfred_search(agg, query="x")
        assert agg.last_search_kwargs is not None
        self.assertIsNone(agg.last_search_kwargs["sources"])

    async def test_default_limit_is_10(self) -> None:
        agg = _FakeAggregator()
        await alfred_search(agg, query="x")
        assert agg.last_search_kwargs is not None
        self.assertEqual(agg.last_search_kwargs["limit_per_source"], 10)


class TestAlfredListRecent(unittest.IsolatedAsyncioTestCase):
    async def test_parses_iso_since_into_aware_datetime(self) -> None:
        agg = _FakeAggregator()
        await alfred_list_recent(agg, since="2026-05-05T09:00:00+00:00")
        assert agg.last_list_recent_kwargs is not None
        self.assertEqual(
            agg.last_list_recent_kwargs["since"],
            datetime(2026, 5, 5, 9, 0, tzinfo=_UTC),
        )

    async def test_returns_list_of_source_item_dicts(self) -> None:
        agg = _FakeAggregator()
        agg.list_recent_response = (_event("a"), _event("b"))

        result = await alfred_list_recent(
            agg, since="2026-05-05T00:00:00+00:00"
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "a")
        self.assertEqual(result[1]["id"], "b")

    async def test_passes_sources_and_limit_through(self) -> None:
        agg = _FakeAggregator()
        await alfred_list_recent(
            agg,
            since="2026-05-05T00:00:00+00:00",
            sources=["gmail", "jira"],
            limit=50,
        )
        assert agg.last_list_recent_kwargs is not None
        self.assertEqual(
            agg.last_list_recent_kwargs["sources"], ["gmail", "jira"]
        )
        self.assertEqual(
            agg.last_list_recent_kwargs["limit_per_source"], 50
        )

    async def test_default_limit_is_20(self) -> None:
        agg = _FakeAggregator()
        await alfred_list_recent(agg, since="2026-05-05T00:00:00+00:00")
        assert agg.last_list_recent_kwargs is not None
        self.assertEqual(
            agg.last_list_recent_kwargs["limit_per_source"], 20
        )

    async def test_invalid_since_raises_value_error(self) -> None:
        agg = _FakeAggregator()
        with self.assertRaises(ValueError):
            await alfred_list_recent(agg, since="not-a-date")


class TestAlfredGet(unittest.IsolatedAsyncioTestCase):
    async def test_returns_serialized_source_item(self) -> None:
        agg = _FakeAggregator()
        agg.get_response = _event("evt_42")

        result = await alfred_get(agg, source="google_calendar", item_id="evt_42")

        self.assertEqual(result["id"], "evt_42")
        self.assertEqual(result["source"], "google_calendar")
        self.assertEqual(agg.last_get_args, ("google_calendar", "evt_42"))


if __name__ == "__main__":
    unittest.main()
