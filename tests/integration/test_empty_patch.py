#!/usr/bin/env python3
"""Test script to reproduce empty PATCH request issue with INFORM API.

This script:
1. Creates a calendar event with specific start/end times
2. Verifies the event was created correctly
3. Sends an empty PATCH request (simulating CalDAV edit behavior)
4. Checks if the event times were reset/modified

Requirements:
- INFORM_CLIENT_ID, INFORM_CLIENT_SECRET, INFORM_LICENSE, INFORM_USER, INFORM_PASSWORD
  environment variables must be set
"""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta

import httpx


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
        """Authenticate and get access token."""
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
        print("✓ Authenticated successfully")

    def _get_headers(self):
        """Get headers with authorization."""
        return {"Authorization": f"Bearer {self.access_token}"}

    async def create_event(self, event_data):
        """Create a calendar event."""
        assert self.http_client
        response = await self.http_client.post(
            "/calendarEvents", json=event_data, headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()

    async def get_event(self, event_key):
        """Get a calendar event with all fields."""
        assert self.http_client
        response = await self.http_client.get(
            f"/calendarEvents/{event_key}",
            params={"fields": "all"},
            headers=self._get_headers(),
        )
        response.raise_for_status()
        return response.json()

    async def patch_event(self, event_key, patch_data):
        """Patch a calendar event."""
        assert self.http_client
        response = await self.http_client.patch(
            f"/calendarEvents/{event_key}", json=patch_data, headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()

    async def delete_event(self, event_key):
        """Delete a calendar event."""
        assert self.http_client
        response = await self.http_client.delete(
            f"/calendarEvents/{event_key}", headers=self._get_headers()
        )
        response.raise_for_status()


def print_event_times(event_data, label):
    """Print event start/end times in a readable format."""
    print(f"\n{label}:")
    print(f"  Event Key: {event_data.get('key', 'N/A')}")
    print(f"  Event Mode: {event_data.get('eventMode', 'N/A')}")

    if event_data.get("eventMode") == "single":
        print(f"  Start: {event_data.get('startDateTime', 'N/A')}")
        print(f"  End: {event_data.get('endDateTime', 'N/A')}")
        print(f"  Start Enabled: {event_data.get('startDateTimeEnabled', 'N/A')}")
        print(f"  End Enabled: {event_data.get('endDateTimeEnabled', 'N/A')}")

    print(f"  Subject: {event_data.get('subject', 'N/A')}")
    print(f"  Owner: {event_data.get('ownerKey', 'N/A')}")


async def test_empty_patch():
    """Test empty PATCH request behavior."""
    print("=" * 80)
    print("INFORM API Empty PATCH Test")
    print("=" * 80)

    async with InformAPITest() as api:
        # Step 1: Create an event with specific times
        now = datetime.now(UTC)
        start_time = now + timedelta(hours=2)
        end_time = start_time + timedelta(hours=1)

        event_data = {
            "eventMode": "single",
            "subject": "Test Empty PATCH",
            "ownerKey": api.username,
            "startDateTime": start_time.isoformat(),
            "endDateTime": end_time.isoformat(),
            "startDateTimeEnabled": True,
            "endDateTimeEnabled": True,
            "content": "Testing empty PATCH request behavior",
        }

        print("\n" + "=" * 80)
        print("Step 1: Creating event")
        print("=" * 80)
        print("Request payload:")
        print(json.dumps(event_data, indent=2))

        created = await api.create_event(event_data)
        event_key = created["key"]
        print(f"\n✓ Event created with key: {event_key}")

        # Step 2: Fetch the event to verify it was created correctly
        print("\n" + "=" * 80)
        print("Step 2: Fetching created event (with all fields)")
        print("=" * 80)

        original_event = await api.get_event(event_key)
        print_event_times(original_event, "Original Event")

        # Step 3: Send an empty PATCH request
        print("\n" + "=" * 80)
        print("Step 3: Sending empty PATCH request")
        print("=" * 80)

        empty_patch = {}
        print(f"Patch payload: {json.dumps(empty_patch)}")

        try:
            patched = await api.patch_event(event_key, empty_patch)
            print("\n✓ PATCH request succeeded")
            print("Response:")
            print(json.dumps(patched, indent=2))
        except httpx.HTTPStatusError as e:
            print(f"\n✗ PATCH request failed: {e}")
            print(f"Response body: {e.response.text}")
            # Cleanup and exit
            await api.delete_event(event_key)
            return
        except Exception as e:
            print(f"\n✗ PATCH request failed: {e}")
            # Cleanup and exit
            await api.delete_event(event_key)
            return

        # Step 4: Fetch the event again to see if times were reset
        print("\n" + "=" * 80)
        print("Step 4: Fetching event after empty PATCH")
        print("=" * 80)

        updated_event = await api.get_event(event_key)
        print_event_times(updated_event, "Event After Empty PATCH")

        # Step 5: Compare the events
        print("\n" + "=" * 80)
        print("Step 5: Comparison")
        print("=" * 80)

        original_start = original_event.get("startDateTime")
        original_end = original_event.get("endDateTime")
        updated_start = updated_event.get("startDateTime")
        updated_end = updated_event.get("endDateTime")

        print(f"\nOriginal Start: {original_start}")
        print(f"Updated Start:  {updated_start}")
        print(f"Start Changed:  {original_start != updated_start}")

        print(f"\nOriginal End:   {original_end}")
        print(f"Updated End:    {updated_end}")
        print(f"End Changed:    {original_end != updated_end}")

        if original_start != updated_start or original_end != updated_end:
            print("\n⚠️  WARNING: Event times were modified by empty PATCH!")
            print("\nThis confirms the issue: empty PATCH requests modify event times.")
        else:
            print("\n✓ Event times were NOT modified by empty PATCH")

        # Check other fields
        print("\nOther field changes:")
        for key in ["subject", "content", "ownerKey", "startDateTimeEnabled", "endDateTimeEnabled"]:
            original_val = original_event.get(key)
            updated_val = updated_event.get(key)
            if original_val != updated_val:
                print(f"  {key}: {original_val} → {updated_val}")

        # Cleanup
        print("\n" + "=" * 80)
        print("Cleanup: Deleting test event")
        print("=" * 80)
        await api.delete_event(event_key)
        print(f"✓ Event {event_key} deleted")

    print("\n" + "=" * 80)
    print("Test completed")
    print("=" * 80)


if __name__ == "__main__":
    # Check for required environment variables
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

    asyncio.run(test_empty_patch())
