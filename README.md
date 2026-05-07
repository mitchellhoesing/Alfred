# Alfred

Personal AI assistant. A Python MCP server bridging Claude Code to Google Calendar, Gmail, and Jira Cloud, plus four intent-driven Claude skills built on top.

Read-only across all sources in v1. Writes deferred to v2.

## Architecture

Single MCP server with a `SourceAdapter` ABC and intent-driven workflow skills. New data sources plug in by writing a new adapter — no changes to core or skills that use generic tools. Full design in [`.claude/plans/we-are-going-to-merry-orbit.md`](.claude/plans/we-are-going-to-merry-orbit.md).

## Prerequisites

- Python 3.11+ (development used 3.14)
- A Google Cloud project with OAuth client credentials (desktop app type)
- A Jira Cloud account and personal API token
- [Claude Code](https://claude.com/claude-code)

## Install

```
pip install -e .
```

## Configure

Copy `.env.example` to `.env` and fill in:

```
GOOGLE_CLIENT_ID=<from Google Cloud Console>
GOOGLE_CLIENT_SECRET=<from Google Cloud Console>
ALFRED_TOKEN_PASSPHRASE=<any strong string; rotates the token-file encryption key>

JIRA_BASE_URL=https://<your-instance>.atlassian.net
JIRA_EMAIL=<your atlassian email>
JIRA_API_TOKEN=<from id.atlassian.com/manage-profile/security/api-tokens>
```

Optional: `ALFRED_GOOGLE_TOKEN_PATH` overrides the default `~/.alfred/google_token.json` location for the encrypted refresh-token file.

### Google Cloud setup (once)

1. In the Google Cloud Console, create or select a project.
2. Enable the **Google Calendar API** and **Gmail API**.
3. Configure the OAuth consent screen as **External**, add your email under **Test users**, and request the scopes `.../auth/calendar.readonly` and `.../auth/gmail.readonly`.
4. Create an OAuth client ID of type **Desktop app**. Copy the client ID and client secret into `.env`.

### Jira API token (once)

Generate at https://id.atlassian.com/manage-profile/security/api-tokens. The token grants the same access as your Atlassian account; treat it like a password.

## Bootstrap Google OAuth

Run once before starting the server:

```
python -m mcp_server.adapters.google_common
```

This opens a browser, walks you through Google's consent screen, and writes an encrypted refresh-token file to `~/.alfred/google_token.json` (or `ALFRED_GOOGLE_TOKEN_PATH`). The MCP server itself never opens a browser; it only reads the cached file.

If the token expires (e.g., scopes changed), delete the file and rerun.

## Run the server

```
python -m mcp_server
```

The server speaks MCP over stdio, which is what Claude Code expects. There's no HTTP transport in v1.

If a source's env vars are missing or invalid, that adapter is **skipped with a warning** and the others still run. The server only refuses to start when *no* adapter could be built.

## Connect to Claude Code

Add Alfred to your project's `.mcp.json` (or `.claude/settings.json` under `mcpServers`):

```json
{
  "mcpServers": {
    "Alfred": {
      "command": "python",
      "args": ["-m", "mcp_server"]
    }
  }
}
```

Restart Claude Code. The seven Alfred tools should appear, and the four skills under `.claude/skills/` will be invocable as `/daily-brief`, `/follow-ups`, `/blockers`, `/schedule-around`.

## MCP tools

Generic (fan out across registered adapters):
- `alfred_search(query, sources?, limit=10)`
- `alfred_list_recent(since, sources?, limit=20)` — `since` is ISO 8601
- `alfred_get(source, item_id)`

Source-specific:
- `calendar_list_events_in_range(time_min, time_max, limit=50)`
- `calendar_find_free_slot(duration_minutes, within_days)`
- `gmail_get_thread(thread_id)`
- `jira_search_jql(jql, limit=25)`

## Skills

Four intent-driven skills live under `.claude/skills/` and compose the MCP tools above into common workflows. Invoke each by its slash command, or trigger it implicitly with one of the example phrases — Claude Code routes matching natural-language requests to the skill automatically.

- **`/daily-brief`** — Morning briefing: today's calendar, unread mail of substance, and active Jira tickets grouped by status.
  *Triggers:* "what's on my plate today?", "give me the morning briefing".
- **`/follow-ups`** — Threads and tickets where you're waiting on someone else: sent emails with no reply, plus tickets you reported but didn't get assigned.
  *Triggers:* "who am I waiting on?", "what's blocked on someone else?", "anything I'm chasing?".
- **`/blockers`** — Active blockers: Jira tickets in Blocked status (with stale-blocker callouts at ≥ 7 days) and calendar events flagged as blockers.
  *Triggers:* "what's blocking me?", "what's stuck?".
- **`/schedule-around`** — Find the first free calendar slot of a given duration in the next N days.
  *Triggers:* "find me time for X", "when can I fit a 30-min meeting?", "schedule around my calendar".

Each skill's full instructions live in its `SKILL.md`. To add a skill, drop a new directory under `.claude/skills/<name>/` containing a `SKILL.md` with `name` and `description` frontmatter — Claude Code picks it up on restart.

## Tests

```
python -m unittest discover
```

Tests are deterministic and offline — every external API call is mocked. There are no live integration tests in the default `unittest discover` set.

`mypy --strict mcp_server/` is the second gate per `.claude/CLAUDE.md`. As of writing, mypy doesn't yet ship a Python 3.14 wheel; install Python 3.11–3.13 to run the type check.

## Project layout

```
mcp_server/
├── __main__.py                     `python -m mcp_server` entry point
├── server.py                       FastMCP wiring (build_registry, register_tools, build_server, run)
├── core/                           Adapter ABC, registry, aggregator, canonical types, auth provider, encrypted OAuth token store, errors, logging
├── adapters/
│   ├── google_common/              Google OAuth flow, credentials store, bootstrap CLI
│   ├── google_calendar/            Calendar adapter, free-slot finder
│   ├── gmail/                      Gmail adapter, thread fetch
│   └── jira/                       Jira Cloud adapter, JQL builder
└── tools/
    ├── generic.py                  alfred_search / alfred_list_recent / alfred_get
    └── specific.py                 source-specific tool wrappers

.claude/skills/                     daily-brief / follow-ups / blockers / schedule-around
tests/                              Mirrors mcp_server/ layout
```

## Adding a new data source

A new source is a self-contained plugin: one package under `mcp_server/adapters/<source>/` plus its tests. `core/`, `aggregator.py`, and the existing adapters stay untouched, and the generic fan-out tools — and therefore every skill built on them — pick up the new source automatically.

1. **Implement the adapter.** Create `mcp_server/adapters/<source>/<source>_adapter.py` with a class that subclasses `SourceAdapter` (`mcp_server/core/source_adapter.py`) and implements `capabilities`, `list_recent`, `get`, and `search`. Map the source's native records to `SourceItem` / `SearchHit` from `mcp_server/core/canonical.py` so the aggregator can treat them uniformly.
2. **Add a factory.** In `<source>_adapter_factory.py`, expose `build_<source>_adapter(env, ...)` that reads required env vars, raises `ConfigurationError` when anything is missing, and returns the adapter instance. The "skip with a warning" boot behavior depends on this contract.
3. **Register the factory.** Add a `(name, factory)` entry to the `factories` tuple in `build_registry` (`mcp_server/server.py`). That is the only edit outside the new package.
4. **(Optional) Source-specific tools.** If the source has an operation that doesn't fit the generic ABC (e.g., a query DSL, a thread fetch), add a method on the adapter and a thin wrapper in `mcp_server/tools/specific.py`, then register it in `register_tools`.
5. **Tests.** Mirror the package under `tests/adapters/<source>/`. Mock all network I/O — see the existing adapter test suites for the pattern.
6. **Document the env vars.** Add the new variables to `.env` and the Configure section above.

