from __future__ import annotations

import unittest
from datetime import datetime
from typing import Sequence

from mcp_server.core.canonical import SearchHit, SourceItem
from mcp_server.core.registry import AdapterRegistry
from mcp_server.core.source_adapter import AdapterCapabilities, SourceAdapter


class _FakeAdapter(SourceAdapter):
    def __init__(self, name: str) -> None:
        self._caps = AdapterCapabilities(name, True, True, False)

    @property
    def capabilities(self) -> AdapterCapabilities:
        return self._caps

    async def list_recent(self, *, since: datetime, limit: int) -> Sequence[SourceItem]:
        return ()

    async def get(self, item_id: str) -> SourceItem:
        raise KeyError(item_id)

    async def search(self, query: str, *, limit: int) -> Sequence[SearchHit]:
        return ()


class TestAdapterRegistry(unittest.TestCase):
    def test_register_and_get(self) -> None:
        r = AdapterRegistry()
        a = _FakeAdapter("foo")
        r.register(a)
        self.assertIs(r.get("foo"), a)

    def test_register_duplicate_raises(self) -> None:
        r = AdapterRegistry()
        r.register(_FakeAdapter("foo"))
        with self.assertRaises(ValueError):
            r.register(_FakeAdapter("foo"))

    def test_get_unknown_raises_keyerror(self) -> None:
        r = AdapterRegistry()
        with self.assertRaises(KeyError):
            r.get("nonexistent")

    def test_all_and_names(self) -> None:
        r = AdapterRegistry()
        r.register(_FakeAdapter("a"))
        r.register(_FakeAdapter("b"))
        self.assertEqual(set(r.names()), {"a", "b"})
        self.assertEqual(len(tuple(r.all())), 2)

    def test_contains(self) -> None:
        r = AdapterRegistry()
        r.register(_FakeAdapter("foo"))
        self.assertIn("foo", r)
        self.assertNotIn("bar", r)

    def test_len(self) -> None:
        r = AdapterRegistry()
        self.assertEqual(len(r), 0)
        r.register(_FakeAdapter("a"))
        self.assertEqual(len(r), 1)


if __name__ == "__main__":
    unittest.main()
