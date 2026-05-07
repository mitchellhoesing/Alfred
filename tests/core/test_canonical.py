from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime

from mcp_server.core.canonical import (
    Event,
    Message,
    Person,
    SearchHit,
    Ticket,
)


class TestPerson(unittest.TestCase):
    def test_defaults(self) -> None:
        p = Person()
        self.assertIsNone(p.name)
        self.assertIsNone(p.email)

    def test_frozen(self) -> None:
        p = Person(name="Alice", email="a@x.com")
        with self.assertRaises(FrozenInstanceError):
            p.name = "Bob"  # type: ignore[misc]


class TestEvent(unittest.TestCase):
    def test_construction(self) -> None:
        now = datetime(2026, 5, 4, 9, 0)
        evt = Event(
            id="evt1",
            source="google_calendar",
            title="Standup",
            start=now,
            end=now,
            attendees=(Person(name="A"),),
            location=None,
            description=None,
            raw={"id": "evt1"},
        )
        self.assertEqual(evt.title, "Standup")
        self.assertEqual(len(evt.attendees), 1)


class TestMessage(unittest.TestCase):
    def test_construction(self) -> None:
        now = datetime(2026, 5, 4, 9, 0)
        sender = Person(name="A", email="a@x.com")
        msg = Message(
            id="m1",
            source="gmail",
            thread_id="t1",
            subject="Hi",
            sender=sender,
            recipients=(sender,),
            sent_at=now,
            snippet="hello",
            is_unread=True,
            raw={},
        )
        self.assertTrue(msg.is_unread)
        self.assertEqual(msg.thread_id, "t1")


class TestTicket(unittest.TestCase):
    def test_construction(self) -> None:
        now = datetime(2026, 5, 4, 9, 0)
        t = Ticket(
            id="FOO-1",
            source="jira",
            summary="bug",
            status="Open",
            assignee=None,
            reporter=None,
            priority="High",
            updated_at=now,
            url="https://example.atlassian.net/browse/FOO-1",
            raw={},
        )
        self.assertEqual(t.id, "FOO-1")
        self.assertEqual(t.priority, "High")


class TestSearchHit(unittest.TestCase):
    def test_minimal(self) -> None:
        hit = SearchHit(source="jira", item_id="FOO-1", title="t", snippet="s")
        self.assertIsNone(hit.url)
        self.assertIsNone(hit.relevance)

    def test_full(self) -> None:
        hit = SearchHit(
            source="gmail",
            item_id="m1",
            title="t",
            snippet="s",
            url="https://mail.google.com/m1",
            relevance=0.87,
        )
        self.assertEqual(hit.relevance, 0.87)


if __name__ == "__main__":
    unittest.main()
