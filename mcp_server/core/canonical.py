"""Canonical, normalized representations of items returned by SourceAdapters.

Adapters are responsible for mapping their source-specific JSON shapes into
these dataclasses. Each item also carries a ``raw`` mapping as an escape hatch
for fields not yet promoted into the canonical schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, TypeAlias


@dataclass(frozen=True)
class Person:
    name: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class Event:
    id: str
    source: str
    title: str
    start: datetime
    end: datetime
    attendees: tuple[Person, ...]
    location: str | None
    description: str | None
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class Message:
    id: str
    source: str
    thread_id: str
    subject: str
    sender: Person
    recipients: tuple[Person, ...]
    sent_at: datetime
    snippet: str
    is_unread: bool
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class Ticket:
    id: str
    source: str
    summary: str
    status: str
    assignee: Person | None
    reporter: Person | None
    priority: str | None
    updated_at: datetime
    url: str
    raw: Mapping[str, Any]


SourceItem: TypeAlias = Event | Message | Ticket


@dataclass(frozen=True)
class SearchHit:
    source: str
    item_id: str
    title: str
    snippet: str
    url: str | None = None
    relevance: float | None = None
