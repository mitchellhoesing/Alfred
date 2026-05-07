"""Jira Cloud SourceAdapter package.

Public surface — anything else under this package is an implementation
detail and should not be imported from outside the package:

- :class:`JiraSourceAdapter` — the :class:`SourceAdapter` registered on the
  shared :class:`AdapterRegistry`.
- :func:`build_jira_adapter` — factory that wires env vars → adapter.
"""

from mcp_server.adapters.jira.jira_adapter_factory import build_jira_adapter
from mcp_server.adapters.jira.jira_source_adapter import JiraSourceAdapter


__all__ = ["JiraSourceAdapter", "build_jira_adapter"]
