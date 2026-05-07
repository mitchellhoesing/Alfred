from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

from mcp_server.adapters.gmail.gmail_message_mapper import (
    map_message_to_canonical,
    map_message_to_search_hit,
)
from mcp_server.core.canonical import Person


_FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


class TestMapMessageFull(unittest.TestCase):
    def setUp(self) -> None:
        self.message = map_message_to_canonical(_load("message_full.json"))

    def test_id_thread_id_and_source(self) -> None:
        self.assertEqual(self.message.id, "msg_abc123")
        self.assertEqual(self.message.thread_id, "thr_zzz")
        self.assertEqual(self.message.source, "gmail")

    def test_subject(self) -> None:
        self.assertEqual(self.message.subject, "Re: Q2 Planning")

    def test_sender_parsed_with_name_and_email(self) -> None:
        self.assertEqual(
            self.message.sender,
            Person(name="Alice Smith", email="alice@example.com"),
        )

    def test_recipients_parsed_in_order(self) -> None:
        self.assertEqual(len(self.message.recipients), 2)
        self.assertEqual(
            self.message.recipients[0],
            Person(name="Mitch", email="mitch@example.com"),
        )
        self.assertEqual(
            self.message.recipients[1],
            Person(name="Bob", email="bob@example.com"),
        )

    def test_sent_at_is_utc_from_internal_date(self) -> None:
        self.assertEqual(
            self.message.sent_at,
            datetime(2026, 5, 5, 13, 0, tzinfo=timezone.utc),
        )

    def test_snippet(self) -> None:
        self.assertEqual(
            self.message.snippet,
            "Hi Mitch, just following up on the Q2 planning doc...",
        )

    def test_is_unread_true_when_unread_label_present(self) -> None:
        self.assertTrue(self.message.is_unread)

    def test_raw_is_immutable(self) -> None:
        self.assertIsInstance(self.message.raw, MappingProxyType)
        with self.assertRaises(TypeError):
            self.message.raw["id"] = "X"  # type: ignore[index]


class TestMapMessageReadStatus(unittest.TestCase):
    def test_no_unread_label_means_is_unread_false(self) -> None:
        message = map_message_to_canonical(_load("message_read.json"))
        self.assertFalse(message.is_unread)

    def test_no_label_ids_key_means_is_unread_false(self) -> None:
        message = map_message_to_canonical(_load("message_no_payload.json"))
        self.assertFalse(message.is_unread)


class TestMapMessageEmailOnlySender(unittest.TestCase):
    def test_email_only_from_yields_person_with_no_name(self) -> None:
        message = map_message_to_canonical(_load("message_read.json"))
        self.assertEqual(
            message.sender,
            Person(name=None, email="noreply@booking.example"),
        )

    def test_single_recipient_yields_one_person(self) -> None:
        message = map_message_to_canonical(_load("message_read.json"))
        self.assertEqual(
            message.recipients,
            (Person(name=None, email="mitch@example.com"),),
        )


class TestMapMessageMissingPayload(unittest.TestCase):
    def setUp(self) -> None:
        self.message = map_message_to_canonical(
            _load("message_no_payload.json")
        )

    def test_no_payload_yields_empty_subject(self) -> None:
        self.assertEqual(self.message.subject, "")

    def test_no_payload_yields_sender_with_none_fields(self) -> None:
        self.assertEqual(self.message.sender, Person(name=None, email=None))

    def test_no_payload_yields_empty_recipients(self) -> None:
        self.assertEqual(self.message.recipients, ())

    def test_missing_snippet_yields_empty_string(self) -> None:
        self.assertEqual(self.message.snippet, "")


class TestMapMessageDecoupling(unittest.TestCase):
    def test_raw_decoupled_from_input_dict(self) -> None:
        raw_dict = _load("message_full.json")
        message = map_message_to_canonical(raw_dict)
        raw_dict["id"] = "MUTATED"
        self.assertEqual(message.raw["id"], "msg_abc123")


class TestMapMessageToSearchHit(unittest.TestCase):
    def test_full_message_search_hit(self) -> None:
        hit = map_message_to_search_hit(_load("message_full.json"))
        self.assertEqual(hit.source, "gmail")
        self.assertEqual(hit.item_id, "msg_abc123")
        self.assertEqual(hit.title, "Re: Q2 Planning")
        self.assertEqual(
            hit.snippet,
            "Hi Mitch, just following up on the Q2 planning doc...",
        )
        self.assertEqual(
            hit.url,
            "https://mail.google.com/mail/u/0/#all/msg_abc123",
        )
        self.assertIsNone(hit.relevance)

    def test_missing_subject_yields_empty_title(self) -> None:
        hit = map_message_to_search_hit(_load("message_no_payload.json"))
        self.assertEqual(hit.title, "")

    def test_missing_snippet_yields_empty_string(self) -> None:
        hit = map_message_to_search_hit(_load("message_no_payload.json"))
        self.assertEqual(hit.snippet, "")


if __name__ == "__main__":
    unittest.main()
