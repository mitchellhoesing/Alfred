"""Source-specific MCP tools — escape hatches that don't fit the
generic :class:`SourceAdapter` ABC.

These tools call methods that exist only on a particular concrete
adapter:

- :func:`calendar_list_events_in_range` → ``GoogleCalendarSourceAdapter.list_events_in_range``
- :func:`calendar_find_free_slot` → ``GoogleCalendarSourceAdapter.find_free_slot``
- :func:`gmail_get_thread` → ``GmailSourceAdapter.get_thread``
- :func:`jira_search_jql` → ``JiraSourceAdapter.search_jql``

Each tool resolves its adapter by source name from the
:class:`AdapterRegistry`, so the dependency on the registry is explicit
and the concrete adapter classes are not imported by the tools layer
(only by ``server.py`` at wiring time). The expected adapter contract is
documented inline as a :class:`Protocol`; the cast is unchecked at
runtime — if the registry has the wrong adapter type, the call fails
loudly at the method dispatch with an :class:`AttributeError`, which is
the appropriate failure mode for a server-config bug.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, Sequence, cast

from mcp_server.core.canonical import Event, Message, Ticket
from mcp_server.core.canonical_serializer import to_jsonable
from mcp_server.core.registry import AdapterRegistry


class _CalendarRangeAdapter(Protocol):
    async def list_events_in_range(
        self,
        *,
        time_min: datetime,
        time_max: datetime,
        limit: int = 50,
    ) -> Sequence[Event]: ...


class _CalendarFreeSlotAdapter(Protocol):
    async def find_free_slot(
        self,
        *,
        duration_minutes: int,
        within_days: int,
    ) -> datetime | None: ...


class _GmailThreadAdapter(Protocol):
    async def get_thread(self, thread_id: str) -> Sequence[Message]: ...


class _JiraJqlAdapter(Protocol):
    async def search_jql(
        self, jql: str, *, limit: int
    ) -> Sequence[Ticket]: ...


async def calendar_list_events_in_range(
    registry: AdapterRegistry,
    *,
    time_min: str,
    time_max: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return Calendar events whose start falls in ``[time_min, time_max]``.

    Both bounds are ISO 8601 strings parsed via
    :meth:`datetime.fromisoformat`. Use this for "what's on my schedule
    today / this week" workflows; ``alfred_list_recent`` filters by
    update time rather than start time, so it's the wrong tool for that.
    """
    adapter = cast(_CalendarRangeAdapter, registry.get("google_calendar"))
    events = await adapter.list_events_in_range(
        time_min=datetime.fromisoformat(time_min),
        time_max=datetime.fromisoformat(time_max),
        limit=limit,
    )
    return [to_jsonable(e) for e in events]


async def calendar_find_free_slot(
    registry: AdapterRegistry,
    *,
    duration_minutes: int,
    within_days: int,
) -> str | None:
    """Find the first ``duration_minutes`` slot within ``within_days`` days.

    Returns an ISO 8601 datetime string, or :data:`None` when no slot
    fits in the search window.
    """
    adapter = cast(
        _CalendarFreeSlotAdapter, registry.get("google_calendar")
    )
    slot = await adapter.find_free_slot(
        duration_minutes=duration_minutes, within_days=within_days
    )
    return slot.isoformat() if slot is not None else None


async def gmail_get_thread(
    registry: AdapterRegistry,
    *,
    thread_id: str,
) -> list[dict[str, Any]]:
    """Return every Message in *thread_id*, oldest first, as JSON dicts."""
    adapter = cast(_GmailThreadAdapter, registry.get("gmail"))
    messages = await adapter.get_thread(thread_id)
    return [to_jsonable(m) for m in messages]


async def jira_search_jql(
    registry: AdapterRegistry,
    *,
    jql: str,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Run a caller-supplied JQL query and return a list of Ticket dicts.

    The JQL string is passed through to Jira **without escaping**. Use
    this only with trusted JQL; user-supplied substrings must be escaped
    via
    :func:`mcp_server.adapters.jira.jql_query_builder.escape_jql_string`
    before being spliced into ``jql``.
    """
    adapter = cast(_JiraJqlAdapter, registry.get("jira"))
    tickets = await adapter.search_jql(jql, limit=limit)
    return [to_jsonable(t) for t in tickets]
