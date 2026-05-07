"""Pure mappers from Jira issue dicts to Alfred's canonical types.

No I/O, no network. Adapters call these after the HTTP client has parsed
the JSON body. Atlassian's user nodes frequently omit ``emailAddress`` (the
account-privacy setting) and may even omit ``displayName`` for deactivated
accounts; both are tolerated rather than raised on.
"""

from __future__ import annotations

from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping

from mcp_server.core.canonical import Person, SearchHit, Ticket


def map_issue_to_ticket(issue: Mapping[str, Any], *, base_url: str) -> Ticket:
    """Convert a Jira issue payload into a canonical :class:`Ticket`.

    ``issue`` is the dict returned by ``GET /rest/api/3/issue/{key}`` or one
    element of the ``issues`` array from ``/rest/api/3/search/jql``. The
    full payload is preserved on ``Ticket.raw`` (wrapped read-only) so
    callers can read fields that have not yet been promoted to the
    canonical schema.
    """
    fields: Mapping[str, Any] = issue.get("fields") or {}
    key: str = issue["key"]
    status_node: Mapping[str, Any] = fields.get("status") or {}
    priority_node = fields.get("priority")
    return Ticket(
        id=key,
        source="jira",
        summary=fields.get("summary") or "",
        status=status_node.get("name") or "",
        assignee=_person_from_user(fields.get("assignee")),
        reporter=_person_from_user(fields.get("reporter")),
        priority=priority_node.get("name") if priority_node else None,
        updated_at=_parse_jira_datetime(fields["updated"]),
        url=f"{base_url.rstrip('/')}/browse/{key}",
        raw=MappingProxyType(dict(issue)),
    )


def map_issue_to_search_hit(
    issue: Mapping[str, Any], *, base_url: str
) -> SearchHit:
    """Convert a Jira issue payload into a canonical :class:`SearchHit`.

    The ``/search/jql`` endpoint does not return a snippet field, so
    ``snippet`` mirrors ``title`` (the issue summary).
    """
    fields: Mapping[str, Any] = issue.get("fields") or {}
    key: str = issue["key"]
    summary: str = fields.get("summary") or ""
    return SearchHit(
        source="jira",
        item_id=key,
        title=summary,
        snippet=summary,
        url=f"{base_url.rstrip('/')}/browse/{key}",
        relevance=None,
    )


def _person_from_user(node: Mapping[str, Any] | None) -> Person | None:
    if node is None:
        return None
    return Person(name=node.get("displayName"), email=node.get("emailAddress"))


def _parse_jira_datetime(value: str) -> datetime:
    """Parse Jira's ISO-8601 timestamps.

    Python 3.11+ ``datetime.fromisoformat`` handles ``Z`` and ``±HHMM``
    natively, so the happy path is one call. The fallback normalizes to
    ``+HH:MM`` form in case Atlassian emits a flavor the stdlib rejects.
    """
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        normalized = value.replace("Z", "+00:00")
        if (
            len(normalized) >= 5
            and normalized[-5] in "+-"
            and normalized[-3] != ":"
        ):
            normalized = normalized[:-2] + ":" + normalized[-2:]
        return datetime.fromisoformat(normalized)
