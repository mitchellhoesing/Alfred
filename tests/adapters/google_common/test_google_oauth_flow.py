from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from google.oauth2.credentials import Credentials

from mcp_server.adapters.google_common.google_oauth_flow import (
    GOOGLE_OAUTH_SCOPES,
    GoogleOAuthFlow,
)


class TestGoogleOAuthScopes(unittest.TestCase):
    def test_default_scopes_include_calendar_and_gmail_readonly(self) -> None:
        self.assertIn(
            "https://www.googleapis.com/auth/calendar.readonly",
            GOOGLE_OAUTH_SCOPES,
        )
        self.assertIn(
            "https://www.googleapis.com/auth/gmail.readonly",
            GOOGLE_OAUTH_SCOPES,
        )


class TestGoogleOAuthFlowRun(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch(
            "mcp_server.adapters.google_common.google_oauth_flow.InstalledAppFlow"
        )
        self._mock_flow_class = patcher.start()
        self.addCleanup(patcher.stop)

        self._mock_flow = MagicMock()
        self._mock_creds = MagicMock(spec=Credentials)
        self._mock_flow.run_local_server.return_value = self._mock_creds
        self._mock_flow_class.from_client_config.return_value = self._mock_flow

    def test_run_returns_credentials_from_flow(self) -> None:
        oauth = GoogleOAuthFlow(client_id="cid", client_secret="cs")
        result = oauth.run()
        self.assertIs(result, self._mock_creds)

    def test_run_passes_client_credentials_through_config(self) -> None:
        GoogleOAuthFlow(client_id="my-id", client_secret="my-secret").run()

        self._mock_flow_class.from_client_config.assert_called_once()
        _, kwargs = self._mock_flow_class.from_client_config.call_args
        installed = kwargs["client_config"]["installed"]
        self.assertEqual(installed["client_id"], "my-id")
        self.assertEqual(installed["client_secret"], "my-secret")
        self.assertIn("auth_uri", installed)
        self.assertIn("token_uri", installed)

    def test_run_uses_default_scopes(self) -> None:
        GoogleOAuthFlow(client_id="cid", client_secret="cs").run()
        _, kwargs = self._mock_flow_class.from_client_config.call_args
        self.assertEqual(tuple(kwargs["scopes"]), GOOGLE_OAUTH_SCOPES)

    def test_run_accepts_custom_scopes(self) -> None:
        custom = ("https://www.googleapis.com/auth/drive.readonly",)
        GoogleOAuthFlow(
            client_id="cid", client_secret="cs", scopes=custom
        ).run()
        _, kwargs = self._mock_flow_class.from_client_config.call_args
        self.assertEqual(tuple(kwargs["scopes"]), custom)

    def test_run_passes_port_to_local_server(self) -> None:
        GoogleOAuthFlow(
            client_id="cid", client_secret="cs", local_server_port=8765
        ).run()
        self._mock_flow.run_local_server.assert_called_once_with(port=8765)

    def test_default_port_is_zero_for_auto_assign(self) -> None:
        GoogleOAuthFlow(client_id="cid", client_secret="cs").run()
        self._mock_flow.run_local_server.assert_called_once_with(port=0)


if __name__ == "__main__":
    unittest.main()
