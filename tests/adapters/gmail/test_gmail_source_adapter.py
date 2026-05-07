from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from mcp_server.adapters.gmail.gmail_source_adapter import GmailSourceAdapter
from mcp_server.core.canonical import Message, SearchHit
from mcp_server.core.errors import ItemNotFoundError
from mcp_server.core.registry import AdapterRegistry


_FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


class _FakeGmailApiClient:
    """Records calls and replays canned responses or raises canned exceptions."""

    def __init__(self) -> None:
        self.list_response: Mapping[str, Any] | Exception | None = None
        self.get_response_by_id: dict[str, Mapping[str, Any] | Exception] = {}
        self.get_default_response: Mapping[str, Any] | Exception | None = None
        self.thread_response_by_id: dict[
            str, Mapping[str, Any] | Exception
        ] = {}
        self.last_list_kwargs: dict[str, Any] | None = None
        self.get_calls: list[str] = []
        self.thread_calls: list[str] = []

    def list_messages(self, **kwargs: Any) -> Mapping[str, Any]:
        self.last_list_kwargs = dict(kwargs)
        if self.list_response is None:
            raise AssertionError("list_response not configured in fake")
        if isinstance(self.list_response, Exception):
            raise self.list_response
        return self.list_response

    def get_message(self, message_id: str, **kwargs: Any) -> Mapping[str, Any]:
        self.get_calls.append(message_id)
        if message_id in self.get_response_by_id:
            resp = self.get_response_by_id[message_id]
        elif self.get_default_response is not None:
            resp = self.get_default_response
        else:
            raise AssertionError(
                f"no get_response configured for {message_id}"
            )
        if isinstance(resp, Exception):
            raise resp
        return resp

    def get_thread(self, thread_id: str, **kwargs: Any) -> Mapping[str, Any]:
        self.thread_calls.append(thread_id)
        if thread_id not in self.thread_response_by_id:
            raise AssertionError(
                f"no thread_response configured for {thread_id}"
            )
        resp = self.thread_response_by_id[thread_id]
        if isinstance(resp, Exception):
            raise resp
        return resp


def _adapter(fake: _FakeGmailApiClient) -> GmailSourceAdapter:
    return GmailSourceAdapter(fake)  # type: ignore[arg-type]


class TestCapabilities(unittest.TestCase):
    def test_capabilities_values(self) -> None:
        caps = _adapter(_FakeGmailApiClient()).capabilities
        self.assertEqual(caps.source_name, "gmail")
        self.assertTrue(caps.supports_search)
        self.assertTrue(caps.supports_time_range)
        self.assertTrue(caps.supports_threading)


class TestGet(unittest.IsolatedAsyncioTestCase):
    async def test_get_returns_message(self) -> None:
        fake = _FakeGmailApiClient()
        fake.get_response_by_id["msg_abc123"] = _load("message_full.json")

        message = await _adapter(fake).get("msg_abc123")

        self.assertIsInstance(message, Message)
        self.assertEqual(message.id, "msg_abc123")
        self.assertEqual(fake.get_calls, ["msg_abc123"])

    async def test_get_propagates_item_not_found(self) -> None:
        fake = _FakeGmailApiClient()
        fake.get_response_by_id["missing-msg"] = ItemNotFoundError(
            "missing-msg"
        )
        with self.assertRaises(ItemNotFoundError):
            await _adapter(fake).get("missing-msg")


class TestListRecent(unittest.IsolatedAsyncioTestCase):
    async def test_list_recent_uses_after_query(self) -> None:
        fake = _FakeGmailApiClient()
        fake.list_response = _load("messages_list.json")
        fake.get_response_by_id["msg_abc123"] = _load("message_full.json")
        fake.get_response_by_id["msg_def456"] = _load("message_read.json")

        since = datetime(2026, 5, 5, 0, 0, tzinfo=timezone.utc)
        await _adapter(fake).list_recent(since=since, limit=10)

        kwargs = fake.last_list_kwargs
        assert kwargs is not None
        self.assertEqual(kwargs["q"], "after:2026/05/05")
        self.assertEqual(kwargs["max_results"], 10)

    async def test_list_recent_fans_out_get_for_each_id_in_order(
        self,
    ) -> None:
        fake = _FakeGmailApiClient()
        fake.list_response = _load("messages_list.json")
        fake.get_response_by_id["msg_abc123"] = _load("message_full.json")
        fake.get_response_by_id["msg_def456"] = _load("message_read.json")

        messages = await _adapter(fake).list_recent(
            since=datetime(2026, 5, 5, tzinfo=timezone.utc), limit=10
        )

        self.assertEqual(len(messages), 2)
        self.assertTrue(all(isinstance(m, Message) for m in messages))
        self.assertEqual(messages[0].id, "msg_abc123")
        self.assertEqual(messages[1].id, "msg_def456")
        self.assertEqual(fake.get_calls, ["msg_abc123", "msg_def456"])

    async def test_list_recent_empty_results(self) -> None:
        fake = _FakeGmailApiClient()
        fake.list_response = _load("messages_list_empty.json")

        messages = await _adapter(fake).list_recent(
            since=datetime(2026, 5, 5, tzinfo=timezone.utc), limit=10
        )
        self.assertEqual(messages, ())
        self.assertEqual(fake.get_calls, [])


