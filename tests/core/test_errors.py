from __future__ import annotations

import unittest

from mcp_server.core.errors import (
    AdapterError,
    AlfredError,
    AuthError,
    ConfigurationError,
    ItemNotFoundError,
    RateLimitError,
)


class TestErrorHierarchy(unittest.TestCase):
    def test_alfred_is_base(self) -> None:
        for cls in (AdapterError, AuthError, ConfigurationError):
            self.assertTrue(issubclass(cls, AlfredError))
            self.assertTrue(issubclass(cls, Exception))

    def test_adapter_subclasses(self) -> None:
        self.assertTrue(issubclass(RateLimitError, AdapterError))
        self.assertTrue(issubclass(ItemNotFoundError, AdapterError))

    def test_can_raise_and_catch(self) -> None:
        with self.assertRaises(AlfredError):
            raise RateLimitError("slow down")


class TestRateLimitErrorRetryAfter(unittest.TestCase):
    def test_default_retry_after_is_none(self) -> None:
        err = RateLimitError("slow down")
        self.assertIsNone(err.retry_after_seconds)

    def test_carries_retry_after_seconds(self) -> None:
        err = RateLimitError("slow down", retry_after_seconds=30)
        self.assertEqual(err.retry_after_seconds, 30)

    def test_message_preserved(self) -> None:
        err = RateLimitError("slow down", retry_after_seconds=30)
        self.assertEqual(str(err), "slow down")

    def test_still_an_adapter_error(self) -> None:
        err = RateLimitError("slow down", retry_after_seconds=5)
        self.assertIsInstance(err, AdapterError)
        self.assertIsInstance(err, AlfredError)


if __name__ == "__main__":
    unittest.main()
