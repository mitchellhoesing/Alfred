from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from mcp_server.adapters.jira.jira_source_adapter import JiraSourceAdapter
from mcp_server.core.canonical import SearchHit, Ticket
from mcp_server.core.errors import ItemNotFoundError
from mcp_server.core.registry import AdapterRegistry


_FIXTURES = Path(__file__).parent / "fixtures"
_BASE_URL = "https://acme.atlassian.net"


def _load(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


class _FakeJiraCloudHttpClient:
    """Stand-in for JiraCloudHttpClient. Records calls and replays canned
    responses or raises canned exceptions."""

    def __init__(self) -> None:
        self._issue_responses: dict[str, Mapping[str, Any] | Exception] = {}
        self._search_response: Mapping[str, Any] | Exception | None = None
        self.last_search_call: dict[str, Any] | None = None
        self.last_get_call: dict[str, Any] | None = None

    def set_issue(self, key: str, response: Mapping[str, Any] | Exception) -> None:
        self._issue_responses[key] = response

    def set_search(self, response: Mapping[str, Any] | Exception) -> None:
        self._search_response = response

    def get_issue(
        self, issue_key: str, *, fields: Sequence[str]
    ) -> Mapping[str, Any]:
        self.last_get_call = {"issue_key": issue_key, "fields": tuple(fields)}
        resp = self._issue_responses[issue_key]
        if isinstance(resp, Exception):
            raise resp
        return resp

    def search_issues_jql(
        self,
        *,
        jql: str,
        fields: Sequence[str],
        limit: int,
    ) -> Mapping[str, Any]:
        self.last_search_call = {
            "jql": jql,
            "fields": tuple(fields),
            "limit": limit,
        }
        if self._search_response is None:
            raise AssertionError("search response not configured in fake")
        if isinstance(self._search_response, Exception):
            raise self._search_response
        return self._search_response


def _adapter(fake: _FakeJiraCloudHttpClient) -> JiraSourceAdapter:
    return JiraSourceAdapter(fake, base_url=_BASE_URL)  # type: ignore[arg-type]


class TestCapabilities(unittest.TestCase):
    def test_capabilities_values(self) -> None:
        caps = _adapter(_FakeJiraCloudHttpClient()).capabilities
        self.assertEqual(caps.source_name, "jira")
        self.assertTrue(caps.supports_search)
        self.assertTrue(caps.supports_time_range)
        self.assertFalse(caps.supports_threading)


class TestGet(unittest.IsolatedAsyncioTestCase):
    async def test_get_returns_ticket(self) -> None:
        fake = _FakeJiraCloudHttpClient()
        fake.set_issue("ALF-1", _load("issue_single.json"))
        adapter = _adapter(fake)

        ticket = await adapter.get("ALF-1")

        self.assertIsInstance(ticket, Ticket)
        self.assertEqual(ticket.id, "ALF-1")
        self.assertEqual(ticket.url, "https://acme.atlassian.net/browse/ALF-1")
        # Verify it requested only the canonical fields
        assert fake.last_get_call is not None
        self.assertEqual(
            fake.last_get_call["fields"],
            ("summary", "status", "assignee", "reporter", "priority", "updated"),
        )

    async def test_get_propagates_item_not_found(self) -> None:
        fake = _FakeJiraCloudHttpClient()
        fake.set_issue("NOPE-1", ItemNotFoundError("NOPE-1"))
        adapter = _adapter(fake)

        with self.assertRaises(ItemNotFoundError):
            await adapter.get("NOPE-1")


class TestListRecent(unittest.IsolatedAsyncioTestCase):
    async def test_list_recent_uses_recent_jql_clause(self) -> None:
        fake = _FakeJiraCloudHttpClient()
        fake.set_search(_load("search_jql_results.json"))
        adapter = _adapter(fake)

        results = await adapter.list_recent(
            since=datetime(2026, 5, 4, 13, 30, tzinfo=timezone.utc),
            limit=10,
        )

        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(t, Ticket) for t in results))
        self.assertEqual(results[0].id, "ALF-1")
        # Verify the JQL has the time-range clause
        assert fake.last_search_call is not None
        self.assertIn(
            'updated >= "2026/05/04 13:30"', fake.last_search_call["jql"]
        )
        self.assertEqual(fake.last_search_call["limit"], 10)

    async def test_list_recent_empty_results(self) -> None:
        fake = _FakeJiraCloudHttpClient()
        fake.set_search(_load("search_jql_empty.json"))
        adapter = _adapter(fake)

        results = await adapter.list_recent(
            since=datetime(2026, 5, 4, tzinfo=timezone.utc),
            limit=10,
        )
        self.assertEqual(results, ())


class TestSearch(unittest.IsolatedAsyncioTestCase):
    async def test_search_returns_search_hits(self) -> None:
        fake = _FakeJiraCloudHttpClient()
        fake.set_search(_load("search_jql_results.json"))
        adapter = _adapter(fake)

        results = await adapter.search("urgent", limit=5)

        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(h, SearchHit) for h in results))
        self.assertEqual(results[0].source, "jira")
        self.assertEqual(results[0].item_id, "ALF-1")
        # Verify the JQL escapes the query and uses text ~
        assert fake.last_search_call is not None
        self.assertIn('text ~ "urgent"', fake.last_search_call["jql"])

    async def test_search_escapes_user_input(self) -> None:
        fake = _FakeJiraCloudHttpClient()
        fake.set_search(_load("search_jql_empty.json"))
        adapter = _adapter(fake)

        await adapter.search('say "hi"', limit=5)

        assert fake.last_search_call is not None
        self.assertIn('text ~ "say \\"hi\\""', fake.last_search_call["jql"])


class TestSearchJql(unittest.IsolatedAsyncioTestCase):
    async def test_search_jql_returns_tickets(self) -> None:
        fake = _FakeJiraCloudHttpClient()
        fake.set_search(_load("search_jql_results.json"))
        adapter = _adapter(fake)

        results = await adapter.search_jql(
            "assignee = currentUser() AND status != Done", limit=25
        )

        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(t, Ticket) for t in results))
        self.assertEqual(results[1].id, "ALF-3")

    async def test_search_jql_passes_through_unescaped(self) -> None:
        fake = _FakeJiraCloudHttpClient()
        fake.set_search(_load("search_jql_empty.json"))
        adapter = _adapter(fake)

        raw_jql = 'project = "ALF" AND text ~ "with \\"quotes\\""'
        await adapter.search_jql(raw_jql, limit=5)

        assert fake.last_search_call is not None
        # The adapter must NOT modify the JQL string at all
        self.assertEqual(fake.last_search_call["jql"], raw_jql)


class TestRegistryIntegration(unittest.TestCase):
    def test_registers_under_jira_source_name(self) -> None:
        adapter = _adapter(_FakeJiraCloudHttpClient())
        registry = AdapterRegistry()
        registry.register(adapter)
        self.assertIn("jira", registry)
        self.assertIs(registry.get("jira"), adapter)


if __name__ == "__main__":
    unittest.main()
