#!/usr/bin/env python3
"""Test different datetime formats to find what INFORM API expects."""

import asyncio
import os
from datetime import UTC, datetime, timedelta

import httpx
import pytest


class InformAPITest:
    """Simple INFORM API client for testing."""

    def __init__(self):
        self.base_url = "https://testapi.in-software.com/v1"
        self.client_id = os.getenv("INFORM_CLIENT_ID", "").strip('"')
        self.client_secret = os.getenv("INFORM_CLIENT_SECRET", "").strip('"')
        self.license = os.getenv("INFORM_LICENSE", "").strip('"')
        self.username = os.getenv("INFORM_USER", "").strip('"')
        self.password = os.getenv("INFORM_PASSWORD", "").strip('"')
        self.access_token = None
        self.http_client = None

    async def __aenter__(self):
        self.http_client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        await self.authenticate()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.http_client:
            await self.http_client.aclose()

    async def authenticate(self):
        assert self.http_client
        payload = {
            "grantType": "password",
            "clientId": self.client_id,
            "clientSecret": self.client_secret,
            "license": self.license,
            "user": self.username,
            "pass": self.password,
        }
        response = await self.http_client.post("/token", json=payload)
        response.raise_for_status()
        data = response.json()
        self.access_token = data["accessToken"]

    def _get_headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    async def create_event(self, event_data):
        assert self.http_client
        response = await self.http_client.post(
            "/calendarEvents", json=event_data, headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()

    async def get_event(self, event_key):
        assert self.http_client
        response = await self.http_client.get(
            f"/calendarEvents/{event_key}",
            params={"fields": "all"},
            headers=self._get_headers(),
        )
        response.raise_for_status()
        return response.json()

    async def delete_event(self, event_key):
        assert self.http_client
        response = await self.http_client.delete(
            f"/calendarEvents/{event_key}", headers=self._get_headers()
        )
        response.raise_for_status()


@pytest.fixture
async def api():
    """Create INFORM API test client."""
    async with InformAPITest() as client:
        yield client


async def _test_datetime_format_helper(api, format_name, start_str, end_str):
    """Test a specific datetime format."""
    print(f"\n{'=' * 80}")
    print(f"Testing: {format_name}")
    print(f"  Start: {start_str}")
    print(f"  End:   {end_str}")
    print("=" * 80)

    event_data = {
        "eventMode": "single",
        "subject": f"Test {format_name}",
        "ownerKey": api.username,
        "startDateTime": start_str,
        "endDateTime": end_str,
        "startDateTimeEnabled": True,
        "endDateTimeEnabled": True,
        "wholeDayEvent": False,
    }

    try:
        created = await api.create_event(event_data)
        event_key = created["key"]

        fetched = await api.get_event(event_key)
        result_start = fetched.get("startDateTime")
        result_end = fetched.get("endDateTime")

        print("\nResult:")
        print(f"  Start: {result_start}")
        print(f"  End:   {result_end}")

        # Check if time was preserved (look for 14:30 in the result)
        if "14:30" in result_start or "T14:30" in result_start:
            print("✅ SUCCESS: Time 14:30 preserved!")
        elif "00:00" in result_start or "T00:00" in result_start:
            print("❌ FAIL: Time reset to midnight")
        else:
            print("⚠️  UNKNOWN: Unexpected time format")

        await api.delete_event(event_key)
        return True

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


async def main():
    """Test various datetime formats."""
    print("=" * 80)
    print("INFORM API DateTime Format Tests")
    print("=" * 80)
    print("\nTesting different datetime formats to find what preserves time correctly")
    print("Target time: 14:30:00 (2:30 PM)")

    async with InformAPITest() as api:
        now = datetime.now(UTC)
        target_date = now.replace(hour=14, minute=30, second=0, microsecond=0)
        target_end = target_date + timedelta(hours=1)

        # Format 1: ISO 8601 with timezone (+00:00)
        await _test_datetime_format_helper(
            api,
            "ISO 8601 with +00:00",
            target_date.isoformat(),
            target_end.isoformat(),
        )

        # Format 2: ISO 8601 with Z
        await _test_datetime_format_helper(
            api,
            "ISO 8601 with Z",
            target_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            target_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        # Format 3: Without timezone info
        await _test_datetime_format_helper(
            api,
            "ISO 8601 without timezone",
            target_date.strftime("%Y-%m-%dT%H:%M:%S"),
            target_end.strftime("%Y-%m-%dT%H:%M:%S"),
        )

        # Format 4: OpenAPI example format (from the docs)
        await _test_datetime_format_helper(
            api,
            "OpenAPI example format",
            "2022-06-22T12:30:00Z",  # From OpenAPI spec
            "2022-06-22T13:30:00Z",
        )

        # Format 5: Today's date with explicit time
        today = now.date()
        await _test_datetime_format_helper(
            api,
            "Today with explicit time (Z)",
            f"{today}T14:30:00Z",
            f"{today}T15:30:00Z",
        )

        # Format 6: Check if microseconds matter
        await _test_datetime_format_helper(
            api,
            "With microseconds",
            f"{today}T14:30:00.000000Z",
            f"{today}T15:30:00.000000Z",
        )

    print("\n" + "=" * 80)
    print("Tests Complete")
    print("=" * 80)


if __name__ == "__main__":
    required_vars = [
        "INFORM_CLIENT_ID",
        "INFORM_CLIENT_SECRET",
        "INFORM_LICENSE",
        "INFORM_USER",
        "INFORM_PASSWORD",
    ]

    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        print(f"Error: Missing required environment variables: {', '.join(missing)}")
        exit(1)

    asyncio.run(main())
