from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Sequence
from unittest.mock import patch

from mcp.server.fastmcp import FastMCP

from mcp_server.adapters.gmail.gmail_source_adapter import GmailSourceAdapter
from mcp_server.adapters.google_calendar.google_calendar_source_adapter import (
    GoogleCalendarSourceAdapter,
)
from mcp_server.adapters.jira.jira_source_adapter import JiraSourceAdapter
from mcp_server.core.canonical import (
    Event,
    Message,
    Person,
    Ticket,
)
from mcp_server.core.errors import ConfigurationError
from mcp_server.core.registry import AdapterRegistry
from mcp_server.core.source_adapter import AdapterCapabilities
from mcp_server.server import build_registry, register_tools


_UTC = timezone.utc


# ---------------------------------------------------------------------------
# build_registry
# ---------------------------------------------------------------------------


def _fake_jira() -> JiraSourceAdapter:
    """A real JiraSourceAdapter wrapped around a None client.

    We only need an instance the registry will accept; it never gets
    called in build_registry tests.
    """
    return JiraSourceAdapter.__new__(JiraSourceAdapter)


def _fake_calendar() -> GoogleCalendarSourceAdapter:
    return GoogleCalendarSourceAdapter.__new__(GoogleCalendarSourceAdapter)


def _fake_gmail() -> GmailSourceAdapter:
    return GmailSourceAdapter.__new__(GmailSourceAdapter)


class TestBuildRegistry(unittest.TestCase):
    def test_all_adapters_register_when_each_factory_succeeds(self) -> None:
        with patch(
            "mcp_server.server.build_jira_adapter", return_value=_fake_jira()
        ), patch(
            "mcp_server.server.build_google_calendar_adapter",
            return_value=_fake_calendar(),
        ), patch(
            "mcp_server.server.build_gmail_adapter", return_value=_fake_gmail()
        ):
            registry = build_registry({"any": "thing"})
        self.assertEqual(
            set(registry.names()), {"jira", "google_calendar", "gmail"}
        )

    def test_skips_adapter_whose_factory_raises_configuration_error(
        self,
    ) -> None:
        with patch(
            "mcp_server.server.build_jira_adapter",
            side_effect=ConfigurationError("missing JIRA_BASE_URL"),
        ), patch(
            "mcp_server.server.build_google_calendar_adapter",
            return_value=_fake_calendar(),
        ), patch(
            "mcp_server.server.build_gmail_adapter", return_value=_fake_gmail()
        ):
            registry = build_registry({})
        self.assertNotIn("jira", registry)
        self.assertIn("google_calendar", registry)
        self.assertIn("gmail", registry)

    def test_raises_when_no_adapter_can_be_built(self) -> None:
        with patch(
            "mcp_server.server.build_jira_adapter",
            side_effect=ConfigurationError("nope"),
        ), patch(
            "mcp_server.server.build_google_calendar_adapter",
            side_effect=ConfigurationError("nope"),
        ), patch(
            "mcp_server.server.build_gmail_adapter",
            side_effect=ConfigurationError("nope"),
        ):
            with self.assertRaises(ConfigurationError) as cm:
                build_registry({})
            self.assertIn("No source adapters", str(cm.exception))


# ---------------------------------------------------------------------------
# register_tools
# ---------------------------------------------------------------------------


class _FakeCalendarAdapter:
    def __init__(self) -> None:
        self.capabilities = AdapterCapabilities(
            source_name="google_calendar",
            supports_search=True,
            supports_time_range=True,
            supports_threading=False,
        )

    async def find_free_slot(
        self, *, duration_minutes: int, within_days: int
    ) -> datetime | None:
        return datetime(2026, 5, 5, 10, 0, tzinfo=_UTC)

    async def list_events_in_range(
        self,
        *,
        time_min: datetime,
        time_max: datetime,
        limit: int = 50,
    ) -> Sequence[Event]:
        return (
            Event(
                id="e1",
                source="google_calendar",
                title="Standup",
                start=time_min,
                end=time_min,
                attendees=(),
                location=None,
                description=None,
                raw=MappingProxyType({}),
            ),
        )

    async def list_recent(
        self, *, since: datetime, limit: int
    ) -> Sequence[Event]:
        return ()

    async def get(self, item_id: str) -> Event:  # pragma: no cover
        raise NotImplementedError

    async def search(
        self, query: str, *, limit: int
    ) -> Sequence[Any]:
        return ()


