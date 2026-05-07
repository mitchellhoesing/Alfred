"""Pure mappers from Google Calendar event dicts to Alfred's canonical types.

No I/O, no network. The :class:`GoogleCalendarApiClient` calls these after
the API returns a parsed JSON body.

Two start/end shapes coexist in Google Calendar:

- **Timed events** carry ``start.dateTime`` (ISO-8601 with offset) and
  optionally ``start.timeZone``. We parse the ISO timestamp directly,
  preserving the original offset on the resulting :class:`datetime`. The
  raw dict still holds the timezone label for callers that need it.
- **All-day events** carry ``start.date`` (YYYY-MM-DD) only. We map these
  to **naive** datetimes at midnight; downstream code should treat naive
  Event datetimes as "the calendar's local midnight on that date" rather
  than as a UTC wall-clock.

Optional fields (``summary``, ``description``, ``location``, ``attendees``)
default to ``""`` / ``None`` / ``()`` when missing.
"""

from __future__ import annotations

from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping

from mcp_server.core.canonical import Event, Person, SearchHit


def map_event_to_canonical(event: Mapping[str, Any]) -> Event:
    """Convert a Google Calendar event payload into a canonical :class:`Event`."""
    return Event(
        id=event["id"],
        source="google_calendar",
        title=event.get("summary") or "",
        start=_parse_event_endpoint(event["start"]),
        end=_parse_event_endpoint(event["end"]),
        attendees=_attendees_from(event.get("attendees")),
        location=event.get("location"),
        description=event.get("description"),
        raw=MappingProxyType(dict(event)),
    )


def map_event_to_search_hit(event: Mapping[str, Any]) -> SearchHit:
    """Convert a Google Calendar event payload into a canonical :class:`SearchHit`.

    Snippet preference is description → summary → empty string. The
    ``htmlLink`` is used as the canonical URL.
    """
    title = event.get("summary") or ""
    snippet = event.get("description") or title
    return SearchHit(
        source="google_calendar",
        item_id=event["id"],
        title=title,
        snippet=snippet,
        url=event.get("htmlLink"),
        relevance=None,
    )


def _parse_event_endpoint(endpoint: Mapping[str, Any]) -> datetime:
    """Parse a Calendar ``start`` or ``end`` block into a datetime."""
    if "dateTime" in endpoint:
        return datetime.fromisoformat(endpoint["dateTime"])
    # All-day event: only ``date`` is present.
    return datetime.fromisoformat(endpoint["date"])


def _attendees_from(
    attendees_node: Any,
) -> tuple[Person, ...]:
    if not attendees_node:
        return ()
    return tuple(
        Person(name=a.get("displayName"), email=a.get("email"))
        for a in attendees_node
    )
