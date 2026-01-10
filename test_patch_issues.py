#!/usr/bin/env python3
"""Enhanced test script to investigate INFORM API PATCH and time issues.

This script tests:
1. Why event times are reset to midnight on CREATE
2. What happens with minimal PATCH requests
3. CalDAV update scenario simulation
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

    def _get_headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    async def create_event(self, event_data):
        response = await self.http_client.post(
            "/calendarEvents", json=event_data, headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()

    async def get_event(self, event_key):
        response = await self.http_client.get(
            f"/calendarEvents/{event_key}",
            params={"fields": "all"},
            headers=self._get_headers(),
        )
        response.raise_for_status()
        return response.json()

    async def patch_event(self, event_key, patch_data):
        response = await self.http_client.patch(
            f"/calendarEvents/{event_key}", json=patch_data, headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()

    async def delete_event(self, event_key):
        response = await self.http_client.delete(
            f"/calendarEvents/{event_key}", headers=self._get_headers()
        )
        response.raise_for_status()


def print_section(title):
    """Print a section header."""
    print(f"\n{'=' * 80}")
    print(title)
    print("=" * 80)


async def test_time_issue():
    """Test why times are being reset to midnight."""
    print_section("TEST 1: Time Reset Issue on CREATE")

    async with InformAPITest() as api:
        now = datetime.now(UTC)
        start_time = now.replace(hour=14, minute=30, second=0, microsecond=0)
        end_time = start_time + timedelta(hours=1)

        print(f"\nCreating event with times:")
        print(f"  Start: {start_time.isoformat()} (14:30:00)")
        print(f"  End:   {end_time.isoformat()} (15:30:00)")

        # Test 1a: With wholeDayEvent explicitly set to False
        event_data = {
            "eventMode": "single",
            "subject": "Test Time Issue",
            "ownerKey": api.username,
            "startDateTime": start_time.isoformat(),
            "endDateTime": end_time.isoformat(),
            "startDateTimeEnabled": True,
            "endDateTimeEnabled": True,
            "wholeDayEvent": False,
        }

        print(f"\nCreating event with wholeDayEvent=False...")
        created = await api.create_event(event_data)
        event_key = created["key"]

        fetched = await api.get_event(event_key)
        print(f"\nRetrieved event:")
        print(f"  Start: {fetched.get('startDateTime')} (expected 14:30:00)")
        print(f"  End:   {fetched.get('endDateTime')} (expected 15:30:00)")
        print(f"  wholeDayEvent: {fetched.get('wholeDayEvent')}")

        if "T14:30:00" in fetched.get("startDateTime", ""):
            print("✓ Times preserved correctly!")
        else:
            print("✗ Times were modified!")

        await api.delete_event(event_key)


async def test_minimal_patch():
    """Test minimal PATCH requests."""
    print_section("TEST 2: Minimal PATCH Requests")

    async with InformAPITest() as api:
        now = datetime.now(UTC)
        start_time = now.replace(hour=14, minute=30, second=0, microsecond=0)
        end_time = start_time + timedelta(hours=1)

        # Create event
        event_data = {
            "eventMode": "single",
            "subject": "Test PATCH",
            "ownerKey": api.username,
            "startDateTime": start_time.isoformat(),
            "endDateTime": end_time.isoformat(),
            "startDateTimeEnabled": True,
            "endDateTimeEnabled": True,
            "wholeDayEvent": False,
        }

        created = await api.create_event(event_data)
        event_key = created["key"]
        print(f"Created event: {event_key}")

        original = await api.get_event(event_key)
        print(f"\nOriginal event:")
        print(f"  Subject: {original.get('subject')}")
        print(f"  Start: {original.get('startDateTime')}")
        print(f"  End: {original.get('endDateTime')}")

        # Test 2a: PATCH with eventMode only
        print(f"\n--- Test 2a: PATCH with eventMode='single' ---")
        try:
            patch_data = {"eventMode": "single"}
            print(f"PATCH payload: {json.dumps(patch_data)}")
            await api.patch_event(event_key, patch_data)

            updated = await api.get_event(event_key)
            print(f"After PATCH:")
            print(f"  Subject: {updated.get('subject')}")
            print(f"  Start: {updated.get('startDateTime')}")
            print(f"  End: {updated.get('endDateTime')}")

            if original.get("startDateTime") != updated.get("startDateTime"):
                print("⚠️  WARNING: Times changed after PATCH with eventMode!")
            else:
                print("✓ Times unchanged")
        except Exception as e:
            print(f"✗ PATCH failed: {e}")

        # Test 2b: PATCH with subject change
        print(f"\n--- Test 2b: PATCH with subject change ---")
        try:
            patch_data = {"subject": "Updated Subject"}
            print(f"PATCH payload: {json.dumps(patch_data)}")
            await api.patch_event(event_key, patch_data)

            updated = await api.get_event(event_key)
            print(f"After PATCH:")
            print(f"  Subject: {updated.get('subject')}")
            print(f"  Start: {updated.get('startDateTime')}")
            print(f"  End: {updated.get('endDateTime')}")

            if original.get("startDateTime") != updated.get("startDateTime"):
                print("⚠️  WARNING: Times changed after subject update!")
            else:
                print("✓ Times unchanged")
        except Exception as e:
            print(f"✗ PATCH failed: {e}")

        await api.delete_event(event_key)


async def test_caldav_scenario():
    """Simulate CalDAV update scenario."""
    print_section("TEST 3: CalDAV Update Scenario")

    async with InformAPITest() as api:
        now = datetime.now(UTC)
        start_time = now.replace(hour=14, minute=30, second=0, microsecond=0)
        end_time = start_time + timedelta(hours=1)

        # Step 1: Create event (like CalDAV PUT)
        print("Step 1: Create event via CalDAV-style PUT")
        event_data = {
            "eventMode": "single",
            "subject": "CalDAV Test Event",
            "ownerKey": api.username,
            "content": "Original description",
            "startDateTime": start_time.isoformat(),
            "endDateTime": end_time.isoformat(),
            "startDateTimeEnabled": True,
            "endDateTimeEnabled": True,
            "wholeDayEvent": False,
        }

        created = await api.create_event(event_data)
        event_key = created["key"]

        original = await api.get_event(event_key)
        print(f"\nCreated event {event_key}:")
        print(f"  Subject: {original.get('subject')}")
        print(f"  Content: {original.get('content')}")
        print(f"  Start: {original.get('startDateTime')}")

        # Step 2: Update via CalDAV (client sends full event)
        # In CalDAV backend, we convert iCal to INFORM format and PATCH
        print(f"\nStep 2: Update event (changing only description)")
        print("CalDAV client sends full iCal, backend converts and PATCHes")

        # What CalDAV backend might send as PATCH
        patch_data = {
            "eventMode": "single",
            "subject": "CalDAV Test Event",  # Same
            "content": "UPDATED description",  # Changed
            "startDateTime": original.get("startDateTime"),  # Same
            "endDateTime": original.get("endDateTime"),  # Same
            "startDateTimeEnabled": True,
            "endDateTimeEnabled": True,
        }

        print(f"\nPATCH payload (CalDAV-style):")
        print(json.dumps(patch_data, indent=2))

        try:
            await api.patch_event(event_key, patch_data)
            updated = await api.get_event(event_key)

            print(f"\nAfter CalDAV update:")
            print(f"  Subject: {updated.get('subject')}")
            print(f"  Content: {updated.get('content')}")
            print(f"  Start: {updated.get('startDateTime')}")

            if original.get("startDateTime") != updated.get("startDateTime"):
                print("\n⚠️  WARNING: Times changed in CalDAV update!")
                print(f"  Original: {original.get('startDateTime')}")
                print(f"  Updated:  {updated.get('startDateTime')}")
            else:
                print("\n✓ Times preserved correctly!")
        except Exception as e:
            print(f"✗ CalDAV update failed: {e}")

        await api.delete_event(event_key)


async def main():
    """Run all tests."""
    print("=" * 80)
    print("INFORM API PATCH and Time Issues Investigation")
    print("=" * 80)

    await test_time_issue()
    await test_minimal_patch()
    await test_caldav_scenario()

    print_section("All Tests Complete")


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
