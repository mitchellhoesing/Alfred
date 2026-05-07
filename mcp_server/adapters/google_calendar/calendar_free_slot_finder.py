"""Pure free-slot search over a list of busy intervals.

Given a search window and a duration, walk a sorted, merged list of busy
intervals and return the start of the first gap that fits the duration —
or :data:`None` if no qualifying gap exists.

This module is **pure**: it has no dependency on the calendar API client
or the source adapter, and no I/O. It is unit-testable in isolation,
which is why it lives in its own module rather than as a private method
on :class:`GoogleCalendarSourceAdapter`. The adapter loads events from
the API, projects them to ``(start, end)`` tuples, and delegates the
gap-finding algorithm here.

All timestamps must be timezone-aware so comparisons are well-defined.
The adapter normalizes naive (all-day) event datetimes to UTC midnight
before calling in.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence


def find_first_free_slot(
    busy_intervals: Sequence[tuple[datetime, datetime]],
    *,
    window_start: datetime,
    window_end: datetime,
    duration: timedelta,
) -> datetime | None:
    """Return the start of the first ``[t, t + duration]`` gap inside the window.

    ``busy_intervals`` may be unsorted and may overlap or extend past the
    window boundaries; the function sorts, clips, and merges them before
    walking. Returns :data:`None` if no qualifying gap exists.
    """
    busy = _clip_and_merge(busy_intervals, window_start, window_end)

    cursor = window_start
    for busy_start, busy_end in busy:
        if busy_start - cursor >= duration:
            return cursor
        if busy_end > cursor:
            cursor = busy_end
    if window_end - cursor >= duration:
        return cursor
    return None


def _clip_and_merge(
    intervals: Sequence[tuple[datetime, datetime]],
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[datetime, datetime]]:
    """Drop out-of-window intervals, clip overlapping ones, merge adjacent."""
    clipped: list[tuple[datetime, datetime]] = []
    for start, end in intervals:
        clipped_start = max(start, window_start)
        clipped_end = min(end, window_end)
        if clipped_start < clipped_end:
            clipped.append((clipped_start, clipped_end))

    clipped.sort(key=lambda iv: iv[0])

    merged: list[tuple[datetime, datetime]] = []
    for start, end in clipped:
        if merged and start <= merged[-1][1]:
            prev_start, prev_end = merged[-1]
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged
