from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from mcp_server.adapters.google_calendar.google_calendar_source_adapter import (
    GoogleCalendarSourceAdapter,
)
from mcp_server.core.canonical import Event, SearchHit
from mcp_server.core.errors import ItemNotFoundError
from mcp_server.core.registry import AdapterRegistry


_FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


class _FakeGoogleCalendarApiClient:
    """Records calls and replays canned responses or raises canned exceptions."""

    def __init__(self) -> None:
        self.list_response: Mapping[str, Any] | Exception | None = None
        self.get_response: Mapping[str, Any] | Exception | None = None
        self.last_list_kwargs: dict[str, Any] | None = None
        self.last_get_kwargs: dict[str, Any] | None = None

    def list_events(self, **kwargs: Any) -> Mapping[str, Any]:
        self.last_list_kwargs = dict(kwargs)
        if self.list_response is None:
            raise AssertionError("list_response not configured in fake")
        if isinstance(self.list_response, Exception):
            raise self.list_response
        return self.list_response

    def get_event(self, event_id: str, **kwargs: Any) -> Mapping[str, Any]:
        self.last_get_kwargs = {"event_id": event_id, **kwargs}
        if self.get_response is None:
            raise AssertionError("get_response not configured in fake")
        if isinstance(self.get_response, Exception):
            raise self.get_response
        return self.get_response


def _adapter(fake: _FakeGoogleCalendarApiClient) -> GoogleCalendarSourceAdapter:
    return GoogleCalendarSourceAdapter(fake)  # type: ignore[arg-type]


class TestCapabilities(unittest.TestCase):
    def test_capabilities_values(self) -> None:
        caps = _adapter(_FakeGoogleCalendarApiClient()).capabilities
        self.assertEqual(caps.source_name, "google_calendar")
        self.assertTrue(caps.supports_search)
        self.assertTrue(caps.supports_time_range)
        self.assertFalse(caps.supports_threading)


class TestGet(unittest.IsolatedAsyncioTestCase):
    async def test_get_returns_event(self) -> None:
        fake = _FakeGoogleCalendarApiClient()
        fake.get_response = _load("event_full.json")

        event = await _adapter(fake).get("evt_abc123")

        self.assertIsInstance(event, Event)
        self.assertEqual(event.id, "evt_abc123")
        assert fake.last_get_kwargs is not None
        self.assertEqual(fake.last_get_kwargs["event_id"], "evt_abc123")

    async def test_get_propagates_item_not_found(self) -> None:
        fake = _FakeGoogleCalendarApiClient()
        fake.get_response = ItemNotFoundError("missing-evt")
        with self.assertRaises(ItemNotFoundError):
            await _adapter(fake).get("missing-evt")


class TestListRecent(unittest.IsolatedAsyncioTestCase):
    async def test_list_recent_uses_updated_min(self) -> None:
        fake = _FakeGoogleCalendarApiClient()
        fake.list_response = _load("events_list.json")

        since = datetime(2026, 5, 5, 0, 0, tzinfo=timezone.utc)
        events = await _adapter(fake).list_recent(since=since, limit=10)

        self.assertEqual(len(events), 2)
        self.assertTrue(all(isinstance(e, Event) for e in events))
        self.assertEqual(events[0].id, "evt_abc123")

        kwargs = fake.last_list_kwargs
        assert kwargs is not None
        self.assertEqual(kwargs["updated_min"], since)
        self.assertEqual(kwargs["max_results"], 10)
        # Must not be passing q (this is list_recent, not search)
        self.assertNotIn("q", kwargs)

    async def test_list_recent_empty_results(self) -> None:
        fake = _FakeGoogleCalendarApiClient()
        fake.list_response = _load("events_list_empty.json")

        events = await _adapter(fake).list_recent(
            since=datetime(2026, 5, 5, tzinfo=timezone.utc), limit=10
        )
        self.assertEqual(events, ())


class TestSearch(unittest.IsolatedAsyncioTestCase):
    async def test_search_returns_search_hits(self) -> None:
        fake = _FakeGoogleCalendarApiClient()
        fake.list_response = _load("events_list.json")

        hits = await _adapter(fake).search("standup", limit=5)

        self.assertEqual(len(hits), 2)
        self.assertTrue(all(isinstance(h, SearchHit) for h in hits))
        self.assertEqual(hits[0].source, "google_calendar")
        self.assertEqual(hits[0].item_id, "evt_abc123")

        kwargs = fake.last_list_kwargs
        assert kwargs is not None
        self.assertEqual(kwargs["q"], "standup")
        self.assertEqual(kwargs["max_results"], 5)

    async def test_search_empty_results(self) -> None:
        fake = _FakeGoogleCalendarApiClient()
        fake.list_response = _load("events_list_empty.json")

        hits = await _adapter(fake).search("nope", limit=5)
        self.assertEqual(hits, ())


