"""Concrete :class:`SourceAdapter` for Google Calendar.

Bridges the async :class:`SourceAdapter` ABC to the sync
:class:`GoogleCalendarApiClient` via :func:`asyncio.to_thread`. Each ABC
method has a private sync counterpart so the mapping logic is testable
without spinning up an event loop.

The Calendar-specific :meth:`find_free_slot` is exposed via the
``calendar_find_free_slot`` MCP tool (see :mod:`mcp_server.tools.specific`).
The pure gap-finding algorithm lives in
:mod:`mcp_server.adapters.google_calendar.calendar_free_slot_finder`;
this adapter only loads events and projects them to busy intervals.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Sequence

from mcp_server.adapters.google_calendar.calendar_event_mapper import (
    map_event_to_canonical,
    map_event_to_search_hit,
)
from mcp_server.adapters.google_calendar.calendar_free_slot_finder import (
    find_first_free_slot,
)
from mcp_server.adapters.google_calendar.google_calendar_api_client import (
    GoogleCalendarApiClient,
)
from mcp_server.core.canonical import Event, SearchHit
from mcp_server.core.source_adapter import AdapterCapabilities, SourceAdapter


_FREE_SLOT_MAX_EVENTS = 250


_CAPABILITIES = AdapterCapabilities(
    source_name="google_calendar",
    supports_search=True,
    supports_time_range=True,
    supports_threading=False,
)


class GoogleCalendarSourceAdapter(SourceAdapter):
    """Adapter wiring Google Calendar into Alfred's :class:`SourceAdapter` ABC."""

    def __init__(self, client: GoogleCalendarApiClient) -> None:
        self._client = client

    @property
    def capabilities(self) -> AdapterCapabilities:
        return _CAPABILITIES

    async def list_recent(
        self, *, since: datetime, limit: int
    ) -> Sequence[Event]:
        return await asyncio.to_thread(self._list_recent_sync, since, limit)

    async def get(self, item_id: str) -> Event:
        return await asyncio.to_thread(self._get_sync, item_id)

    async def search(
        self, query: str, *, limit: int
    ) -> Sequence[SearchHit]:
        return await asyncio.to_thread(self._search_sync, query, limit)

    async def list_events_in_range(
        self,
        *,
        time_min: datetime,
        time_max: datetime,
        limit: int = 50,
    ) -> Sequence[Event]:
        """Return events whose start falls in ``[time_min, time_max]``.

        Source-specific (not on the :class:`SourceAdapter` ABC).
        :meth:`list_recent` filters by ``updated_min``, which surfaces
        rescheduled / newly-added events but misses standing meetings on
        the schedule. This method instead filters by event start/end
        time, which is what "what's on my schedule" workflows want.
        """
        return await asyncio.to_thread(
            self._list_events_in_range_sync, time_min, time_max, limit
        )

    async def find_free_slot(
        self,
        *,
        duration_minutes: int,
        within_days: int,
        now: datetime | None = None,
    ) -> datetime | None:
        """Return the start of the first free slot of ``duration_minutes``.

        Source-specific (not on the :class:`SourceAdapter` ABC). Searches
        ``[now, now + within_days]`` and returns the start of the first
        gap that accommodates ``duration_minutes``, or :data:`None` if no
        such gap exists.

        ``now`` is injectable for deterministic tests; production callers
        leave it as :data:`None` to use the current UTC instant.
        """
        anchor = now if now is not None else datetime.now(timezone.utc)
        return await asyncio.to_thread(
            self._find_free_slot_sync,
            duration_minutes,
            within_days,
            anchor,
        )

    def _list_recent_sync(
        self, since: datetime, limit: int
    ) -> tuple[Event, ...]:
        result = self._client.list_events(
            updated_min=since, max_results=limit
        )
        items = result.get("items") or ()
        return tuple(map_event_to_canonical(e) for e in items)

    def _get_sync(self, item_id: str) -> Event:
        body = self._client.get_event(item_id)
        return map_event_to_canonical(body)

    def _search_sync(self, query: str, limit: int) -> tuple[SearchHit, ...]:
        result = self._client.list_events(q=query, max_results=limit)
        items = result.get("items") or ()
        return tuple(map_event_to_search_hit(e) for e in items)

    def _list_events_in_range_sync(
        self,
        time_min: datetime,
        time_max: datetime,
        limit: int,
    ) -> tuple[Event, ...]:
        result = self._client.list_events(
            time_min=time_min, time_max=time_max, max_results=limit
        )
        items = result.get("items") or ()
        return tuple(map_event_to_canonical(e) for e in items)

    def _find_free_slot_sync(
        self,
        duration_minutes: int,
        within_days: int,
        now: datetime,
    ) -> datetime | None:
        window_end = now + timedelta(days=within_days)
        result = self._client.list_events(
            time_min=now,
            time_max=window_end,
            max_results=_FREE_SLOT_MAX_EVENTS,
        )
        events = result.get("items") or ()
        busy = tuple(
            (
                _to_aware_utc(event.start),
                _to_aware_utc(event.end),
            )
            for event in (map_event_to_canonical(e) for e in events)
        )
        return find_first_free_slot(
            busy,
            window_start=now,
            window_end=window_end,
            duration=timedelta(minutes=duration_minutes),
        )


def _to_aware_utc(dt: datetime) -> datetime:
    """All-day events surface as naive datetimes (calendar-local midnight).

    The free-slot finder requires aware datetimes; we treat naive as UTC
    midnight, matching the convention documented on
    :func:`map_event_to_canonical`.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
