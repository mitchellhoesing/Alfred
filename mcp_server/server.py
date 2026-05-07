"""FastMCP wiring for Alfred.

Boot sequence:

1. Load ``.env`` via :func:`dotenv.load_dotenv` so adapter factories can
   read their config from ``os.environ``.
2. :func:`build_registry` calls each source-specific adapter factory and
   registers the result on a shared :class:`AdapterRegistry`. Adapters
   whose env-var config is incomplete are skipped with a warning so a
   user can run Alfred with any subset of {Jira, Calendar, Gmail}; only
   if **zero** adapters could be built do we raise
   :class:`ConfigurationError`.
3. :func:`register_tools` exposes the seven MCP tools — three generic
   fan-out tools backed by :class:`CrossSourceAggregator` and four
   source-specific escape hatches keyed off the registry.
4. :func:`run` runs the FastMCP server on stdio (the only transport we
   need for Claude Code).

The boot logic is split into small, injectable functions so each piece
is unit-testable without standing up an MCP server. ``run`` itself is a
thin shell that orchestrates the pieces.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Mapping

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from mcp_server.adapters.gmail.gmail_adapter_factory import build_gmail_adapter
from mcp_server.adapters.google_calendar.google_calendar_adapter_factory import (
    build_google_calendar_adapter,
)
from mcp_server.adapters.jira.jira_adapter_factory import build_jira_adapter
from mcp_server.core.aggregator import CrossSourceAggregator
from mcp_server.core.errors import ConfigurationError
from mcp_server.core.registry import AdapterRegistry
from mcp_server.tools import generic as tools_generic
from mcp_server.tools import specific as tools_specific


_log = logging.getLogger(__name__)


def build_registry(
    env: Mapping[str, str],
    *,
    token_path: Path | None = None,
) -> AdapterRegistry:
    """Try every adapter factory; register what builds, skip what doesn't.

    Each :class:`ConfigurationError` is logged and swallowed so a user
    with only some sources configured can still run Alfred. If **all**
    factories fail, the function raises :class:`ConfigurationError` —
    a server with no adapters has nothing to do.
    """
    registry = AdapterRegistry()
    factories: tuple[tuple[str, Any], ...] = (
        ("jira", lambda: build_jira_adapter(env)),
        (
            "google_calendar",
            lambda: build_google_calendar_adapter(env, token_path=token_path),
        ),
        ("gmail", lambda: build_gmail_adapter(env, token_path=token_path)),
    )
    for source_name, build_fn in factories:
        try:
            registry.register(build_fn())
        except ConfigurationError as exc:
            _log.warning("skipping %s adapter: %s", source_name, exc)
    if len(registry) == 0:
        raise ConfigurationError(
            "No source adapters could be built. Check your .env file."
        )
    return registry


def register_tools(mcp: FastMCP, registry: AdapterRegistry) -> None:
    """Register the seven Alfred MCP tools on *mcp*, bound to *registry*.

    Generic tools share a single :class:`CrossSourceAggregator`;
    specific tools take the registry directly so they can resolve their
    concrete adapter by source name.
    """
    aggregator = CrossSourceAggregator(registry)

    @mcp.tool()
    async def alfred_search(
        query: str,
        sources: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Free-text search across all (or specified) Alfred sources."""
        return await tools_generic.alfred_search(
            aggregator, query=query, sources=sources, limit=limit
        )

    @mcp.tool()
    async def alfred_list_recent(
        since: str,
        sources: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List items modified-or-created on/after the ISO timestamp ``since``."""
        return await tools_generic.alfred_list_recent(
            aggregator, since=since, sources=sources, limit=limit
        )

    @mcp.tool()
    async def alfred_get(source: str, item_id: str) -> dict[str, Any]:
        """Fetch a single item by its source-native id."""
        return await tools_generic.alfred_get(
            aggregator, source=source, item_id=item_id
        )

    @mcp.tool()
    async def calendar_list_events_in_range(
        time_min: str,
        time_max: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List calendar events whose start falls in [time_min, time_max] (ISO 8601)."""
        return await tools_specific.calendar_list_events_in_range(
            registry, time_min=time_min, time_max=time_max, limit=limit
        )

    @mcp.tool()
    async def calendar_find_free_slot(
        duration_minutes: int,
        within_days: int,
    ) -> str | None:
        """Find the first free calendar slot of *duration_minutes* within *within_days*."""
        return await tools_specific.calendar_find_free_slot(
            registry,
            duration_minutes=duration_minutes,
            within_days=within_days,
        )

    @mcp.tool()
    async def gmail_get_thread(thread_id: str) -> list[dict[str, Any]]:
        """Return every Gmail message in *thread_id*, oldest first."""
        return await tools_specific.gmail_get_thread(
            registry, thread_id=thread_id
        )

    @mcp.tool()
    async def jira_search_jql(
        jql: str, limit: int = 25
    ) -> list[dict[str, Any]]:
        """Run a caller-supplied JQL query against Jira and return tickets."""
        return await tools_specific.jira_search_jql(
            registry, jql=jql, limit=limit
        )


def build_server(
    env: Mapping[str, str],
    *,
    token_path: Path | None = None,
) -> FastMCP:
    """Compose a fully-wired :class:`FastMCP` for *env*.

    Separated from :func:`run` so tests (and any future programmatic
    embedding) can build the server without invoking the stdio loop.
    """
    registry = build_registry(env, token_path=token_path)
    mcp: FastMCP = FastMCP("Alfred")
    register_tools(mcp, registry)
    return mcp


def run() -> None:
    """Entry point: load ``.env``, build the server, run on stdio."""
    logging.basicConfig(level=logging.INFO)
    load_dotenv()
    mcp = build_server(dict(os.environ))
    mcp.run()