class TestListEventsInRange(unittest.IsolatedAsyncioTestCase):
    async def test_passes_time_min_max_and_limit_to_client(self) -> None:
        fake = _FakeGoogleCalendarApiClient()
        fake.list_response = {"items": []}

        time_min = datetime(2026, 5, 5, 0, 0, tzinfo=timezone.utc)
        time_max = datetime(2026, 5, 6, 0, 0, tzinfo=timezone.utc)
        await _adapter(fake).list_events_in_range(
            time_min=time_min, time_max=time_max, limit=25
        )

        kwargs = fake.last_list_kwargs
        assert kwargs is not None
        self.assertEqual(kwargs["time_min"], time_min)
        self.assertEqual(kwargs["time_max"], time_max)
        self.assertEqual(kwargs["max_results"], 25)
        # Must NOT pass updated_min — this is a start-time query, not a
        # recently-modified query.
        self.assertNotIn("updated_min", kwargs)

    async def test_returns_canonical_events_in_response_order(self) -> None:
        fake = _FakeGoogleCalendarApiClient()
        fake.list_response = _load("events_list.json")

        events = await _adapter(fake).list_events_in_range(
            time_min=datetime(2026, 5, 5, tzinfo=timezone.utc),
            time_max=datetime(2026, 5, 6, tzinfo=timezone.utc),
        )
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].id, "evt_abc123")

    async def test_default_limit_is_50(self) -> None:
        fake = _FakeGoogleCalendarApiClient()
        fake.list_response = {"items": []}

        await _adapter(fake).list_events_in_range(
            time_min=datetime(2026, 5, 5, tzinfo=timezone.utc),
            time_max=datetime(2026, 5, 6, tzinfo=timezone.utc),
        )
        kwargs = fake.last_list_kwargs
        assert kwargs is not None
        self.assertEqual(kwargs["max_results"], 50)


class TestFindFreeSlot(unittest.IsolatedAsyncioTestCase):
    """Wiring tests only; the gap-finding algorithm is tested in
    test_calendar_free_slot_finder.py. Here we just confirm the adapter
    passes the right window to the client and forwards the algorithm's
    result through."""

    @staticmethod
    def _event(start_iso: str, end_iso: str, eid: str = "x") -> dict[str, Any]:
        return {
            "id": eid,
            "start": {"dateTime": start_iso},
            "end": {"dateTime": end_iso},
        }

    async def test_passes_now_and_window_end_to_client(self) -> None:
        fake = _FakeGoogleCalendarApiClient()
        fake.list_response = {"items": []}

        now = datetime(2026, 5, 5, 9, 0, tzinfo=timezone.utc)
        await _adapter(fake).find_free_slot(
            duration_minutes=30, within_days=1, now=now
        )

        kwargs = fake.last_list_kwargs
        assert kwargs is not None
        self.assertEqual(kwargs["time_min"], now)
        self.assertEqual(
            kwargs["time_max"],
            datetime(2026, 5, 6, 9, 0, tzinfo=timezone.utc),
        )

    async def test_returns_window_start_when_no_events(self) -> None:
        fake = _FakeGoogleCalendarApiClient()
        fake.list_response = {"items": []}
        now = datetime(2026, 5, 5, 9, 0, tzinfo=timezone.utc)

        slot = await _adapter(fake).find_free_slot(
            duration_minutes=60, within_days=1, now=now
        )
        self.assertEqual(slot, now)

    async def test_returns_pre_event_slot_when_long_enough(self) -> None:
        fake = _FakeGoogleCalendarApiClient()
        fake.list_response = {
            "items": [
                self._event(
                    "2026-05-05T10:00:00+00:00", "2026-05-05T11:00:00+00:00"
                ),
            ]
        }
        now = datetime(2026, 5, 5, 9, 0, tzinfo=timezone.utc)

        slot = await _adapter(fake).find_free_slot(
            duration_minutes=30, within_days=1, now=now
        )
        self.assertEqual(slot, now)  # 9:00–10:00 = 60min slot, fits 30min

    async def test_returns_inter_event_slot_when_pre_event_too_short(
        self,
    ) -> None:
        fake = _FakeGoogleCalendarApiClient()
        fake.list_response = {
            "items": [
                self._event(
                    "2026-05-05T09:00:00+00:00", "2026-05-05T10:00:00+00:00"
                ),
                self._event(
                    "2026-05-05T11:00:00+00:00", "2026-05-05T12:00:00+00:00"
                ),
            ]
        }
        now = datetime(2026, 5, 5, 9, 0, tzinfo=timezone.utc)

        slot = await _adapter(fake).find_free_slot(
            duration_minutes=45, within_days=1, now=now
        )
        # Pre = 0min, gap 10-11 = 60min → returns 10:00
        self.assertEqual(
            slot, datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc)
        )

    async def test_returns_none_when_window_is_fully_busy(self) -> None:
        fake = _FakeGoogleCalendarApiClient()
        # Single event spanning the whole 1-day window.
        fake.list_response = {
            "items": [
                self._event(
                    "2026-05-05T09:00:00+00:00", "2026-05-06T09:00:00+00:00"
                ),
            ]
        }
        now = datetime(2026, 5, 5, 9, 0, tzinfo=timezone.utc)

        slot = await _adapter(fake).find_free_slot(
            duration_minutes=30, within_days=1, now=now
        )
        self.assertIsNone(slot)


class TestRegistryIntegration(unittest.TestCase):
    def test_registers_under_google_calendar_source_name(self) -> None:
        adapter = _adapter(_FakeGoogleCalendarApiClient())
        registry = AdapterRegistry()
        registry.register(adapter)
        self.assertIn("google_calendar", registry)
        self.assertIs(registry.get("google_calendar"), adapter)


if __name__ == "__main__":
    unittest.main()
