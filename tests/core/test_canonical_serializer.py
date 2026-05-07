from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import MappingProxyType

from mcp_server.core.canonical import (
    Event,
    Message,
    Person,
    SearchHit,
    Ticket,
)
from mcp_server.core.canonical_serializer import to_jsonable


_UTC = timezone.utc


def _person(name: str, email: str) -> Person:
    return Person(name=name, email=email)


class TestEvent(unittest.TestCase):
    def setUp(self) -> None:
        self.event = Event(
            id="evt_1",
            source="google_calendar",
            title="Standup",
            start=datetime(2026, 5, 5, 9, 0, tzinfo=_UTC),
            end=datetime(2026, 5, 5, 9, 30, tzinfo=_UTC),
            attendees=(
                _person("Alice", "alice@example.com"),
                _person("Bob", "bob@example.com"),
            ),
            location="Zoom",
            description="Daily sync",
            raw=MappingProxyType({"id": "evt_1", "extra": "field"}),
        )
        self.payload = to_jsonable(self.event)

    def test_top_level_scalars(self) -> None:
        self.assertEqual(self.payload["id"], "evt_1")
        self.assertEqual(self.payload["source"], "google_calendar")
        self.assertEqual(self.payload["title"], "Standup")
        self.assertEqual(self.payload["location"], "Zoom")
        self.assertEqual(self.payload["description"], "Daily sync")

    def test_aware_datetimes_become_iso_strings_with_offset(self) -> None:
        self.assertEqual(self.payload["start"], "2026-05-05T09:00:00+00:00")
        self.assertEqual(self.payload["end"], "2026-05-05T09:30:00+00:00")

    def test_attendees_become_list_of_dicts_in_order(self) -> None:
        self.assertEqual(
            self.payload["attendees"],
            [
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob", "email": "bob@example.com"},
            ],
        )

    def test_raw_becomes_plain_dict(self) -> None:
        self.assertEqual(
            self.payload["raw"], {"id": "evt_1", "extra": "field"}
        )
        self.assertIsInstance(self.payload["raw"], dict)


class TestEventNaiveDatetime(unittest.TestCase):
    def test_naive_datetime_serializes_without_offset(self) -> None:
        # All-day events surface as naive datetimes per the calendar mapper.
        event = Event(
            id="evt_allday",
            source="google_calendar",
            title="Holiday",
            start=datetime(2026, 7, 4, 0, 0),
            end=datetime(2026, 7, 5, 0, 0),
            attendees=(),
            location=None,
            description=None,
            raw=MappingProxyType({}),
        )
        payload = to_jsonable(event)
        self.assertEqual(payload["start"], "2026-07-04T00:00:00")
        self.assertEqual(payload["end"], "2026-07-05T00:00:00")
        self.assertNotIn("+", payload["start"])


class TestMessage(unittest.TestCase):
    def test_message_serialization(self) -> None:
        msg = Message(
            id="msg_1",
            source="gmail",
            thread_id="thr_1",
            subject="Re: Q2",
            sender=_person("Alice", "alice@example.com"),
            recipients=(_person("Mitch", "mitch@example.com"),),
            sent_at=datetime(2026, 5, 5, 13, 0, tzinfo=_UTC),
            snippet="Following up...",
            is_unread=True,
            raw=MappingProxyType({"labelIds": ["INBOX", "UNREAD"]}),
        )
        payload = to_jsonable(msg)
        self.assertEqual(payload["id"], "msg_1")
        self.assertEqual(payload["thread_id"], "thr_1")
        self.assertEqual(
            payload["sender"], {"name": "Alice", "email": "alice@example.com"}
        )
        self.assertEqual(
            payload["recipients"],
            [{"name": "Mitch", "email": "mitch@example.com"}],
        )
        self.assertEqual(payload["sent_at"], "2026-05-05T13:00:00+00:00")
        self.assertTrue(payload["is_unread"])


class TestTicket(unittest.TestCase):
    def test_ticket_with_none_assignee(self) -> None:
        ticket = Ticket(
            id="ALF-1",
            source="jira",
            summary="Implement adapter",
            status="In Progress",
            assignee=None,
            reporter=_person("Mitch", "mitch@example.com"),
            priority="High",
            updated_at=datetime(
                2026, 5, 5, 10, 0,
                tzinfo=timezone(timedelta(hours=-4)),
            ),
            url="https://example.atlassian.net/browse/ALF-1",
            raw=MappingProxyType({}),
        )
        payload = to_jsonable(ticket)
        self.assertEqual(payload["id"], "ALF-1")
        self.assertIsNone(payload["assignee"])
        self.assertEqual(
            payload["reporter"],
            {"name": "Mitch", "email": "mitch@example.com"},
        )
        self.assertEqual(
            payload["updated_at"], "2026-05-05T10:00:00-04:00"
        )


class TestSearchHit(unittest.TestCase):
    def test_search_hit_serialization(self) -> None:
        hit = SearchHit(
            source="gmail",
            item_id="msg_1",
            title="Re: Q2",
            snippet="...",
            url="https://mail.google.com/...",
            relevance=0.87,
        )
        payload = to_jsonable(hit)
        self.assertEqual(
            payload,
            {
                "source": "gmail",
                "item_id": "msg_1",
                "title": "Re: Q2",
                "snippet": "...",
                "url": "https://mail.google.com/...",
                "relevance": 0.87,
            },
        )


class TestRoundTripsThroughJsonStdlib(unittest.TestCase):
    def test_event_payload_is_json_dumps_safe(self) -> None:
        import json

        event = Event(
            id="evt_1",
            source="google_calendar",
            title="x",
            start=datetime(2026, 5, 5, tzinfo=_UTC),
            end=datetime(2026, 5, 5, 1, tzinfo=_UTC),
            attendees=(_person("a", "a@x"),),
            location=None,
            description=None,
            raw=MappingProxyType({"k": 1}),
        )
        # Must not raise.
        json.dumps(to_jsonable(event))


if __name__ == "__main__":
    unittest.main()
