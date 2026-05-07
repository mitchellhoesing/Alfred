from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

from mcp_server.adapters.google_calendar.calendar_event_mapper import (
    map_event_to_canonical,
    map_event_to_search_hit,
)
from mcp_server.core.canonical import Person


_FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


class TestMapEventToCanonicalFullEvent(unittest.TestCase):
    def setUp(self) -> None:
        self.event = map_event_to_canonical(_load("event_full.json"))

    def test_id_and_source(self) -> None:
        self.assertEqual(self.event.id, "evt_abc123")
        self.assertEqual(self.event.source, "google_calendar")

    def test_title(self) -> None:
        self.assertEqual(self.event.title, "Q2 Planning Sync")

    def test_start_and_end_are_aware_utc_normalized(self) -> None:
        # 09:00-04:00 == 13:00 UTC
        eastern = timezone(timedelta(hours=-4))
        self.assertEqual(
            self.event.start, datetime(2026, 5, 5, 9, 0, tzinfo=eastern)
        )
        self.assertEqual(
            self.event.end, datetime(2026, 5, 5, 10, 0, tzinfo=eastern)
        )
        # Sanity-check timezone awareness
        self.assertIsNotNone(self.event.start.tzinfo)

    def test_attendees_mapped_in_order(self) -> None:
        self.assertEqual(len(self.event.attendees), 2)
        self.assertEqual(
            self.event.attendees[0],
            Person(name="Alice", email="alice@example.com"),
        )
        self.assertEqual(
            self.event.attendees[1],
            Person(name="Bob Coworker", email="bob@example.com"),
        )

    def test_location_and_description(self) -> None:
        self.assertEqual(self.event.location, "Zoom")
        self.assertEqual(
            self.event.description,
            "Review Q2 OKRs and scope for Alfred milestones.",
        )

    def test_raw_is_immutable(self) -> None:
        self.assertIsInstance(self.event.raw, MappingProxyType)
        with self.assertRaises(TypeError):
            self.event.raw["id"] = "X"  # type: ignore[index]


class TestMapEventToCanonicalAllDay(unittest.TestCase):
    def test_all_day_start_and_end_are_midnight_naive(self) -> None:
        event = map_event_to_canonical(_load("event_all_day.json"))
        self.assertEqual(event.start, datetime(2026, 6, 15, 0, 0))
        self.assertEqual(event.end, datetime(2026, 6, 17, 0, 0))
        self.assertIsNone(event.start.tzinfo)
        self.assertIsNone(event.end.tzinfo)

    def test_all_day_event_with_no_attendees_returns_empty_tuple(self) -> None:
        event = map_event_to_canonical(_load("event_all_day.json"))
        self.assertEqual(event.attendees, ())


class TestMapEventToCanonicalMissingOptionalFields(unittest.TestCase):
    def test_missing_summary_yields_empty_title(self) -> None:
        event = map_event_to_canonical(_load("event_no_optional_fields.json"))
        self.assertEqual(event.title, "")

    def test_missing_location_is_none(self) -> None:
        event = map_event_to_canonical(_load("event_no_optional_fields.json"))
        self.assertIsNone(event.location)

    def test_missing_description_is_none(self) -> None:
        event = map_event_to_canonical(_load("event_no_optional_fields.json"))
        self.assertIsNone(event.description)

    def test_missing_attendees_is_empty_tuple(self) -> None:
        event = map_event_to_canonical(_load("event_no_optional_fields.json"))
        self.assertEqual(event.attendees, ())


class TestMapEventDecoupling(unittest.TestCase):
    def test_raw_decoupled_from_input_dict(self) -> None:
        raw_dict = _load("event_full.json")
        event = map_event_to_canonical(raw_dict)
        raw_dict["id"] = "MUTATED"
        self.assertEqual(event.raw["id"], "evt_abc123")


class TestMapEventToSearchHit(unittest.TestCase):
    def test_full_event_uses_description_as_snippet(self) -> None:
        hit = map_event_to_search_hit(_load("event_full.json"))
        self.assertEqual(hit.source, "google_calendar")
        self.assertEqual(hit.item_id, "evt_abc123")
        self.assertEqual(hit.title, "Q2 Planning Sync")
        self.assertEqual(
            hit.snippet, "Review Q2 OKRs and scope for Alfred milestones."
        )
        self.assertEqual(
            hit.url,
            "https://www.google.com/calendar/event?eid=ZXZ0X2FiYzEyMw",
        )
        self.assertIsNone(hit.relevance)

    def test_no_description_falls_back_to_title(self) -> None:
        # event_no_optional_fields.json has no summary AND no description.
        hit = map_event_to_search_hit(
            _load("event_no_optional_fields.json")
        )
        self.assertEqual(hit.title, "")
        self.assertEqual(hit.snippet, "")  # empty title → empty snippet

    def test_summary_is_used_when_no_description_present(self) -> None:
        hit = map_event_to_search_hit(_load("event_all_day.json"))
        self.assertEqual(hit.title, "Company Offsite")
        # All-day fixture has summary but no description
        self.assertEqual(hit.snippet, "Company Offsite")


if __name__ == "__main__":
    unittest.main()
