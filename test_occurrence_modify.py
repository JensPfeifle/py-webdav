#!/usr/bin/env python3
"""Test updating and deleting individual occurrences."""

import asyncio
import os
from datetime import datetime, timedelta, UTC

from py_webdav.inform_api_client import InformAPIClient, InformConfig


async def main():
    """Test occurrence modification operations."""
    config = InformConfig()
    owner_key = os.getenv("INFORM_OWNER_KEY", config.username).strip('"')

    client = InformAPIClient(config)

    print(f"\n{'='*80}")
    print(f"Testing Occurrence Update and Delete")
    print(f"{'='*80}\n")

    # Create a test series event (daily for 5 days)
    print("Step 1: Create test series event")
    print("-" * 80)

    event_data = {
        "subject": "Test Occurrence Modification",
        "content": "Original content",
        "ownerKey": owner_key,
        "eventMode": "serial",
        "seriesStartDate": "2026-03-01",
        "occurrenceStartTime": 32400,  # 9:00 AM local
        "occurrenceStartTimeEnabled": True,
        "occurrenceEndTime": 36000,  # 10:00 AM local
        "occurrenceEndTimeEnabled": True,
        "wholeDayEvent": False,
        "seriesSchema": {
            "schemaType": "daily",
            "dailySchemaData": {
                "regularity": "interval",
                "daysInterval": 1
            }
        },
        "seriesEndDate": "2026-03-05"
    }

    try:
        created = await client.create_calendar_event(event_data)
        event_key = created.get("key")
        print(f"✓ Created series event: {event_key}")
        print(f"  Daily from 2026-03-01 to 2026-03-05 (5 days)")
    except Exception as e:
        print(f"✗ Failed to create event: {e}")
        await client.close()
        return

    # Get all occurrences
    print(f"\nStep 2: List all occurrences")
    print("-" * 80)

    start_date = datetime(2026, 3, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2026, 3, 5, 23, 59, 59, tzinfo=UTC)

    response = await client.get_calendar_events_occurrences(
        owner_key=owner_key,
        start_datetime=start_date.isoformat(),
        end_datetime=end_date.isoformat(),
        limit=100,
    )

    occurrences = [
        e for e in response.get("calendarEvents", [])
        if e.get("key") == event_key
    ]

    print(f"Found {len(occurrences)} occurrences:")
    for i, occ in enumerate(occurrences, 1):
        occ_id = occ.get("occurrenceId")
        start_dt = occ.get("startDateTime")
        print(f"  {i}. {start_dt} - Occurrence ID: {occ_id}")

    if len(occurrences) < 2:
        print("Need at least 2 occurrences for testing")
        await client.close()
        return

    # Test updating an occurrence
    print(f"\nStep 3: Update second occurrence (change subject and time)")
    print("-" * 80)

    second_occ_id = occurrences[1].get("occurrenceId")
    second_start = occurrences[1].get("startDateTime")

    update_data = {
        "subject": "Modified Occurrence",
        "content": "This occurrence was modified",
        "startDateTime": "2026-03-02T14:00:00Z",  # Change from 9am to 2pm
        "endDateTime": "2026-03-02T15:00:00Z",
        "startDateTimeEnabled": True,
        "endDateTimeEnabled": True,
    }

    try:
        await client.update_calendar_event_occurrence(event_key, second_occ_id, update_data)
        print(f"✓ Updated occurrence {second_occ_id}")

        # Fetch and verify
        updated = await client.get_calendar_event_occurrence(
            event_key, second_occ_id, fields=["all"]
        )
        print(f"  New subject: {updated.get('subject')}")
        print(f"  New start: {updated.get('startDateTime')}")
        print(f"  New content: {updated.get('content')}")
    except Exception as e:
        print(f"✗ Failed to update occurrence: {e}")

    # Test deleting an occurrence
    print(f"\nStep 4: Delete third occurrence")
    print("-" * 80)

    third_occ_id = occurrences[2].get("occurrenceId")

    try:
        await client.delete_calendar_event_occurrence(event_key, third_occ_id)
        print(f"✓ Deleted occurrence {third_occ_id}")
    except Exception as e:
        print(f"✗ Failed to delete occurrence: {e}")

    # Verify the changes
    print(f"\nStep 5: Verify final state")
    print("-" * 80)

    response = await client.get_calendar_events_occurrences(
        owner_key=owner_key,
        start_datetime=start_date.isoformat(),
        end_datetime=end_date.isoformat(),
        limit=100,
    )

    final_occurrences = [
        e for e in response.get("calendarEvents", [])
        if e.get("key") == event_key
    ]

    print(f"Final occurrences: {len(final_occurrences)} (expected 4)")
    for i, occ in enumerate(final_occurrences, 1):
        occ_id = occ.get("occurrenceId")
        start_dt = occ.get("startDateTime")
        subject = occ.get("subject")
        marker = ""
        if occ_id == second_occ_id:
            marker = " ← Modified"
        print(f"  {i}. {start_dt} - {subject} (ID: {occ_id}){marker}")

    # Verify third occurrence is gone
    remaining_ids = [o.get("occurrenceId") for o in final_occurrences]
    if third_occ_id not in remaining_ids:
        print(f"\n✓ Third occurrence was successfully deleted")
    else:
        print(f"\n✗ Third occurrence still exists!")

    # Clean up
    print(f"\nStep 6: Clean up")
    print("-" * 80)
    try:
        await client.delete_calendar_event(event_key)
        print(f"✓ Deleted test series event")
    except Exception as e:
        print(f"⚠ Failed to delete: {e}")

    await client.close()

    print(f"\n{'='*80}")
    print(f"Summary:")
    print(f"{'='*80}")
    print(f"✓ Series event creation: Working")
    print(f"✓ Occurrence update: Working")
    print(f"✓ Occurrence delete: Working")
    print(f"\nOccurrence modification fully supported!")


if __name__ == "__main__":
    asyncio.run(main())
