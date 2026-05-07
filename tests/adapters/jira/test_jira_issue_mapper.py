from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

from mcp_server.adapters.jira.jira_issue_mapper import (
    map_issue_to_search_hit,
    map_issue_to_ticket,
)
from mcp_server.core.canonical import Person


_FIXTURES = Path(__file__).parent / "fixtures"
_BASE_URL = "https://acme.atlassian.net"


def _load(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


class TestMapIssueToTicket(unittest.TestCase):
    def test_full_fields(self) -> None:
        ticket = map_issue_to_ticket(_load("issue_single.json"), base_url=_BASE_URL)
        self.assertEqual(ticket.id, "ALF-1")
        self.assertEqual(ticket.source, "jira")
        self.assertEqual(
            ticket.summary, "Investigate cross-source aggregation latency"
        )
        self.assertEqual(ticket.status, "In Progress")
        self.assertEqual(
            ticket.assignee,
            Person(name="Mitch Hoesing", email="hoesingmitch02@gmail.com"),
        )
        self.assertEqual(
            ticket.reporter,
            Person(name="Alex Reporter", email="alex@example.com"),
        )
        self.assertEqual(ticket.priority, "High")
        self.assertEqual(
            ticket.updated_at,
            datetime(2026, 5, 4, 13, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(ticket.url, "https://acme.atlassian.net/browse/ALF-1")

    def test_assignee_present_but_no_email(self) -> None:
        ticket = map_issue_to_ticket(
            _load("issue_assignee_no_email.json"), base_url=_BASE_URL
        )
        self.assertIsNotNone(ticket.assignee)
        assert ticket.assignee is not None
        self.assertEqual(ticket.assignee.name, "Privacy Person")
        self.assertIsNone(ticket.assignee.email)

    def test_unassigned_and_no_priority(self) -> None:
        ticket = map_issue_to_ticket(
            _load("issue_unassigned.json"), base_url=_BASE_URL
        )
        self.assertIsNone(ticket.assignee)
        self.assertIsNone(ticket.priority)
        # Reporter is still populated
        self.assertIsNotNone(ticket.reporter)

    def test_raw_is_immutable(self) -> None:
        ticket = map_issue_to_ticket(_load("issue_single.json"), base_url=_BASE_URL)
        self.assertIsInstance(ticket.raw, MappingProxyType)
        with self.assertRaises(TypeError):
            ticket.raw["key"] = "X"  # type: ignore[index]

    def test_raw_decoupled_from_input(self) -> None:
        # Mutating the input dict after mapping must not change ticket.raw.
        issue = _load("issue_single.json")
        ticket = map_issue_to_ticket(issue, base_url=_BASE_URL)
        issue["key"] = "MUTATED"
        self.assertEqual(ticket.raw["key"], "ALF-1")

    def test_url_strips_trailing_slash_on_base_url(self) -> None:
        ticket = map_issue_to_ticket(
            _load("issue_single.json"), base_url="https://acme.atlassian.net/"
        )
        self.assertEqual(ticket.url, "https://acme.atlassian.net/browse/ALF-1")


class TestMapIssueToSearchHit(unittest.TestCase):
    def test_basic_fields(self) -> None:
        hit = map_issue_to_search_hit(
            _load("issue_single.json"), base_url=_BASE_URL
        )
        self.assertEqual(hit.source, "jira")
        self.assertEqual(hit.item_id, "ALF-1")
        self.assertEqual(
            hit.title, "Investigate cross-source aggregation latency"
        )
        self.assertEqual(
            hit.snippet, "Investigate cross-source aggregation latency"
        )
        self.assertEqual(hit.url, "https://acme.atlassian.net/browse/ALF-1")
        self.assertIsNone(hit.relevance)


if __name__ == "__main__":
    unittest.main()
