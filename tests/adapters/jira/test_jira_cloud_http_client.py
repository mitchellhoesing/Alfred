from __future__ import annotations

import base64
import json
import logging
import unittest
from typing import Any, Mapping
from unittest.mock import patch

import requests

from mcp_server.adapters.jira.jira_cloud_http_client import (
    JiraCloudHttpClient,
    JiraCloudHttpClientConfig,
)
from mcp_server.core.auth_provider import StaticJiraAuthProvider
from mcp_server.core.errors import (
    AdapterError,
    AuthError,
    ItemNotFoundError,
    RateLimitError,
)


class _FakeResponse:
    """Minimal stand-in for ``requests.Response`` used only by tests."""

    def __init__(
        self,
        status_code: int,
        *,
        json_body: Any = None,
        text: str = "",
        headers: Mapping[str, str] | None = None,
        raise_on_json: bool = False,
    ) -> None:
        self.status_code = status_code
        self.headers = dict(headers) if headers else {}
        self.text = text
        self._json_body = json_body
        self._raise_on_json = raise_on_json

    def json(self) -> Any:
        if self._raise_on_json:
            raise ValueError("not JSON")
        return self._json_body


class _FakeSession:
    """Records the last call and replays a single canned response."""

    def __init__(self, response: _FakeResponse | Exception) -> None:
        self._response = response
        self.last_get_args: dict[str, Any] | None = None
        self.last_post_args: dict[str, Any] | None = None

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> _FakeResponse:
        self.last_get_args = {
            "url": url,
            "headers": dict(headers),
            "params": dict(params) if params else None,
            "timeout": timeout,
        }
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        json: Any = None,
        timeout: float | None = None,
    ) -> _FakeResponse:
        self.last_post_args = {
            "url": url,
            "headers": dict(headers),
            "json": json,
            "timeout": timeout,
        }
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _config(base_url: str = "https://acme.atlassian.net") -> JiraCloudHttpClientConfig:
    return JiraCloudHttpClientConfig(base_url=base_url, timeout_seconds=5.0)


def _auth() -> StaticJiraAuthProvider:
    return StaticJiraAuthProvider(email="me@example.com", api_token="tkn")


def _build(session: _FakeSession) -> JiraCloudHttpClient:
    return JiraCloudHttpClient(_config(), _auth(), session=session)  # type: ignore[arg-type]


class TestAuthHeader(unittest.TestCase):
    def test_basic_header_is_base64_email_colon_token(self) -> None:
        session = _FakeSession(
            _FakeResponse(200, json_body={"key": "ALF-1", "fields": {}})
        )
        client = _build(session)
        client.get_issue("ALF-1", fields=("summary",))

        assert session.last_get_args is not None
        auth = session.last_get_args["headers"]["Authorization"]
        expected = base64.b64encode(b"me@example.com:tkn").decode("ascii")
        self.assertEqual(auth, f"Basic {expected}")

    def test_accept_header_is_application_json(self) -> None:
        session = _FakeSession(
            _FakeResponse(200, json_body={"key": "ALF-1", "fields": {}})
        )
        client = _build(session)
        client.get_issue("ALF-1", fields=("summary",))

        assert session.last_get_args is not None
        self.assertEqual(
            session.last_get_args["headers"]["Accept"], "application/json"
        )