class TestSearch(unittest.IsolatedAsyncioTestCase):
    async def test_search_passes_query_as_q(self) -> None:
        fake = _FakeGmailApiClient()
        fake.list_response = _load("messages_list.json")
        fake.get_response_by_id["msg_abc123"] = _load("message_full.json")
        fake.get_response_by_id["msg_def456"] = _load("message_read.json")

        await _adapter(fake).search("from:alice", limit=5)

        kwargs = fake.last_list_kwargs
        assert kwargs is not None
        self.assertEqual(kwargs["q"], "from:alice")
        self.assertEqual(kwargs["max_results"], 5)

    async def test_search_returns_search_hits_in_order(self) -> None:
        fake = _FakeGmailApiClient()
        fake.list_response = _load("messages_list.json")
        fake.get_response_by_id["msg_abc123"] = _load("message_full.json")
        fake.get_response_by_id["msg_def456"] = _load("message_read.json")

        hits = await _adapter(fake).search("planning", limit=5)

        self.assertEqual(len(hits), 2)
        self.assertTrue(all(isinstance(h, SearchHit) for h in hits))
        self.assertEqual(hits[0].source, "gmail")
        self.assertEqual(hits[0].item_id, "msg_abc123")
        self.assertEqual(hits[1].item_id, "msg_def456")

    async def test_search_empty_results(self) -> None:
        fake = _FakeGmailApiClient()
        fake.list_response = _load("messages_list_empty.json")
        hits = await _adapter(fake).search("nope", limit=5)
        self.assertEqual(hits, ())
        self.assertEqual(fake.get_calls, [])


class TestGetThread(unittest.IsolatedAsyncioTestCase):
    async def test_returns_messages_in_order_from_thread(self) -> None:
        fake = _FakeGmailApiClient()
        fake.thread_response_by_id["thr_zzz"] = _load("thread_full.json")

        messages = await _adapter(fake).get_thread("thr_zzz")

        self.assertEqual(len(messages), 2)
        self.assertTrue(all(isinstance(m, Message) for m in messages))
        self.assertEqual(messages[0].id, "msg_abc123")
        self.assertEqual(messages[1].id, "msg_xyz789")
        # Both messages should carry the same thread_id from the fixture
        self.assertEqual(messages[0].thread_id, "thr_zzz")
        self.assertEqual(messages[1].thread_id, "thr_zzz")
        self.assertEqual(fake.thread_calls, ["thr_zzz"])

    async def test_empty_thread_returns_empty_tuple(self) -> None:
        fake = _FakeGmailApiClient()
        fake.thread_response_by_id["thr_empty"] = _load("thread_empty.json")
        messages = await _adapter(fake).get_thread("thr_empty")
        self.assertEqual(messages, ())

    async def test_propagates_item_not_found(self) -> None:
        fake = _FakeGmailApiClient()
        fake.thread_response_by_id["missing-thr"] = ItemNotFoundError(
            "missing-thr"
        )
        with self.assertRaises(ItemNotFoundError):
            await _adapter(fake).get_thread("missing-thr")


class TestRegistryIntegration(unittest.TestCase):
    def test_registers_under_gmail_source_name(self) -> None:
        adapter = _adapter(_FakeGmailApiClient())
        registry = AdapterRegistry()
        registry.register(adapter)
        self.assertIn("gmail", registry)
        self.assertIs(registry.get("gmail"), adapter)


if __name__ == "__main__":
    unittest.main()
