from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Sequence

from mcp_server.core.canonical import Event, Message, Person, Ticket
from mcp_server.core.registry import AdapterRegistry
from mcp_server.core.source_adapter import AdapterCapabilities
from mcp_server.tools.specific import (
    calendar_find_free_slot,
    calendar_list_events_in_range,
    gmail_get_thread,
    jira_search_jql,
)


_UTC = timezone.utc


# Each fake exposes only the surface area the tool under test needs:
# the `capabilities` property (so the registry will register it under the
# expected source name) and the one source-specific async method. The
# AdapterRegistry doesn't enforce the SourceAdapter ABC at runtime, so
# these fakes don't need the full abstract interface.


class _FakeCalendarAdapter:
    def __init__(self) -> None:
        self.capabilities = AdapterCapabilities(
            source_name="google_calendar",
            supports_search=True,
            supports_time_range=True,
            supports_threading=False,
        )
        self.find_free_slot_result: datetime | None = None
        self.last_kwargs: dict[str, Any] | None = None
        self.range_response: tuple[Event, ...] = ()
        self.last_range_kwargs: dict[str, Any] | None = None

    async def find_free_slot(
        self,
        *,
        duration_minutes: int,
        within_days: int,
    ) -> datetime | None:
        self.last_kwargs = {
            "duration_minutes": duration_minutes,
            "within_days": within_days,
        }
        return self.find_free_slot_result

    async def list_events_in_range(
        self,
        *,
        time_min: datetime,
        time_max: datetime,
        limit: int = 50,
    ) -> Sequence[Event]:
        self.last_range_kwargs = {
            "time_min": time_min,
            "time_max": time_max,
            "limit": limit,
        }
        return self.range_response


class _FakeGmailAdapter:
    def __init__(self) -> None:
        self.capabilities = AdapterCapabilities(
            source_name="gmail",
            supports_search=True,
            supports_time_range=True,
            supports_threading=True,
        )
        self.thread_response: tuple[Message, ...] = ()
        self.last_thread_id: str | None = None

    async def get_thread(self, thread_id: str) -> Sequence[Message]:
        self.last_thread_id = thread_id
        return self.thread_response


class _FakeJiraAdapter:
    def __init__(self) -> None:
        self.capabilities = AdapterCapabilities(
            source_name="jira",
            supports_search=True,
            supports_time_range=True,
            supports_threading=False,
        )
        self.search_jql_response: tuple[Ticket, ...] = ()
        self.last_kwargs: dict[str, Any] | None = None

    async def search_jql(
        self, jql: str, *, limit: int
    ) -> Sequence[Ticket]:
        self.last_kwargs = {"jql": jql, "limit": limit}
        return self.search_jql_response


def _registry_with(*adapters: Any) -> AdapterRegistry:
    registry = AdapterRegistry()
    for a in adapters:
        registry.register(a)  # type: ignore[arg-type]
    return registry


def _message(mid: str) -> Message:
    return Message(
        id=mid,
        source="gmail",
        thread_id="thr_zzz",
        subject="x",
        sender=Person(name=None, email=None),
        recipients=(),
        sent_at=datetime(2026, 5, 5, 13, 0, tzinfo=_UTC),
        snippet="",
        is_unread=False,
        raw=MappingProxyType({}),
    )


def _event(eid: str) -> Event:
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


def _ticket(tid: str) -> Ticket:
    return Ticket(
        id=tid,
        source="jira",
        summary="t",
        status="In Progress",
        assignee=None,
        reporter=None,
        priority=None,
        updated_at=datetime(2026, 5, 5, 12, 0, tzinfo=_UTC),
        url=f"https://example.atlassian.net/browse/{tid}",
        raw=MappingProxyType({}),
    )


