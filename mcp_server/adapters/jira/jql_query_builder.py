"""Build JQL strings safely from typed inputs.

JQL injection is real — never splice unescaped user-supplied text into a JQL
clause. This module is the single place that constructs JQL fragments for
the Jira adapter. Public surface:

- :data:`JIRA_FIELDS` — the canonical field list to request from
  ``/rest/api/3/issue`` and ``/rest/api/3/search/jql``.
- :func:`escape_jql_string` — escapes a string for use inside a JQL
  double-quoted literal.
- :func:`build_text_search_jql` — wraps a free-text query in a safe JQL
  ``text ~ "..."`` clause.
- :func:`build_recent_jql` — builds a time-range clause for ``list_recent``;
  always emits a UTC-normalized timestamp.
"""

from __future__ import annotations

from datetime import datetime, timezone


JIRA_FIELDS: tuple[str, ...] = (
    "summary",
    "status",
    "assignee",
    "reporter",
    "priority",
    "updated",
)


_JQL_DATETIME_FORMAT = "%Y/%m/%d %H:%M"
_CONTROL_CHAR_TO_SPACE = str.maketrans({"\n": " ", "\r": " ", "\t": " "})


def escape_jql_string(value: str) -> str:
    """Escape *value* for inclusion inside a JQL double-quoted string literal.

    Per Atlassian's JQL spec, the only characters that require escaping
    inside ``"..."`` are backslash and double-quote. Control characters
    (newline, carriage return, tab) corrupt JQL parsing on the server, so
    they are normalized to a space before escaping.

    The caller is responsible for wrapping the returned value in ``"..."``.
    """
    normalized = value.translate(_CONTROL_CHAR_TO_SPACE)
    backslash_escaped = normalized.replace("\\", "\\\\")
    return backslash_escaped.replace('"', '\\"')


def build_text_search_jql(query: str) -> str:
    """JQL clause matching *query* against all text fields, newest first."""
    return f'text ~ "{escape_jql_string(query)}" ORDER BY updated DESC'


def build_recent_jql(since: datetime) -> str:
    """JQL clause for issues updated on/after *since*, newest first.

    Naive datetimes are assumed to be UTC. Aware datetimes are converted to
    UTC before formatting, so the emitted clause is timezone-stable
    regardless of where the caller built the input.
    """
    if since.tzinfo is None:
        since_utc = since.replace(tzinfo=timezone.utc)
    else:
        since_utc = since.astimezone(timezone.utc)
    formatted = since_utc.strftime(_JQL_DATETIME_FORMAT)
    return f'updated >= "{formatted}" ORDER BY updated DESC'