class TestGetIssue(unittest.TestCase):
    def test_happy_path_returns_body(self) -> None:
        body = {"key": "ALF-1", "fields": {"summary": "x"}}
        session = _FakeSession(_FakeResponse(200, json_body=body))
        client = _build(session)

        result = client.get_issue("ALF-1", fields=("summary", "status"))

        self.assertEqual(result["key"], "ALF-1")
        assert session.last_get_args is not None
        self.assertEqual(
            session.last_get_args["url"],
            "https://acme.atlassian.net/rest/api/3/issue/ALF-1",
        )
        self.assertEqual(
            session.last_get_args["params"], {"fields": "summary,status"}
        )
        self.assertEqual(session.last_get_args["timeout"], 5.0)

    def test_404_raises_item_not_found(self) -> None:
        session = _FakeSession(_FakeResponse(404, text="missing"))
        client = _build(session)
        with self.assertRaises(ItemNotFoundError):
            client.get_issue("NOPE-1", fields=("summary",))

    def test_401_raises_auth_error(self) -> None:
        session = _FakeSession(_FakeResponse(401, text="unauth"))
        client = _build(session)
        with self.assertRaises(AuthError):
            client.get_issue("ALF-1", fields=("summary",))

    def test_403_raises_auth_error(self) -> None:
        session = _FakeSession(_FakeResponse(403, text="forbidden"))
        client = _build(session)
        with self.assertRaises(AuthError):
            client.get_issue("ALF-1", fields=("summary",))

    def test_400_raises_adapter_error(self) -> None:
        session = _FakeSession(_FakeResponse(400, text="bad jql"))
        client = _build(session)
        with self.assertRaises(AdapterError):
            client.get_issue("ALF-1", fields=("summary",))

    def test_410_raises_adapter_error(self) -> None:
        session = _FakeSession(_FakeResponse(410, text="gone"))
        client = _build(session)
        with self.assertRaises(AdapterError):
            client.get_issue("ALF-1", fields=("summary",))

    def test_500_raises_adapter_error(self) -> None:
        session = _FakeSession(_FakeResponse(500, text="oops"))
        client = _build(session)
        with self.assertRaises(AdapterError):
            client.get_issue("ALF-1", fields=("summary",))

    def test_429_with_retry_after_populates_field(self) -> None:
        session = _FakeSession(
            _FakeResponse(429, text="slow down", headers={"Retry-After": "30"})
        )
        client = _build(session)
        with self.assertRaises(RateLimitError) as cm:
            client.get_issue("ALF-1", fields=("summary",))
        self.assertEqual(cm.exception.retry_after_seconds, 30)

    def test_429_without_retry_after_field_is_none(self) -> None:
        session = _FakeSession(_FakeResponse(429, text="slow down"))
        client = _build(session)
        with self.assertRaises(RateLimitError) as cm:
            client.get_issue("ALF-1", fields=("summary",))
        self.assertIsNone(cm.exception.retry_after_seconds)

    def test_429_with_bogus_retry_after_field_is_none(self) -> None:
        session = _FakeSession(
            _FakeResponse(429, text="slow down", headers={"Retry-After": "soon"})
        )
        client = _build(session)
        with self.assertRaises(RateLimitError) as cm:
            client.get_issue("ALF-1", fields=("summary",))
        self.assertIsNone(cm.exception.retry_after_seconds)

    def test_timeout_raises_adapter_error(self) -> None:
        session = _FakeSession(requests.Timeout("read timed out"))
        client = _build(session)
        with self.assertRaises(AdapterError):
            client.get_issue("ALF-1", fields=("summary",))

    def test_connection_error_raises_adapter_error(self) -> None:
        session = _FakeSession(requests.ConnectionError("dns down"))
        client = _build(session)
        with self.assertRaises(AdapterError):
            client.get_issue("ALF-1", fields=("summary",))

    def test_non_json_body_raises_adapter_error(self) -> None:
        session = _FakeSession(_FakeResponse(200, raise_on_json=True))
        client = _build(session)
        with self.assertRaises(AdapterError):
            client.get_issue("ALF-1", fields=("summary",))

    def test_non_object_json_raises_adapter_error(self) -> None:
        session = _FakeSession(_FakeResponse(200, json_body=["array", "not", "obj"]))
        client = _build(session)
        with self.assertRaises(AdapterError):
            client.get_issue("ALF-1", fields=("summary",))


class TestSearchIssuesJql(unittest.TestCase):
    def test_happy_path_posts_correct_body(self) -> None:
        body = {"isLast": True, "issues": []}
        session = _FakeSession(_FakeResponse(200, json_body=body))
        client = _build(session)

        result = client.search_issues_jql(
            jql='text ~ "x" ORDER BY updated DESC',
            fields=("summary", "status"),
            limit=25,
        )

        self.assertEqual(result, body)
        assert session.last_post_args is not None
        self.assertEqual(
            session.last_post_args["url"],
            "https://acme.atlassian.net/rest/api/3/search/jql",
        )
        self.assertEqual(
            session.last_post_args["json"],
            {
                "jql": 'text ~ "x" ORDER BY updated DESC',
                "fields": ["summary", "status"],
                "maxResults": 25,
            },
        )
        self.assertEqual(
            session.last_post_args["headers"]["Content-Type"], "application/json"
        )

    def test_truncation_warning_when_next_page_token_present(self) -> None:
        body = {"isLast": False, "nextPageToken": "tok", "issues": []}
        session = _FakeSession(_FakeResponse(200, json_body=body))
        client = _build(session)

        with self.assertLogs(
            "mcp_server.adapters.jira.jira_cloud_http_client", level=logging.WARNING
        ) as cm:
            client.search_issues_jql(jql="x", fields=("summary",), limit=10)
        self.assertTrue(
            any("nextPageToken" in line or "truncated" in line for line in cm.output)
        )

    def test_no_warning_when_no_next_page_token(self) -> None:
        body = {"isLast": True, "issues": []}
        session = _FakeSession(_FakeResponse(200, json_body=body))
        client = _build(session)

        # assertNoLogs is 3.10+; use a try/except pattern compatible with assertLogs.
        logger = logging.getLogger(
            "mcp_server.adapters.jira.jira_cloud_http_client"
        )
        with self.assertLogs(logger, level=logging.DEBUG) as cm:
            logger.debug("baseline log to satisfy assertLogs")
            client.search_issues_jql(jql="x", fields=("summary",), limit=10)
        self.assertFalse(any("WARNING" in line for line in cm.output))

    def test_404_on_search_is_adapter_error_not_item_not_found(self) -> None:
        session = _FakeSession(_FakeResponse(404, text="missing"))
        client = _build(session)
        with self.assertRaises(AdapterError) as cm:
            client.search_issues_jql(jql="x", fields=("summary",), limit=10)
        self.assertNotIsInstance(cm.exception, ItemNotFoundError)

    def test_429_on_search_raises_rate_limit_error(self) -> None:
        session = _FakeSession(
            _FakeResponse(429, headers={"Retry-After": "5"})
        )
        client = _build(session)
        with self.assertRaises(RateLimitError) as cm:
            client.search_issues_jql(jql="x", fields=("summary",), limit=10)
        self.assertEqual(cm.exception.retry_after_seconds, 5)


class TestSessionAutoCreate(unittest.TestCase):
    def test_default_session_is_created_when_none_passed(self) -> None:
        with patch("mcp_server.adapters.jira.jira_cloud_http_client.requests.Session") as mock_session:
            JiraCloudHttpClient(_config(), _auth())
            mock_session.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
