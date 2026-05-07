"""Pure mappers from Gmail message payloads to Alfred's canonical types.

No I/O. The :class:`GmailApiClient` calls these after the API returns a
parsed JSON body for ``users.messages.get`` (in ``metadata`` format).

Header parsing:

- ``Subject`` is read case-insensitively. Missing → ``""``.
- ``From`` is parsed via :func:`email.utils.parseaddr`. An email-only
  address (no display name) maps to ``Person(name=None, email="...")``.
  A missing ``From`` header maps to ``Person(name=None, email=None)``.
- ``To`` is parsed via :func:`email.utils.getaddresses`. Multiple
  recipients are preserved in order. Missing → ``()``.
- ``internalDate`` is millis since the Unix epoch (UTC) per Gmail docs;
  always interpreted as UTC.
- ``is_unread`` is ``"UNREAD" in labelIds``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import getaddresses, parseaddr
from types import MappingProxyType
from typing import Any, Mapping

from mcp_server.core.canonical import Message, Person, SearchHit


_GMAIL_MESSAGE_URL_TEMPLATE = "https://mail.google.com/mail/u/0/#all/{message_id}"


def map_message_to_canonical(message: Mapping[str, Any]) -> Message:
    """Convert a Gmail messages.get(metadata) payload into a canonical :class:`Message`."""
    headers = _headers_from_payload(message.get("payload"))
    label_ids = message.get("labelIds") or ()
    return Message(
        id=message["id"],
        source="gmail",
        thread_id=message["threadId"],
        subject=headers.get("subject", ""),
        sender=_parse_sender(headers.get("from")),
        recipients=_parse_recipients(headers.get("to")),
        sent_at=_parse_internal_date(message["internalDate"]),
        snippet=message.get("snippet") or "",
        is_unread="UNREAD" in label_ids,
        raw=MappingProxyType(dict(message)),
    )


def map_message_to_search_hit(message: Mapping[str, Any]) -> SearchHit:
    """Convert a Gmail messages.get(metadata) payload into a canonical :class:`SearchHit`."""
    headers = _headers_from_payload(message.get("payload"))
    return SearchHit(
        source="gmail",
        item_id=message["id"],
        title=headers.get("subject", ""),
        snippet=message.get("snippet") or "",
        url=_GMAIL_MESSAGE_URL_TEMPLATE.format(message_id=message["id"]),
        relevance=None,
    )


def _headers_from_payload(payload: Any) -> dict[str, str]:
    if not payload:
        return {}
    headers_node = payload.get("headers") or ()
    return {h["name"].lower(): h["value"] for h in headers_node}


def _parse_sender(raw_from: str | None) -> Person:
    if not raw_from:
        return Person(name=None, email=None)
    name, email = parseaddr(raw_from)
    return Person(name=name or None, email=email or None)


def _parse_recipients(raw_to: str | None) -> tuple[Person, ...]:
    if not raw_to:
        return ()
    return tuple(
        Person(name=name or None, email=email or None)
        for name, email in getaddresses([raw_to])
    )


def _parse_internal_date(raw: str | int) -> datetime:
    millis = int(raw)
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
