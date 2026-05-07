from __future__ import annotations

import unittest

from mcp_server.adapters.jira.jira_adapter_factory import build_jira_adapter
from mcp_server.adapters.jira.jira_source_adapter import JiraSourceAdapter
from mcp_server.core.errors import ConfigurationError


def _full_env() -> dict[str, str]:
    return {
        "JIRA_BASE_URL": "https://acme.atlassian.net",
        "JIRA_EMAIL": "me@example.com",
        "JIRA_API_TOKEN": "tok",
    }


class TestBuildJiraAdapter(unittest.TestCase):
    def test_happy_path_returns_adapter(self) -> None:
        adapter = build_jira_adapter(_full_env())
        self.assertIsInstance(adapter, JiraSourceAdapter)
        self.assertEqual(adapter.capabilities.source_name, "jira")

    def test_missing_base_url_raises(self) -> None:
        env = _full_env()
        del env["JIRA_BASE_URL"]
        with self.assertRaises(ConfigurationError) as cm:
            build_jira_adapter(env)
        self.assertIn("JIRA_BASE_URL", str(cm.exception))

    def test_missing_email_raises(self) -> None:
        env = _full_env()
        del env["JIRA_EMAIL"]
        with self.assertRaises(ConfigurationError):
            build_jira_adapter(env)

    def test_missing_api_token_raises(self) -> None:
        env = _full_env()
        del env["JIRA_API_TOKEN"]
        with self.assertRaises(ConfigurationError):
            build_jira_adapter(env)

    def test_empty_string_treated_as_missing(self) -> None:
        env = _full_env()
        env["JIRA_API_TOKEN"] = ""
        with self.assertRaises(ConfigurationError):
            build_jira_adapter(env)

    def test_whitespace_only_treated_as_missing(self) -> None:
        env = _full_env()
        env["JIRA_EMAIL"] = "   "
        with self.assertRaises(ConfigurationError):
            build_jira_adapter(env)


if __name__ == "__main__":
    unittest.main()
