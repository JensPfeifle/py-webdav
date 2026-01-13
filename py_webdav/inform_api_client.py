"""INFORM API client for retrieving data from IN-FORM via REST API.

This client handles OAuth2 authentication with automatic token refresh
and provides methods to interact with the INFORM API.

Can be reused for both CardDAV and CalDAV backend implementations.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

INFORM_CLIENT_ID = os.getenv("INFORM_CLIENT_ID", "").strip('"')
INFORM_CLIENT_SECRET = os.getenv("INFORM_CLIENT_SECRET", "").strip('"')
INFORM_LICENSE = os.getenv("INFORM_LICENSE", "").strip('"')
INFORM_USER = os.getenv("INFORM_USER", "").strip('"')
INFORM_PASSWORD = os.getenv("INFORM_PASSWORD", "").strip('"')
INFORM_TIMEZONE = os.getenv("INFORM_TIMEZONE", "Europe/Berlin").strip('"')


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
    username: str = INFORM_USER or ""
    password: str = INFORM_PASSWORD or ""

    # API configuration
    base_url: str = "https://testapi.in-software.com/v1"
    timeout: float = 30.0  # Request timeout in seconds

    # Server timezone for occurrence time conversion
    # INFORM API returns occurrenceStartTime/occurrenceEndTime in seconds from
    # midnight in the server's local timezone, not UTC
    server_timezone: str = INFORM_TIMEZONE or "Europe/Berlin"


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

    def __init__(self, config: InformConfig | None = None, debug: bool = False) -> None:
        """Initialize INFORM API client.

        Args:
            config: INFORM API configuration (uses default if None)
            debug: Enable debug logging of API requests/responses
        """
        self.config = config or InformConfig()
        self.debug = debug
        self._tokens: InformTokens | None = None
        self._token_lock = asyncio.Lock()
        self._http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                headers={"Content-Type": "application/json"},
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

        # Log request if debug is enabled
        if self.debug:
            from py_webdav.debug import log_inform_request

            # Redact sensitive fields in log
            log_payload = payload.copy()
            log_payload["clientSecret"] = "[REDACTED]"
            log_payload["pass"] = "[REDACTED]"
            log_inform_request("POST", f"{self.config.base_url}/token", {}, log_payload)

        response = await client.post("/token", json=payload)

        # Log response if debug is enabled
        if self.debug:
            from py_webdav.debug import log_inform_response

            response_body = None
            if response.headers.get("content-type", "").startswith("application/json"):
                try:
                    response_data = response.json()
                    # Redact sensitive tokens in log
                    response_body = response_data.copy()
                    if "accessToken" in response_body:
                        response_body["accessToken"] = "[REDACTED]"
                    if "refreshToken" in response_body:
                        response_body["refreshToken"] = "[REDACTED]"
                except Exception:
                    pass

            log_inform_response(response.status_code, response_body)

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

        # Log request if debug is enabled
        if self.debug:
            from py_webdav.debug import log_inform_request

            # Redact sensitive fields in log
            log_payload = payload.copy()
            log_payload["clientSecret"] = "[REDACTED]"
            log_payload["refreshToken"] = "[REDACTED]"
            log_inform_request("POST", f"{self.config.base_url}/token", {}, log_payload)

        response = await client.post("/token", json=payload)

        # Log response if debug is enabled
        if self.debug:
            from py_webdav.debug import log_inform_response

            response_body = None
            if response.headers.get("content-type", "").startswith("application/json"):
                try:
                    response_data = response.json()
                    # Redact sensitive tokens in log
                    response_body = response_data.copy()
                    if "accessToken" in response_body:
                        response_body["accessToken"] = "[REDACTED]"
                    if "refreshToken" in response_body:
                        response_body["refreshToken"] = "[REDACTED]"
                except Exception:
                    pass

            log_inform_response(response.status_code, response_body)

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

        # Log request if debug is enabled
        if self.debug:
            from py_webdav.debug import log_inform_request

            full_url = f"{self.config.base_url}{path}"
            # Include query params in URL if present
            if "params" in kwargs:
                params = kwargs["params"]
                if params:
                    param_str = "&".join(f"{k}={v}" for k, v in params.items())
                    full_url = f"{full_url}?{param_str}"

            request_body = kwargs.get("json")
            log_inform_request(method, full_url, headers, request_body)

        response = await client.request(method, path, headers=headers, **kwargs)

        # Log response if debug is enabled
        if self.debug:
            from py_webdav.debug import log_inform_response

            response_body = None
            if response.headers.get("content-type", "").startswith("application/json"):
                try:
                    response_body = response.json()
                except Exception:
                    pass

            log_inform_response(response.status_code, response_body)

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

    # Calendar Events API methods

    async def get_calendar_events_occurrences(
        self,
        owner_key: str,
        start_datetime: str,
        end_datetime: str,
        offset: int = 0,
        limit: int = 1000,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get calendar event occurrences for an owner in a date range.

        Returns both single events and serial event occurrences.

        Args:
            owner_key: Employee key who owns the events
            start_datetime: Start of date range (ISO 8601)
            end_datetime: End of date range (ISO 8601)
            offset: Pagination offset
            limit: Maximum number of results (max 1000)
            fields: List of fields to return

        Returns:
            Dictionary with 'calendarEvents', 'count', and 'totalCount' keys
        """
        params: dict[str, Any] = {
            "ownerKey": owner_key,
            "endDateTime.gte": start_datetime,
            "startDateTime.lte": end_datetime,
            "offset": offset,
            "limit": min(limit, 1000),
        }

        if fields:
            params["fields"] = ",".join(fields)

        response = await self._make_request(
            "GET",
            "/calendarEventsOccurrences",
            params=params,
        )

        data: dict[str, Any] = response.json()
        return data

    async def get_calendar_event(
        self,
        event_key: str,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get single calendar event by key.

        Args:
            event_key: Calendar event identification key
            fields: List of fields to return

        Returns:
            Calendar event data dictionary
        """
        params: dict[str, Any] = {}

        if fields:
            params["fields"] = ",".join(fields)

        response = await self._make_request(
            "GET",
            f"/calendarEvents/{event_key}",
            params=params,
        )

        data: dict[str, Any] = response.json()
        return data

    async def create_calendar_event(
        self,
        event_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a new calendar event.

        Args:
            event_data: Calendar event data (single or serial)

        Returns:
            Created calendar event data
        """
        response = await self._make_request(
            "POST",
            "/calendarEvents",
            json=event_data,
        )

        data: dict[str, Any] = response.json()
        return data

    async def update_calendar_event(
        self,
        event_key: str,
        event_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an existing calendar event.

        Args:
            event_key: Calendar event identification key
            event_data: Partial calendar event data to update

        Returns:
            Updated calendar event data
        """
        response = await self._make_request(
            "PATCH",
            f"/calendarEvents/{event_key}",
            json=event_data,
        )

        data: dict[str, Any] = response.json()
        return data

    async def delete_calendar_event(
        self,
        event_key: str,
    ) -> None:
        """Delete a calendar event.

        Args:
            event_key: Calendar event identification key
        """
        await self._make_request(
            "DELETE",
            f"/calendarEvents/{event_key}",
        )

    async def get_calendar_event_occurrence(
        self,
        event_key: str,
        occurrence_id: str,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get data for a specific occurrence of a serial calendar event.

        Args:
            event_key: Calendar event identification key
            occurrence_id: Occurrence identification
            fields: List of fields to return

        Returns:
            Calendar event occurrence data
        """
        params: dict[str, Any] = {}
        if fields:
            params["fields"] = ",".join(fields)

        response = await self._make_request(
            "GET",
            f"/calendarEvents/{event_key}/occurrences/{occurrence_id}",
            params=params,
        )

        data: dict[str, Any] = response.json()
        return data

    async def update_calendar_event_occurrence(
        self,
        event_key: str,
        occurrence_id: str,
        event_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update a specific occurrence of a serial calendar event.

        Args:
            event_key: Calendar event identification key
            occurrence_id: Occurrence identification
            event_data: Partial event data to update for this occurrence

        Returns:
            Updated occurrence data
        """
        response = await self._make_request(
            "PATCH",
            f"/calendarEvents/{event_key}/occurrences/{occurrence_id}",
            json=event_data,
        )

        data: dict[str, Any] = response.json()
        return data

    async def delete_calendar_event_occurrence(
        self,
        event_key: str,
        occurrence_id: str,
    ) -> None:
        """Delete a specific occurrence of a serial calendar event.

        Args:
            event_key: Calendar event identification key
            occurrence_id: Occurrence identification
        """
        await self._make_request(
            "DELETE",
            f"/calendarEvents/{event_key}/occurrences/{occurrence_id}",
        )