class TestCalendarListEventsInRange(unittest.IsolatedAsyncioTestCase):
    async def test_parses_iso_strings_and_returns_event_dicts(self) -> None:
        cal = _FakeCalendarAdapter()
        cal.range_response = (_event("e1"), _event("e2"))
        registry = _registry_with(cal)

        result = await calendar_list_events_in_range(
            registry,
            time_min="2026-05-05T00:00:00+00:00",
            time_max="2026-05-06T00:00:00+00:00",
            limit=25,
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "e1")
        assert cal.last_range_kwargs is not None
        self.assertEqual(
            cal.last_range_kwargs["time_min"],
            datetime(2026, 5, 5, 0, 0, tzinfo=_UTC),
        )
        self.assertEqual(
            cal.last_range_kwargs["time_max"],
            datetime(2026, 5, 6, 0, 0, tzinfo=_UTC),
        )
        self.assertEqual(cal.last_range_kwargs["limit"], 25)

    async def test_default_limit_is_50(self) -> None:
        cal = _FakeCalendarAdapter()
        registry = _registry_with(cal)

        await calendar_list_events_in_range(
            registry,
            time_min="2026-05-05T00:00:00+00:00",
            time_max="2026-05-06T00:00:00+00:00",
        )
        assert cal.last_range_kwargs is not None
        self.assertEqual(cal.last_range_kwargs["limit"], 50)


class TestCalendarFindFreeSlot(unittest.IsolatedAsyncioTestCase):
    async def test_returns_iso_string_when_slot_found(self) -> None:
        cal = _FakeCalendarAdapter()
        cal.find_free_slot_result = datetime(2026, 5, 5, 10, 0, tzinfo=_UTC)
        registry = _registry_with(cal)

        result = await calendar_find_free_slot(
            registry, duration_minutes=30, within_days=2
        )

        self.assertEqual(result, "2026-05-05T10:00:00+00:00")
        self.assertEqual(
            cal.last_kwargs,
            {"duration_minutes": 30, "within_days": 2},
        )

    async def test_returns_none_when_no_slot_found(self) -> None:
        cal = _FakeCalendarAdapter()
        cal.find_free_slot_result = None
        registry = _registry_with(cal)

        result = await calendar_find_free_slot(
            registry, duration_minutes=60, within_days=1
        )
        self.assertIsNone(result)


class TestGmailGetThread(unittest.IsolatedAsyncioTestCase):
    async def test_returns_list_of_message_dicts(self) -> None:
        gmail = _FakeGmailAdapter()
        gmail.thread_response = (_message("m1"), _message("m2"))
        registry = _registry_with(gmail)

        result = await gmail_get_thread(registry, thread_id="thr_zzz")

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "m1")
        self.assertEqual(result[1]["id"], "m2")
        self.assertEqual(gmail.last_thread_id, "thr_zzz")

    async def test_empty_thread_returns_empty_list(self) -> None:
        gmail = _FakeGmailAdapter()
        gmail.thread_response = ()
        registry = _registry_with(gmail)

        result = await gmail_get_thread(registry, thread_id="thr_x")
        self.assertEqual(result, [])


class TestJiraSearchJql(unittest.IsolatedAsyncioTestCase):
    async def test_returns_list_of_ticket_dicts(self) -> None:
        jira = _FakeJiraAdapter()
        jira.search_jql_response = (_ticket("ALF-1"), _ticket("ALF-2"))
        registry = _registry_with(jira)

        result = await jira_search_jql(
            registry, jql='assignee = currentUser()', limit=10
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "ALF-1")
        self.assertEqual(
            jira.last_kwargs,
            {"jql": 'assignee = currentUser()', "limit": 10},
        )

    async def test_default_limit_is_25(self) -> None:
        jira = _FakeJiraAdapter()
        registry = _registry_with(jira)

        await jira_search_jql(registry, jql="x")

        assert jira.last_kwargs is not None
        self.assertEqual(jira.last_kwargs["limit"], 25)


if __name__ == "__main__":
    unittest.main()
