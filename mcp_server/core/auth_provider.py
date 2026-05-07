"""Credential provider abstractions.

Generic over the credential type because Google returns
``google.oauth2.credentials.Credentials`` while Jira just needs an
``(email, api_token)`` pair — there is no useful unified shape, so the ABC
is parameterized rather than forced into a lowest common denominator.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar

from mcp_server.core.errors import AuthError


CredentialT = TypeVar("CredentialT")


class AuthProvider(ABC, Generic[CredentialT]):
    @abstractmethod
    def get_credentials(self) -> CredentialT: ...


@dataclass(frozen=True)
class JiraBasicAuth:
    email: str
    api_token: str


class StaticJiraAuthProvider(AuthProvider[JiraBasicAuth]):
    """Reads Jira email + API token from constructor args (typically env vars)."""

    def __init__(self, email: str, api_token: str) -> None:
        if not email or not api_token:
            raise AuthError("Jira email and api_token must both be non-empty")
        self._creds = JiraBasicAuth(email=email, api_token=api_token)

    def get_credentials(self) -> JiraBasicAuth:
        return self._creds
