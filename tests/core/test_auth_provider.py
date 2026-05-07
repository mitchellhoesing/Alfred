from __future__ import annotations

import unittest

from mcp_server.core.auth_provider import (
    AuthProvider,
    JiraBasicAuth,
    StaticJiraAuthProvider,
)
from mcp_server.core.errors import AuthError


class TestStaticJiraAuthProvider(unittest.TestCase):
    def test_returns_credentials(self) -> None:
        p = StaticJiraAuthProvider(email="a@x.com", api_token="tok")
        creds = p.get_credentials()
        self.assertIsInstance(creds, JiraBasicAuth)
        self.assertEqual(creds.email, "a@x.com")
        self.assertEqual(creds.api_token, "tok")

    def test_rejects_empty_email(self) -> None:
        with self.assertRaises(AuthError):
            StaticJiraAuthProvider(email="", api_token="tok")

    def test_rejects_empty_token(self) -> None:
        with self.assertRaises(AuthError):
            StaticJiraAuthProvider(email="a@x.com", api_token="")

    def test_is_authprovider(self) -> None:
        self.assertIsInstance(
            StaticJiraAuthProvider("a@x.com", "tok"), AuthProvider
        )


if __name__ == "__main__":
    unittest.main()
