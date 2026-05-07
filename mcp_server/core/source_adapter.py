"""The SourceAdapter contract — every data-source plugin implements this ABC.

Keep the interface intentionally small (ISP). Source-specific operations that
do not generalize (Jira's JQL search, Calendar's free-slot finder, Gmail's
thread fetch) live as methods on the concrete adapter and are exposed through
``mcp_server.tools.specific``, not through this base class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from mcp_server.core.canonical import SearchHit, SourceItem


@dataclass(frozen=True)
class AdapterCapabilities:
    """Describes what an adapter supports. Used by tools/the model to decide
    whether a fan-out call is meaningful for a given source."""

    source_name: str
    supports_search: bool
    supports_time_range: bool
    supports_threading: bool


class SourceAdapter(ABC):
    """Contract every data-source adapter must satisfy."""

    @property
    @abstractmethod
    def capabilities(self) -> AdapterCapabilities: ...

    @abstractmethod
    async def list_recent(
        self, *, since: datetime, limit: int
    ) -> Sequence[SourceItem]:
        """Return canonical items modified-or-created on/after ``since``."""

    @abstractmethod
    async def get(self, item_id: str) -> SourceItem:
        """Return a single canonical item by its source-native id.

        Raises :class:`mcp_server.core.errors.ItemNotFoundError` when missing.
        """

    @abstractmethod
    async def search(self, query: str, *, limit: int) -> Sequence[SearchHit]:
        """Return up to ``limit`` SearchHits matching ``query``."""
