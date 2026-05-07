"""In-process registry of SourceAdapter instances.

The MCP server populates this at startup; the CrossSourceAggregator and the
tools layer both depend on it (DIP — they take an AdapterRegistry, not the
concrete adapters).
"""

from __future__ import annotations

from typing import Iterable

from mcp_server.core.source_adapter import SourceAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, SourceAdapter] = {}

    def register(self, adapter: SourceAdapter) -> None:
        name = adapter.capabilities.source_name
        if name in self._adapters:
            raise ValueError(f"Adapter '{name}' is already registered")
        self._adapters[name] = adapter

    def get(self, source_name: str) -> SourceAdapter:
        try:
            return self._adapters[source_name]
        except KeyError as exc:
            raise KeyError(f"No adapter registered for source '{source_name}'") from exc

    def all(self) -> Iterable[SourceAdapter]:
        return tuple(self._adapters.values())

    def names(self) -> tuple[str, ...]:
        return tuple(self._adapters.keys())

    def __contains__(self, source_name: object) -> bool:
        return isinstance(source_name, str) and source_name in self._adapters

    def __len__(self) -> int:
        return len(self._adapters)
