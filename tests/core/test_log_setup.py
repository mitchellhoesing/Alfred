from __future__ import annotations

import logging
import unittest

from mcp_server.core.log_setup import configure_logging


class TestConfigureLogging(unittest.TestCase):
    def setUp(self) -> None:
        # Snapshot existing handlers so we can restore root state.
        self._existing = list(logging.getLogger().handlers)
        self._existing_level = logging.getLogger().level

    def tearDown(self) -> None:
        root = logging.getLogger()
        for h in list(root.handlers):
            if h not in self._existing:
                root.removeHandler(h)
        root.setLevel(self._existing_level)

    def test_adds_handler(self) -> None:
        configure_logging()
        names = {h.get_name() for h in logging.getLogger().handlers}
        self.assertIn("alfred_stderr", names)

    def test_idempotent(self) -> None:
        configure_logging()
        configure_logging()
        alfred = [h for h in logging.getLogger().handlers if h.get_name() == "alfred_stderr"]
        self.assertEqual(len(alfred), 1)

    def test_respects_level(self) -> None:
        configure_logging(level=logging.WARNING)
        self.assertEqual(logging.getLogger().level, logging.WARNING)


if __name__ == "__main__":
    unittest.main()
