from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from mcp_server.adapters.jira.jql_query_builder import (
    JIRA_FIELDS,
    build_recent_jql,
    build_text_search_jql,
    escape_jql_string,
)


class TestEscapeJqlString(unittest.TestCase):
    def test_plain_text_unchanged(self) -> None:
        self.assertEqual(escape_jql_string("hello world"), "hello world")

    def test_backslash_doubled(self) -> None:
        self.assertEqual(escape_jql_string(r"a\b"), r"a\\b")

    def test_double_quote_escaped(self) -> None:
        self.assertEqual(escape_jql_string('a"b'), r'a\"b')

    def test_backslash_then_quote_escaped_in_order(self) -> None:
        # Input: \"   →  must escape the backslash first, then the quote,
        # otherwise the new \ from the quote-escape would be re-escaped.
        self.assertEqual(escape_jql_string('\\"'), r'\\\"')

    def test_newline_replaced_with_space(self) -> None:
        self.assertEqual(escape_jql_string("a\nb"), "a b")

    def test_carriage_return_replaced_with_space(self) -> None:
        self.assertEqual(escape_jql_string("a\rb"), "a b")

    def test_tab_replaced_with_space(self) -> None:
        self.assertEqual(escape_jql_string("a\tb"), "a b")

    def test_single_quote_unchanged(self) -> None:
        # Inside a JQL double-quoted string, ' is just a regular character.
        self.assertEqual(escape_jql_string("it's"), "it's")


class TestBuildTextSearchJql(unittest.TestCase):
    def test_simple_query(self) -> None:
        self.assertEqual(
            build_text_search_jql("urgent bug"),
            'text ~ "urgent bug" ORDER BY updated DESC',
        )

    def test_query_with_quote_is_escaped(self) -> None:
        self.assertEqual(
            build_text_search_jql('say "hi"'),
            'text ~ "say \\"hi\\"" ORDER BY updated DESC',
        )

    def test_query_with_newline_normalized(self) -> None:
        self.assertEqual(
            build_text_search_jql("line1\nline2"),
            'text ~ "line1 line2" ORDER BY updated DESC',
        )


class TestBuildRecentJql(unittest.TestCase):
    def test_aware_utc_datetime(self) -> None:
        since = datetime(2026, 5, 4, 13, 30, tzinfo=timezone.utc)
        self.assertEqual(
            build_recent_jql(since),
            'updated >= "2026/05/04 13:30" ORDER BY updated DESC',
        )

    def test_aware_non_utc_datetime_converted_to_utc(self) -> None:
        # 09:30 in UTC-04:00 == 13:30 UTC
        eastern = timezone(timedelta(hours=-4))
        since = datetime(2026, 5, 4, 9, 30, tzinfo=eastern)
        self.assertEqual(
            build_recent_jql(since),
            'updated >= "2026/05/04 13:30" ORDER BY updated DESC',
        )

    def test_naive_datetime_treated_as_utc(self) -> None:
        since = datetime(2026, 5, 4, 13, 30)
        self.assertEqual(
            build_recent_jql(since),
            'updated >= "2026/05/04 13:30" ORDER BY updated DESC',
        )


class TestJiraFields(unittest.TestCase):
    def test_fields_match_canonical_ticket(self) -> None:
        self.assertEqual(
            JIRA_FIELDS,
            ("summary", "status", "assignee", "reporter", "priority", "updated"),
        )


if __name__ == "__main__":
    unittest.main()