class _FakeGmailAdapter:
    def __init__(self) -> None:
        self.capabilities = AdapterCapabilities(
            source_name="gmail",
            supports_search=True,
            supports_time_range=True,
            supports_threading=True,
        )

    async def get_thread(self, thread_id: str) -> Sequence[Message]:
        return (
            Message(
                id="m1",
                source="gmail",
                thread_id=thread_id,
                subject="Re: x",
                sender=Person(name=None, email=None),
                recipients=(),
                sent_at=datetime(2026, 5, 5, 13, 0, tzinfo=_UTC),
                snippet="",
                is_unread=False,
                raw=MappingProxyType({}),
            ),
        )

    async def list_recent(
        self, *, since: datetime, limit: int
    ) -> Sequence[Message]:
        return ()

    async def get(self, item_id: str) -> Message:  # pragma: no cover
        raise NotImplementedError

    async def search(
        self, query: str, *, limit: int
    ) -> Sequence[Any]:
        return ()


class _FakeJiraAdapter:
    def __init__(self) -> None:
        self.capabilities = AdapterCapabilities(
            source_name="jira",
            supports_search=True,
            supports_time_range=True,
            supports_threading=False,
        )

    async def search_jql(
        self, jql: str, *, limit: int
    ) -> Sequence[Ticket]:
        return ()

    async def list_recent(
        self, *, since: datetime, limit: int
    ) -> Sequence[Ticket]:
        return ()

    async def get(self, item_id: str) -> Ticket:  # pragma: no cover
        raise NotImplementedError

    async def search(
        self, query: str, *, limit: int
    ) -> Sequence[Any]:
        return ()


class TestRegisterTools(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.registry = AdapterRegistry()
        self.registry.register(_FakeCalendarAdapter())  # type: ignore[arg-type]
        self.registry.register(_FakeGmailAdapter())  # type: ignore[arg-type]
        self.registry.register(_FakeJiraAdapter())  # type: ignore[arg-type]
        self.mcp: FastMCP = FastMCP("Alfred-test")
        register_tools(self.mcp, self.registry)

    async def test_all_seven_tools_are_registered(self) -> None:
        names = {t.name for t in await self.mcp.list_tools()}
        self.assertEqual(
            names,
            {
                "alfred_search",
                "alfred_list_recent",
                "alfred_get",
                "calendar_list_events_in_range",
                "calendar_find_free_slot",
                "gmail_get_thread",
                "jira_search_jql",
            },
        )

    async def test_calendar_list_events_in_range_returns_event_dicts(
        self,
    ) -> None:
        _content, structured = await self.mcp.call_tool(
            "calendar_list_events_in_range",
            {
                "time_min": "2026-05-05T00:00:00+00:00",
                "time_max": "2026-05-06T00:00:00+00:00",
            },
        )
        self.assertEqual(len(structured["result"]), 1)
        self.assertEqual(structured["result"][0]["id"], "e1")

    async def test_calendar_find_free_slot_returns_iso_string(self) -> None:
        _content, structured = await self.mcp.call_tool(
            "calendar_find_free_slot",
            {"duration_minutes": 30, "within_days": 1},
        )
        self.assertEqual(structured["result"], "2026-05-05T10:00:00+00:00")

    async def test_gmail_get_thread_returns_list_of_messages(self) -> None:
        _content, structured = await self.mcp.call_tool(
            "gmail_get_thread", {"thread_id": "thr_zzz"}
        )
        self.assertEqual(len(structured["result"]), 1)
        self.assertEqual(structured["result"][0]["id"], "m1")

    async def test_alfred_search_returns_empty_list_with_no_data(
        self,
    ) -> None:
        _content, structured = await self.mcp.call_tool(
            "alfred_search", {"query": "anything"}
        )
        self.assertEqual(structured["result"], [])


if __name__ == "__main__":
    unittest.main()
