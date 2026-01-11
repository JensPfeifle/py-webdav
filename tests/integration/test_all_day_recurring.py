#!/usr/bin/env python3
"""Test all-day recurring event to see the error."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

from py_webdav.inform_api_client import InformAPIClient, InformConfig


async def test():
    """Test all-day recurring event."""
    config = InformConfig()
    client = InformAPIClient(config)

    try:
        start_date = datetime.now(UTC).date()

        # Create recurring all-day event
        # Test 1: Without time fields
        event_data_no_times = {
            "eventMode": "serial",
            "subject": "Recurring All-Day Event (No Times)",
            "ownerKey": config.username,
            "seriesStartDate": start_date.strftime("%Y-%m-%d"),
            "wholeDayEvent": True,
            "seriesSchema": {
                "schemaType": "daily",
                "dailySchemaData": {"regularity": "interval", "daysInterval": 1},
            },
            "seriesEndDate": (start_date + timedelta(days=4)).strftime("%Y-%m-%d"),
        }

        print("Test 1: Without time fields")
        print(json.dumps(event_data_no_times, indent=2))

        try:
            created = await client.create_calendar_event(event_data_no_times)
            print(f"\n✓ Success! Created event: {created['key']}")
            await client.delete_calendar_event(created["key"])
        except Exception as e:
            print(f"\n✗ Failed: {e}")
            if hasattr(e, "response"):
                print(f"Response: {e.response.text}")  # type: ignore

        # Test 2: With time fields
        event_data_with_times = {
            "eventMode": "serial",
            "subject": "Recurring All-Day Event (With Times)",
            "ownerKey": config.username,
            "seriesStartDate": start_date.strftime("%Y-%m-%d"),
            "occurrenceStartTime": 0,  # Midnight
            "occurrenceStartTimeEnabled": True,
            "occurrenceEndTime": 86340,  # End of day
            "occurrenceEndTimeEnabled": True,
            "wholeDayEvent": True,
            "seriesSchema": {
                "schemaType": "daily",
                "dailySchemaData": {"regularity": "interval", "daysInterval": 1},
            },
            "seriesEndDate": (start_date + timedelta(days=4)).strftime("%Y-%m-%d"),
        }

        print("\n\nTest 2: With time fields")
        print(json.dumps(event_data_with_times, indent=2))

        created = await client.create_calendar_event(event_data_with_times)
        print(f"\nSuccess! Created event: {created['key']}")

        # Cleanup
        await client.delete_calendar_event(created["key"])

    except Exception as e:
        print(f"\nError: {e}")
        if hasattr(e, "response"):
            print(f"Response: {e.response.text}")  # type: ignore
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(test())
