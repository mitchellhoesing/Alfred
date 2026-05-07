from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from mcp_server.adapters.google_calendar.calendar_free_slot_finder import (
    find_first_free_slot,
)


_UTC = timezone.utc


def _at(hour: int, minute: int = 0) -> datetime:
    """Helper: 2026-05-05 HH:MM UTC."""
    return datetime(2026, 5, 5, hour, minute, tzinfo=_UTC)


def _window() -> tuple[datetime, datetime]:
    return _at(9, 0), _at(17, 0)  # 9am–5pm


class TestEmptyBusyList(unittest.TestCase):
    def test_returns_window_start(self) -> None:
        start, end = _window()
        result = find_first_free_slot(
            [], window_start=start, window_end=end, duration=timedelta(minutes=30)
        )
        self.assertEqual(result, start)


class TestSingleBusyInterval(unittest.TestCase):
    def test_pre_event_gap_long_enough_returns_window_start(self) -> None:
        # 9-10 free, then busy 10-11, then 11-17 free — pre-event gap = 60min
        start, end = _window()
        result = find_first_free_slot(
            [(_at(10), _at(11))],
            window_start=start,
            window_end=end,
            duration=timedelta(minutes=30),
        )
        self.assertEqual(result, _at(9))

    def test_pre_event_gap_too_short_returns_post_event_start(self) -> None:
        # Window 9–17, busy 9:15–10. Pre-event gap = 15min < 30min → use post-event slot.
        start, end = _window()
        result = find_first_free_slot(
            [(_at(9, 15), _at(10))],
            window_start=start,
            window_end=end,
            duration=timedelta(minutes=30),
        )
        self.assertEqual(result, _at(10))

    def test_busy_covers_entire_window_returns_none(self) -> None:
        start, end = _window()
        result = find_first_free_slot(
            [(_at(8), _at(18))],  # extends past both ends
            window_start=start,
            window_end=end,
            duration=timedelta(minutes=15),
        )
        self.assertIsNone(result)

    def test_duration_exactly_fits_returns_slot(self) -> None:
        start, end = _window()
        # 9–10 free → 60min slot. Request exactly 60 min.
        result = find_first_free_slot(
            [(_at(10), _at(17))],
            window_start=start,
            window_end=end,
            duration=timedelta(minutes=60),
        )
        self.assertEqual(result, _at(9))

    def test_duration_one_minute_too_long_returns_none(self) -> None:
        start, end = _window()
        # Only 9–10 (60 min) and busy fills the rest. Need 61 min → none.
        result = find_first_free_slot(
            [(_at(10), _at(17))],
            window_start=start,
            window_end=end,
            duration=timedelta(minutes=61),
        )
        self.assertIsNone(result)


class TestMultipleBusyIntervals(unittest.TestCase):
    def test_finds_inter_event_gap_when_pre_event_too_short(self) -> None:
        # Busy 9-10, 12-13. Pre-event = 0min, inter-event = 2hr. Need 90min.
        start, end = _window()
        result = find_first_free_slot(
            [(_at(9), _at(10)), (_at(12), _at(13))],
            window_start=start,
            window_end=end,
            duration=timedelta(minutes=90),
        )
        self.assertEqual(result, _at(10))

    def test_skips_inter_event_gaps_too_small(self) -> None:
        # Busy 9-11, 11:15-13. Pre = 0, inter = 15min < 30, post = 4hr
        start, end = _window()
        result = find_first_free_slot(
            [(_at(9), _at(11)), (_at(11, 15), _at(13))],
            window_start=start,
            window_end=end,
            duration=timedelta(minutes=30),
        )
        self.assertEqual(result, _at(13))

    def test_back_to_back_events_collapse_to_single_busy_block(self) -> None:
        # Busy 9-10, 10-11 — no gap between them; needs 30min slot
        start, end = _window()
        result = find_first_free_slot(
            [(_at(9), _at(10)), (_at(10), _at(11))],
            window_start=start,
            window_end=end,
            duration=timedelta(minutes=30),
        )
        self.assertEqual(result, _at(11))

    def test_overlapping_events_merge_correctly(self) -> None:
        # Busy 9-11 and 10-12 → effectively 9-12. Request 30min.
        start, end = _window()
        result = find_first_free_slot(
            [(_at(9), _at(11)), (_at(10), _at(12))],
            window_start=start,
            window_end=end,
            duration=timedelta(minutes=30),
        )
        self.assertEqual(result, _at(12))

    def test_unsorted_input_is_handled(self) -> None:
        # Same as inter-event test but reverse-ordered input.
        start, end = _window()
        result = find_first_free_slot(
            [(_at(12), _at(13)), (_at(9), _at(10))],
            window_start=start,
            window_end=end,
            duration=timedelta(minutes=90),
        )
        self.assertEqual(result, _at(10))


class TestEventsOutsideWindow(unittest.TestCase):
    def test_event_entirely_before_window_is_ignored(self) -> None:
        start, end = _window()
        result = find_first_free_slot(
            [(_at(7), _at(8))],  # ends before window starts
            window_start=start,
            window_end=end,
            duration=timedelta(minutes=30),
        )
        self.assertEqual(result, start)

    def test_event_entirely_after_window_is_ignored(self) -> None:
        start, end = _window()
        result = find_first_free_slot(
            [(_at(20), _at(21))],
            window_start=start,
            window_end=end,
            duration=timedelta(minutes=30),
        )
        self.assertEqual(result, start)

    def test_event_overlapping_window_start_is_clipped(self) -> None:
        # Event 8-10 overlaps window-start at 9. Effectively busy 9-10.
        start, end = _window()
        result = find_first_free_slot(
            [(_at(8), _at(10))],
            window_start=start,
            window_end=end,
            duration=timedelta(minutes=30),
        )
        self.assertEqual(result, _at(10))

    def test_event_overlapping_window_end_is_clipped(self) -> None:
        # Event 16-18 overlaps window-end at 17. Pre-event gap = 9–16 = 7hr.
        start, end = _window()
        result = find_first_free_slot(
            [(_at(16), _at(18))],
            window_start=start,
            window_end=end,
            duration=timedelta(minutes=30),
        )
        self.assertEqual(result, _at(9))


if __name__ == "__main__":
    unittest.main()
