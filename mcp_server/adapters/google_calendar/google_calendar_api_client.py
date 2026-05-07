"""Sync HTTP client for Google Calendar's Events resource.

Wraps a :class:`googleapiclient.discovery.Resource` (a ``service`` built
via :func:`googleapiclient.discovery.build`) and translates the library's
:class:`googleapiclient.errors.HttpError` into Alfred's domain exceptions.
The service is injected so tests can substitute a fake without touching
the network.

The Calendar API's ``events.list`` endpoint accepts both ``timeMin`` /
``timeMax`` (event start window) and ``updatedMin`` (last-modification
filter). The :class:`GoogleCalendarSourceAdapter` will pick which one to
pass based on whether the caller wants "what's coming up" or "what
recently changed."

Failure mapping (HttpError → domain exception):

================================  ==========================================
HttpError status / condition      Raises
================================  ==========================================
2xx                               (returns parsed body)
401 / 403                         :class:`AuthError`
404 (single-event ``get`` only)   :class:`ItemNotFoundError`
404 (search / list)               :class:`AdapterError`
429                               :class:`RateLimitError` (with Retry-After)
5xx                               :class:`AdapterError`
other                             :class:`AdapterError`
================================  ==========================================
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, NoReturn, cast

from googleapiclient.errors import HttpError

from mcp_server.core.errors import (
    AdapterError,
    AuthError,
    ItemNotFoundError,
    RateLimitError,
)


class GoogleCalendarApiClient:
    """Thin sync wrapper over Google Calendar's events Resource."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def list_events(
        self,
        *,
        max_results: int,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        updated_min: datetime | None = None,
        q: str | None = None,
        calendar_id: str = "primary",
    ) -> Mapping[str, Any]:
        params: dict[str, Any] = {
            "calendarId": calendar_id,
            "singleEvents": True,
            "orderBy": "startTime",
            "maxResults": max_results,
        }
        if time_min is not None:
            params["timeMin"] = time_min.isoformat()
        if time_max is not None:
            params["timeMax"] = time_max.isoformat()
        if updated_min is not None:
            params["updatedMin"] = updated_min.isoformat()
        if q is not None:
            params["q"] = q
        try:
            return cast(
                Mapping[str, Any],
                self._service.events().list(**params).execute(),
            )
        except HttpError as exc:
            self._raise_for_http_error(exc, item_id=None)

    def get_event(
        self, event_id: str, *, calendar_id: str = "primary"
    ) -> Mapping[str, Any]:
        try:
            return cast(
                Mapping[str, Any],
                self._service.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute(),
            )
        except HttpError as exc:
            self._raise_for_http_error(exc, item_id=event_id)

    @staticmethod
    def _raise_for_http_error(exc: HttpError, *, item_id: str | None) -> NoReturn:
        status = int(exc.resp.status)
        if status == 401:
            raise AuthError("google calendar credentials rejected") from exc
        if status == 403:
            raise AuthError("google calendar forbidden") from exc
        if status == 404:
            if item_id is not None:
                raise ItemNotFoundError(item_id) from exc
            raise AdapterError("google calendar 404") from exc
        if status == 429:
            raise RateLimitError(
                "google calendar rate-limited",
                retry_after_seconds=_parse_retry_after(exc),
            ) from exc
        raise AdapterError(f"google calendar {status}") from exc


def _parse_retry_after(exc: HttpError) -> int | None:
    """Pull a ``Retry-After`` header value (seconds) off an HttpError, if any."""
    raw: Any = None
    try:
        raw = exc.resp.get("retry-after")
    except Exception:
        try:
            raw = exc.resp["retry-after"]
        except Exception:
            return None
    if raw is None:
        return None
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return None
