from __future__ import annotations

import unittest
from typing import Any

from googleapiclient.errors import HttpError

from mcp_server.adapters.gmail.gmail_api_client import GmailApiClient
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


class _FakeApiRequest:
    def __init__(self, response: Any) -> None:
        self._response = response

    def execute(self) -> Any:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _FakeMessagesResource:
    def __init__(self) -> None:
        self.list_response: Any = None
        self.get_response: Any = None
        self.last_list_kwargs: dict[str, Any] | None = None
        self.last_get_kwargs: dict[str, Any] | None = None

    def list(self, **kwargs: Any) -> _FakeApiRequest:
        self.last_list_kwargs = dict(kwargs)
        return _FakeApiRequest(self.list_response)

    def get(self, **kwargs: Any) -> _FakeApiRequest:
        self.last_get_kwargs = dict(kwargs)
        return _FakeApiRequest(self.get_response)


class _FakeThreadsResource:
    def __init__(self) -> None:
        self.get_response: Any = None
        self.last_get_kwargs: dict[str, Any] | None = None

    def get(self, **kwargs: Any) -> _FakeApiRequest:
        self.last_get_kwargs = dict(kwargs)
        return _FakeApiRequest(self.get_response)


class _FakeUsersResource:
    def __init__(self) -> None:
        self._messages = _FakeMessagesResource()
        self._threads = _FakeThreadsResource()

    def messages(self) -> _FakeMessagesResource:
        return self._messages

    def threads(self) -> _FakeThreadsResource:
        return self._threads


class _FakeService:
    def __init__(self) -> None:
        self._users = _FakeUsersResource()

    def users(self) -> _FakeUsersResource:
        return self._users


class TestListMessages(unittest.TestCase):
    def setUp(self) -> None:
        self.service = _FakeService()
        self.client = GmailApiClient(self.service)
        self.messages = self.service._users._messages

    def test_happy_path_returns_body_and_passes_default_params(self) -> None:
        body = {"messages": [{"id": "m1", "threadId": "t1"}]}
        self.messages.list_response = body

        result = self.client.list_messages(max_results=20)

        self.assertEqual(result, body)
        kwargs = self.messages.last_list_kwargs
        assert kwargs is not None
        self.assertEqual(kwargs["userId"], "me")
        self.assertEqual(kwargs["maxResults"], 20)

    def test_passes_q_when_provided(self) -> None:
        self.messages.list_response = {"resultSizeEstimate": 0}
        self.client.list_messages(q="from:alice", max_results=10)
        kwargs = self.messages.last_list_kwargs
        assert kwargs is not None
        self.assertEqual(kwargs["q"], "from:alice")

    def test_passes_label_ids_when_provided(self) -> None:
        self.messages.list_response = {"resultSizeEstimate": 0}
        self.client.list_messages(label_ids=("INBOX", "UNREAD"), max_results=10)
        kwargs = self.messages.last_list_kwargs
        assert kwargs is not None
        self.assertEqual(list(kwargs["labelIds"]), ["INBOX", "UNREAD"])

    def test_omits_optional_params_when_not_provided(self) -> None:
        self.messages.list_response = {"resultSizeEstimate": 0}
        self.client.list_messages(max_results=5)
        kwargs = self.messages.last_list_kwargs
        assert kwargs is not None
        self.assertNotIn("q", kwargs)
        self.assertNotIn("labelIds", kwargs)

    def test_404_on_list_is_adapter_error_not_item_not_found(self) -> None:
        self.messages.list_response = _http_error(404)
        with self.assertRaises(AdapterError) as cm:
            self.client.list_messages(max_results=5)
        self.assertNotIsInstance(cm.exception, ItemNotFoundError)

    def test_401_raises_auth_error(self) -> None:
        self.messages.list_response = _http_error(401)
        with self.assertRaises(AuthError):
            self.client.list_messages(max_results=5)

    def test_403_raises_auth_error(self) -> None:
        self.messages.list_response = _http_error(403)
        with self.assertRaises(AuthError):
            self.client.list_messages(max_results=5)

    def test_429_with_retry_after_populates_field(self) -> None:
        self.messages.list_response = _http_error(429, {"retry-after": "30"})
        with self.assertRaises(RateLimitError) as cm:
            self.client.list_messages(max_results=5)
        self.assertEqual(cm.exception.retry_after_seconds, 30)

    def test_429_without_retry_after_field_is_none(self) -> None:
        self.messages.list_response = _http_error(429)
        with self.assertRaises(RateLimitError) as cm:
            self.client.list_messages(max_results=5)
        self.assertIsNone(cm.exception.retry_after_seconds)

    def test_500_raises_adapter_error(self) -> None:
        self.messages.list_response = _http_error(500)
        with self.assertRaises(AdapterError):
            self.client.list_messages(max_results=5)


class TestGetMessage(unittest.TestCase):
    def setUp(self) -> None:
        self.service = _FakeService()
        self.client = GmailApiClient(self.service)
        self.messages = self.service._users._messages

    def test_happy_path_returns_body_with_default_metadata_format(self) -> None:
        body = {"id": "msg_abc", "threadId": "thr_zzz"}
        self.messages.get_response = body

        result = self.client.get_message("msg_abc")

        self.assertEqual(result, body)
        kwargs = self.messages.last_get_kwargs
        assert kwargs is not None
        self.assertEqual(kwargs["userId"], "me")
        self.assertEqual(kwargs["id"], "msg_abc")
        self.assertEqual(kwargs["format"], "metadata")
        self.assertEqual(
            list(kwargs["metadataHeaders"]),
            ["Subject", "From", "To", "Date"],
        )

    def test_custom_format_overrides_default(self) -> None:
        self.messages.get_response = {"id": "x", "threadId": "t"}
        self.client.get_message("x", format="full")
        kwargs = self.messages.last_get_kwargs
        assert kwargs is not None
        self.assertEqual(kwargs["format"], "full")

    def test_custom_metadata_headers_pass_through(self) -> None:
        self.messages.get_response = {"id": "x", "threadId": "t"}
        self.client.get_message(
            "x", metadata_headers=("Subject", "Reply-To")
        )
        kwargs = self.messages.last_get_kwargs
        assert kwargs is not None
        self.assertEqual(
            list(kwargs["metadataHeaders"]), ["Subject", "Reply-To"]
        )

    def test_404_raises_item_not_found(self) -> None:
        self.messages.get_response = _http_error(404)
        with self.assertRaises(ItemNotFoundError):
            self.client.get_message("missing-msg")

    def test_401_raises_auth_error(self) -> None:
        self.messages.get_response = _http_error(401)
        with self.assertRaises(AuthError):
            self.client.get_message("msg_abc")

    def test_429_raises_rate_limit_error(self) -> None:
        self.messages.get_response = _http_error(429, {"retry-after": "5"})
        with self.assertRaises(RateLimitError) as cm:
            self.client.get_message("msg_abc")
        self.assertEqual(cm.exception.retry_after_seconds, 5)


class TestGetThread(unittest.TestCase):
    def setUp(self) -> None:
        self.service = _FakeService()
        self.client = GmailApiClient(self.service)
        self.threads = self.service._users._threads

    def test_happy_path_passes_thread_id_and_default_metadata_format(
        self,
    ) -> None:
        body = {"id": "thr_abc", "messages": []}
        self.threads.get_response = body

        result = self.client.get_thread("thr_abc")

        self.assertEqual(result, body)
        kwargs = self.threads.last_get_kwargs
        assert kwargs is not None
        self.assertEqual(kwargs["userId"], "me")
        self.assertEqual(kwargs["id"], "thr_abc")
        self.assertEqual(kwargs["format"], "metadata")
        self.assertEqual(
            list(kwargs["metadataHeaders"]),
            ["Subject", "From", "To", "Date"],
        )

    def test_404_raises_item_not_found(self) -> None:
        self.threads.get_response = _http_error(404)
        with self.assertRaises(ItemNotFoundError):
            self.client.get_thread("missing-thr")

    def test_401_raises_auth_error(self) -> None:
        self.threads.get_response = _http_error(401)
        with self.assertRaises(AuthError):
            self.client.get_thread("thr_abc")

    def test_429_raises_rate_limit_error(self) -> None:
        self.threads.get_response = _http_error(429, {"retry-after": "7"})
        with self.assertRaises(RateLimitError) as cm:
            self.client.get_thread("thr_abc")
        self.assertEqual(cm.exception.retry_after_seconds, 7)


if __name__ == "__main__":
    unittest.main()
