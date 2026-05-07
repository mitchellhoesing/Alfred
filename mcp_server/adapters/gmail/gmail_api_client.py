"""Sync HTTP client for Gmail's ``users.messages`` resource.

Wraps a :class:`googleapiclient.discovery.Resource` (a ``service`` built
via :func:`googleapiclient.discovery.build`) and translates the library's
:class:`googleapiclient.errors.HttpError` into Alfred's domain exceptions.
The service is injected so tests can substitute a fake without touching
the network.

Gmail's ``users.messages.list`` returns thin id objects; the source
adapter follows up with one ``users.messages.get`` per item to fetch the
metadata headers it needs. The ``get`` call defaults to
``format=metadata`` with the ``Subject``, ``From``, ``To``, and ``Date``
headers — enough to populate :class:`Message` without paying for the body.

Failure mapping (HttpError → domain exception):

================================  ==========================================
HttpError status / condition      Raises
================================  ==========================================
2xx                               (returns parsed body)
401 / 403                         :class:`AuthError`
404 (single-message ``get`` only) :class:`ItemNotFoundError`
404 (search / list)               :class:`AdapterError`
429                               :class:`RateLimitError` (with Retry-After)
5xx                               :class:`AdapterError`
other                             :class:`AdapterError`
================================  ==========================================
"""

from __future__ import annotations

from typing import Any, Mapping, NoReturn, Sequence, cast

from googleapiclient.errors import HttpError

from mcp_server.core.errors import (
    AdapterError,
    AuthError,
    ItemNotFoundError,
    RateLimitError,
)


_DEFAULT_METADATA_HEADERS: tuple[str, ...] = ("Subject", "From", "To", "Date")


class GmailApiClient:
    """Thin sync wrapper over Gmail's users.messages Resource."""

    def __init__(self, service: Any, *, user_id: str = "me") -> None:
        self._service = service
        self._user_id = user_id

    def list_messages(
        self,
        *,
        max_results: int,
        q: str | None = None,
        label_ids: Sequence[str] | None = None,
    ) -> Mapping[str, Any]:
        params: dict[str, Any] = {
            "userId": self._user_id,
            "maxResults": max_results,
        }
        if q is not None:
            params["q"] = q
        if label_ids is not None:
            params["labelIds"] = list(label_ids)
        try:
            return cast(
                Mapping[str, Any],
                self._service.users().messages().list(**params).execute(),
            )
        except HttpError as exc:
            self._raise_for_http_error(exc, item_id=None)

    def get_message(
        self,
        message_id: str,
        *,
        format: str = "metadata",
        metadata_headers: Sequence[str] = _DEFAULT_METADATA_HEADERS,
    ) -> Mapping[str, Any]:
        params: dict[str, Any] = {
            "userId": self._user_id,
            "id": message_id,
            "format": format,
            "metadataHeaders": list(metadata_headers),
        }
        try:
            return cast(
                Mapping[str, Any],
                self._service.users().messages().get(**params).execute(),
            )
        except HttpError as exc:
            self._raise_for_http_error(exc, item_id=message_id)

    def get_thread(
        self,
        thread_id: str,
        *,
        format: str = "metadata",
        metadata_headers: Sequence[str] = _DEFAULT_METADATA_HEADERS,
    ) -> Mapping[str, Any]:
        """Fetch a Gmail thread including all of its messages.

        Returns the raw ``users.threads.get`` body — the source adapter
        is responsible for mapping the embedded ``messages`` to canonical
        :class:`Message` objects. Defaults to ``format=metadata`` so we
        only pay for headers, not message bodies.
        """
        params: dict[str, Any] = {
            "userId": self._user_id,
            "id": thread_id,
            "format": format,
            "metadataHeaders": list(metadata_headers),
        }
        try:
            return cast(
                Mapping[str, Any],
                self._service.users().threads().get(**params).execute(),
            )
        except HttpError as exc:
            self._raise_for_http_error(exc, item_id=thread_id)

    @staticmethod
    def _raise_for_http_error(exc: HttpError, *, item_id: str | None) -> NoReturn:
        status = int(exc.resp.status)
        if status == 401:
            raise AuthError("gmail credentials rejected") from exc
        if status == 403:
            raise AuthError("gmail forbidden") from exc
        if status == 404:
            if item_id is not None:
                raise ItemNotFoundError(item_id) from exc
            raise AdapterError("gmail 404") from exc
        if status == 429:
            raise RateLimitError(
                "gmail rate-limited",
                retry_after_seconds=_parse_retry_after(exc),
            ) from exc
        raise AdapterError(f"gmail {status}") from exc


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
