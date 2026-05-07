"""Sync HTTP client for Jira Cloud's REST v3 API.

This is the only place in the Jira adapter that touches the network. The
client is intentionally **synchronous**; the async :class:`SourceAdapter`
contract is honored by :class:`JiraSourceAdapter`, which bridges to this
sync surface via :func:`asyncio.to_thread`. Keeping the network layer sync
makes retries, error mapping, and tests linear and easy to reason about.

Atlassian deprecated ``/rest/api/3/search`` in 2024 in favor of
``/rest/api/3/search/jql`` (token-paginated, slightly different response
shape) — that is the endpoint this client targets. v1 issues a single page
per call (capped at ``limit``); when the response carries a
``nextPageToken`` we log a warning so callers know the result was
truncated. Full pagination is a follow-up.

Failure mapping (see :func:`_raise_for_status`):

==============================  ==========================================
HTTP / network condition        Raises
==============================  ==========================================
2xx                             (returns parsed body)
400 / 410 / 5xx                 :class:`AdapterError`
401 / 403                       :class:`AuthError`
404 (single-issue lookup only)  :class:`ItemNotFoundError`
404 (search)                    :class:`AdapterError`
429                             :class:`RateLimitError` (with Retry-After)
``requests.Timeout``            :class:`AdapterError`
``requests.ConnectionError``    :class:`AdapterError`
non-JSON body                   :class:`AdapterError`
non-object JSON body            :class:`AdapterError`
==============================  ==========================================
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any, Mapping, Sequence, cast

import requests

from mcp_server.core.auth_provider import AuthProvider, JiraBasicAuth
from mcp_server.core.errors import (
    AdapterError,
    AuthError,
    ItemNotFoundError,
    RateLimitError,
)


_log = logging.getLogger(__name__)
_MAX_BODY_EXCERPT = 200


@dataclass(frozen=True)
class JiraCloudHttpClientConfig:
    base_url: str
    timeout_seconds: float = 15.0


class JiraCloudHttpClient:
    """Thin sync wrapper over Atlassian's Jira Cloud REST v3 API."""

    def __init__(
        self,
        config: JiraCloudHttpClientConfig,
        auth_provider: AuthProvider[JiraBasicAuth],
        session: requests.Session | None = None,
    ) -> None:
        self._config = config
        self._auth_provider = auth_provider
        self._session = session if session is not None else requests.Session()

    def get_issue(
        self, issue_key: str, *, fields: Sequence[str]
    ) -> Mapping[str, Any]:
        """Fetch a single issue. Maps 404 to :class:`ItemNotFoundError`."""
        url = (
            f"{self._config.base_url.rstrip('/')}/rest/api/3/issue/{issue_key}"
        )
        params = {"fields": ",".join(fields)}
        try:
            resp = self._session.get(
                url,
                headers=self._build_headers(),
                params=params,
                timeout=self._config.timeout_seconds,
            )
        except requests.Timeout as exc:
            raise AdapterError(f"jira timeout calling {url}") from exc
        except requests.ConnectionError as exc:
            raise AdapterError(f"jira network error calling {url}") from exc
        self._raise_for_status(resp, item_id=issue_key)
        return self._parse_json(resp)

    def search_issues_jql(
        self,
        *,
        jql: str,
        fields: Sequence[str],
        limit: int,
    ) -> Mapping[str, Any]:
        """POST a single-page JQL search to ``/rest/api/3/search/jql``.

        v1: no follow-up paging. If the response includes a
        ``nextPageToken`` (i.e. there *would* be more results), we emit a
        warning so the caller knows the list was truncated at ``limit``.
        """
        url = f"{self._config.base_url.rstrip('/')}/rest/api/3/search/jql"
        body: dict[str, Any] = {
            "jql": jql,
            "fields": list(fields),
            "maxResults": limit,
        }
        try:
            resp = self._session.post(
                url,
                headers={
                    **self._build_headers(),
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=self._config.timeout_seconds,
            )
        except requests.Timeout as exc:
            raise AdapterError(f"jira timeout calling {url}") from exc
        except requests.ConnectionError as exc:
            raise AdapterError(f"jira network error calling {url}") from exc
        self._raise_for_status(resp, item_id=None)
        result = self._parse_json(resp)
        if result.get("nextPageToken"):
            _log.warning(
                "jira search returned nextPageToken; pagination not "
                "implemented — results truncated to %d issues",
                limit,
            )
        return result

    def _build_headers(self) -> Mapping[str, str]:
        creds = self._auth_provider.get_credentials()
        token = base64.b64encode(
            f"{creds.email}:{creds.api_token}".encode("utf-8")
        ).decode("ascii")
        return {
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
        }

    def _raise_for_status(
        self,
        resp: requests.Response,
        *,
        item_id: str | None,
    ) -> None:
        status = resp.status_code
        if 200 <= status < 300:
            return
        excerpt = (resp.text or "")[:_MAX_BODY_EXCERPT]
        if status == 401:
            raise AuthError("jira credentials rejected")
        if status == 403:
            raise AuthError(f"jira forbidden: {excerpt}")
        if status == 404:
            if item_id is not None:
                raise ItemNotFoundError(item_id)
            raise AdapterError(f"jira 404: {excerpt}")
        if status == 410:
            raise AdapterError(f"jira endpoint deprecated: {excerpt}")
        if status == 429:
            raise RateLimitError(
                f"jira rate-limited: {excerpt}",
                retry_after_seconds=self._parse_retry_after(
                    resp.headers.get("Retry-After")
                ),
            )
        raise AdapterError(f"jira {status}: {excerpt}")

    @staticmethod
    def _parse_json(resp: requests.Response) -> Mapping[str, Any]:
        try:
            data = resp.json()
        except ValueError as exc:
            raise AdapterError("jira returned non-JSON body") from exc
        if not isinstance(data, dict):
            raise AdapterError(
                f"jira returned non-object JSON: {type(data).__name__}"
            )
        return cast(Mapping[str, Any], data)

    @staticmethod
    def _parse_retry_after(header: str | None) -> int | None:
        if header is None:
            return None
        try:
            return max(0, int(header))
        except (TypeError, ValueError):
            return None
