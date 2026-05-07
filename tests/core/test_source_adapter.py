from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime
from typing import Sequence

from mcp_server.core.canonical import SearchHit, SourceItem
from mcp_server.core.source_adapter import AdapterCapabilities, SourceAdapter


class _IncompleteAdapter(SourceAdapter):
    """Deliberately omits the abstract methods — must not be instantiable."""

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities("x", True, True, True)


class _CompleteAdapter(SourceAdapter):
    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities("x", True, True, True)

    async def list_recent(self, *, since: datetime, limit: int) -> Sequence[SourceItem]:
        return ()

    async def get(self, item_id: str) -> SourceItem:
        raise KeyError(item_id)

    async def search(self, query: str, *, limit: int) -> Sequence[SearchHit]:
        return ()


class TestAdapterCapabilities(unittest.TestCase):
    def test_frozen(self) -> None:
        c = AdapterCapabilities(
            source_name="x",
            supports_search=True,
            supports_time_range=False,
            supports_threading=False,
        )
        with self.assertRaises(FrozenInstanceError):
            c.source_name = "y"  # type: ignore[misc]


class TestSourceAdapterContract(unittest.TestCase):
    def test_incomplete_subclass_cannot_instantiate(self) -> None:
        with self.assertRaises(TypeError):
            _IncompleteAdapter()  # type: ignore[abstract]

    def test_complete_subclass_instantiates(self) -> None:
        adapter = _CompleteAdapter()
        self.assertEqual(adapter.capabilities.source_name, "x")


if __name__ == "__main__":
    unittest.main()
