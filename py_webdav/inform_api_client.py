"""INFORM API client for retrieving data from IN-FORM via REST API.

This client handles OAuth2 authentication with automatic token refresh
and provides methods to interact with the INFORM API.

Can be reused for both CardDAV and CalDAV backend implementations.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
import os

import httpx

INFORM_CLIENT_ID = os.getenv("INFORM_CLIENT_ID")
INFORM_CLIENT_SECRET = os.getenv("INFORM_CLIENT_SECRET")
INFORM_LICENSE = os.getenv("INFORM_LICENSE")
INFORM_USER = os.getenv("INFORM_USER")
INFORM_PASSWORD = os.getenv("INFORM_PASSWORD")


@dataclass
class InformConfig:
    """Configuration for INFORM API client.

    All values are placeholders and should be replaced with actual credentials.
    """

    # OAuth2 credentials
    client_id: str = INFORM_CLIENT_ID or ""
    client_secret: str = INFORM_CLIENT_SECRET or ""

    # INFORM credentials
    license: str = INFORM_LICENSE or "W993259P"
    username: str = INFORM_USER
    password: str = INFORM_PASSWORD

    # API configuration
    base_url: str = "https://testapi.in-software.com/v1"
    timeout: float = 30.0  # Request timeout in seconds


@dataclass
class InformTokens:
    """OAuth2 tokens from INFORM API."""

    access_token: str
    refresh_token: str
    expires_at: datetime
    token_type: str = "bearer"

    def is_expired(self) -> bool:
        """Check if access token is expired or will expire soon."""
        # Consider token expired 60 seconds before actual expiration
        return datetime.now(UTC) >= (self.expires_at - timedelta(seconds=60))


class InformAPIClient:
    """Client for INFORM API with automatic token refresh.

    This client can be reused for CardDAV and CalDAV implementations.
    """

    def __init__(self, config: InformConfig | None = None) -> None:
        """Initialize INFORM API client.

        Args:
            config: INFORM API configuration (uses default if None)
        """
        self.config = config or InformConfig()
        self._tokens: InformTokens | None = None
        self._token_lock = asyncio.Lock()
        self._http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                headers={"Content-Type": "application/json"}
            )
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client and cleanup resources."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def __aenter__(self) -> InformAPIClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def _request_token_with_password(self) -> InformTokens:
        """Request OAuth2 token using password grant type."""
        client = await self._get_http_client()

        payload = {
            "grantType": "password",
            "clientId": self.config.client_id,
            "clientSecret": self.config.client_secret,
            "license": self.config.license,
            "user": self.config.username,
            "pass": self.config.password,
        }

        response = await client.post("/token", json=payload)
        response.raise_for_status()

        data = response.json()

        # Calculate token expiration time
        expires_in = int(data.get("expiresIn", 1800))  # Default 30 minutes
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

        return InformTokens(
            access_token=data["accessToken"],
            refresh_token=data["refreshToken"],
            expires_at=expires_at,
            token_type=data.get("tokenType", "bearer"),
        )

    async def _request_token_with_refresh(self, refresh_token: str) -> InformTokens:
        """Request OAuth2 token using refresh token grant type."""
        client = await self._get_http_client()

        payload = {
            "grantType": "refreshToken",
            "clientId": self.config.client_id,
            "clientSecret": self.config.client_secret,
            "refreshToken": refresh_token,
        }

        response = await client.post("/token", json=payload)
        response.raise_for_status()

        data = response.json()

        # Calculate token expiration time
        expires_in = int(data.get("expiresIn", 1800))  # Default 30 minutes
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

        return InformTokens(
            access_token=data["accessToken"],
            refresh_token=data["refreshToken"],
            expires_at=expires_at,
            token_type=data.get("tokenType", "bearer"),
        )

    async def _ensure_valid_token(self) -> str:
        """Ensure we have a valid access token, refreshing if necessary.

        Returns:
            Valid access token
        """
        async with self._token_lock:
            # Get new token if we don't have one
            if self._tokens is None:
                self._tokens = await self._request_token_with_password()
                return self._tokens.access_token

            # Refresh token if expired
            if self._tokens.is_expired():
                try:
                    self._tokens = await self._request_token_with_refresh(
                        self._tokens.refresh_token
                    )
                except Exception:
                    # If refresh fails, get new token with password
                    self._tokens = await self._request_token_with_password()

            return self._tokens.access_token

    async def _make_request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make authenticated request to INFORM API.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., "/companies")
            **kwargs: Additional arguments for httpx request

        Returns:
            HTTP response

        Raises:
            httpx.HTTPError: If request fails
        """
        client = await self._get_http_client()
        token = await self._ensure_valid_token()

        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"

        response = await client.request(method, path, headers=headers, **kwargs)
        response.raise_for_status()

        return response

    async def get_companies(self) -> list[str]:
        """Get list of available companies.

        Returns:
            List of company names
        """
        response = await self._make_request("GET", "/companies")
        data = response.json()

        # Extract company names from response
        companies = []
        for company in data.get("companies", []):
            if "companyName" in company:
                companies.append(company["companyName"])

        return companies

    async def get_addresses(
        self,
        company: str,
        offset: int = 0,
        limit: int = 1000,
        address_type: str | None = None,
        phrase: str | None = None,
    ) -> dict[str, Any]:
        """Get addresses from INFORM.

        Args:
            company: Company name
            offset: Pagination offset
            limit: Maximum number of results (max 1000)
            address_type: Filter by address type (customer, supplier, employee, other)
            phrase: Search phrase

        Returns:
            Dictionary with 'addresses', 'count', and 'totalCount' keys
        """
        params: dict[str, Any] = {
            "offset": offset,
            "limit": min(limit, 1000),
        }

        if address_type:
            params["addressType"] = address_type

        if phrase:
            params["phrase"] = phrase

        response = await self._make_request(
            "GET",
            f"/companies/{company}/addresses",
            params=params,
        )

        data: dict[str, Any] = response.json()
        return data

    async def get_address(
        self,
        company: str,
        address_key: str,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get single address by key.

        Args:
            company: Company name
            address_key: Address identification key (e.g., "BACHE")
            fields: List of fields to return

        Returns:
            Address data dictionary
        """
        params: dict[str, Any] = {}

        if fields:
            params["fields"] = ",".join(fields)

        response = await self._make_request(
            "GET",
            f"/companies/{company}/addresses/{address_key}",
            params=params,
        )

        data: dict[str, Any] = response.json()
        return data
