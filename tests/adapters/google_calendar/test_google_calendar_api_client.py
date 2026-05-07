from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Any

from googleapiclient.errors import HttpError

from mcp_server.adapters.google_calendar.google_calendar_api_client import (
    GoogleCalendarApiClient,
)
from mcp_server.core.errors import (
    AdapterError,
    AuthError,
    ItemNotFoundError,
    RateLimitError,
)


class _FakeHttplibResp(dict):  # type: ignore[type-arg]
    """Mimics httplib2.Response: dict of headers + a `status` attribute."""

    def __init__(self, status: int, headers: dict[str, str] | None = None) -> None:
        super().__init__(headers or {})
        self.status = status
        self.reason = "Test"


def _http_error(status: int, headers: dict[str, str] | None = None) -> HttpError:
    return HttpError(_FakeHttplibResp(status, headers), b'{"error":"x"}')


class _FakeEventsRequest:
    def __init__(self, response: Any) -> None:
        self._response = response

    def execute(self) -> Any:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _FakeEventsResource:
    def __init__(self) -> None:
        self.list_response: Any = None
        self.get_response: Any = None
        self.last_list_kwargs: dict[str, Any] | None = None
        self.last_get_kwargs: dict[str, Any] | None = None

    def list(self, **kwargs: Any) -> _FakeEventsRequest:
        self.last_list_kwargs = dict(kwargs)
        return _FakeEventsRequest(self.list_response)

    def get(self, **kwargs: Any) -> _FakeEventsRequest:
        self.last_get_kwargs = dict(kwargs)
        return _FakeEventsRequest(self.get_response)


class _FakeService:
    def __init__(self) -> None:
        self._events = _FakeEventsResource()

    def events(self) -> _FakeEventsResource:
        return self._events


class TestListEvents(unittest.TestCase):
    def setUp(self) -> None:
        self.service = _FakeService()
        self.client = GoogleCalendarApiClient(self.service)

    def test_happy_path_returns_body_and_passes_default_params(self) -> None:
        body = {"items": [{"id": "evt1"}]}
        self.service._events.list_response = body

        result = self.client.list_events(max_results=20)

        self.assertEqual(result, body)
        kwargs = self.service._events.last_list_kwargs
        assert kwargs is not None
        self.assertEqual(kwargs["calendarId"], "primary")
        self.assertEqual(kwargs["maxResults"], 20)
        self.assertEqual(kwargs["singleEvents"], True)
        self.assertEqual(kwargs["orderBy"], "startTime")

    def test_passes_time_min_and_max_as_iso_strings(self) -> None:
        self.service._events.list_response = {"items": []}
        when_min = datetime(2026, 5, 5, 9, 0, tzinfo=timezone.utc)
        when_max = datetime(2026, 5, 5, 17, 0, tzinfo=timezone.utc)

        self.client.list_events(
            time_min=when_min, time_max=when_max, max_results=10
        )

        kwargs = self.service._events.last_list_kwargs
        assert kwargs is not None
        self.assertEqual(kwargs["timeMin"], when_min.isoformat())
        self.assertEqual(kwargs["timeMax"], when_max.isoformat())

    def test_passes_q_when_provided(self) -> None:
        self.service._events.list_response = {"items": []}
        self.client.list_events(q="standup", max_results=10)
        kwargs = self.service._events.last_list_kwargs
        assert kwargs is not None
        self.assertEqual(kwargs["q"], "standup")

    def test_passes_updated_min_when_provided(self) -> None:
        self.service._events.list_response = {"items": []}
        when = datetime(2026, 5, 5, tzinfo=timezone.utc)
        self.client.list_events(updated_min=when, max_results=10)
        kwargs = self.service._events.last_list_kwargs
        assert kwargs is not None
        self.assertEqual(kwargs["updatedMin"], when.isoformat())

    def test_omits_optional_params_when_not_provided(self) -> None:
        self.service._events.list_response = {"items": []}
        self.client.list_events(max_results=5)
        kwargs = self.service._events.last_list_kwargs
        assert kwargs is not None
        self.assertNotIn("timeMin", kwargs)
        self.assertNotIn("timeMax", kwargs)
        self.assertNotIn("q", kwargs)
        self.assertNotIn("updatedMin", kwargs)

    def test_404_on_search_is_adapter_error_not_item_not_found(self) -> None:
        self.service._events.list_response = _http_error(404)
        with self.assertRaises(AdapterError) as cm:
            self.client.list_events(max_results=5)
        self.assertNotIsInstance(cm.exception, ItemNotFoundError)

    def test_401_raises_auth_error(self) -> None:
        self.service._events.list_response = _http_error(401)
        with self.assertRaises(AuthError):
            self.client.list_events(max_results=5)

    def test_403_raises_auth_error(self) -> None:
        self.service._events.list_response = _http_error(403)
        with self.assertRaises(AuthError):
            self.client.list_events(max_results=5)

    def test_429_with_retry_after_populates_field(self) -> None:
        self.service._events.list_response = _http_error(
            429, {"retry-after": "30"}
        )
        with self.assertRaises(RateLimitError) as cm:
            self.client.list_events(max_results=5)
        self.assertEqual(cm.exception.retry_after_seconds, 30)

    def test_429_without_retry_after_field_is_none(self) -> None:
        self.service._events.list_response = _http_error(429)
        with self.assertRaises(RateLimitError) as cm:
            self.client.list_events(max_results=5)
        self.assertIsNone(cm.exception.retry_after_seconds)

    def test_500_raises_adapter_error(self) -> None:
        self.service._events.list_response = _http_error(500)
        with self.assertRaises(AdapterError):
            self.client.list_events(max_results=5)


class TestGetEvent(unittest.TestCase):
    def setUp(self) -> None:
        self.service = _FakeService()
        self.client = GoogleCalendarApiClient(self.service)

    def test_happy_path_returns_body(self) -> None:
        body = {"id": "evt_abc", "summary": "x"}
        self.service._events.get_response = body

        result = self.client.get_event("evt_abc")

        self.assertEqual(result, body)
        kwargs = self.service._events.last_get_kwargs
        assert kwargs is not None
        self.assertEqual(kwargs["calendarId"], "primary")
        self.assertEqual(kwargs["eventId"], "evt_abc")

    def test_404_raises_item_not_found(self) -> None:
        self.service._events.get_response = _http_error(404)
        with self.assertRaises(ItemNotFoundError):
            self.client.get_event("missing-evt")

    def test_401_raises_auth_error(self) -> None:
        self.service._events.get_response = _http_error(401)
        with self.assertRaises(AuthError):
            self.client.get_event("evt_abc")

    def test_429_raises_rate_limit_error(self) -> None:
        self.service._events.get_response = _http_error(
            429, {"retry-after": "5"}
        )
        with self.assertRaises(RateLimitError) as cm:
            self.client.get_event("evt_abc")
        self.assertEqual(cm.exception.retry_after_seconds, 5)


if __name__ == "__main__":
    unittest.main()
