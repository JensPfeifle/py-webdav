#!/usr/bin/env python3
"""Verify that fetching full event includes all necessary fields for RRULE."""

import asyncio
import json
import os
from datetime import datetime, timedelta, UTC

from py_webdav.inform_api_client import InformAPIClient, InformConfig


async def main():
    """Verify full event fetch includes eventMode and seriesSchema."""
    config = InformConfig()
    owner_key = os.getenv("INFORM_OWNER_KEY", config.username).strip('"')

    client = InformAPIClient(config)

    # Get date range (next 30 days)
    start_date = datetime.now(UTC)
    end_date = start_date + timedelta(days=30)

    print(f"\n{'='*80}")
    print(f"Step 1: Fetch occurrences (what list_calendar_objects does)")
    print(f"{'='*80}\n")

    # Fetch occurrences
    response = await client.get_calendar_events_occurrences(
        owner_key=owner_key,
        start_datetime=start_date.isoformat(),
        end_datetime=end_date.isoformat(),
        limit=1000,
    )

    events = response.get("calendarEvents", [])
    print(f"Total occurrences: {len(events)}")

    # Get first series event
    series_event = None
    for event in events:
        if event.get("occurrenceId"):
            series_event = event
            break

    if not series_event:
        print("No series events found!")
        return

    event_key = series_event.get("key")
    occ_id = series_event.get("occurrenceId")

    print(f"\nFound series event:")
    print(f"  Key: {event_key}")
    print(f"  Occurrence ID: {occ_id}")
    print(f"  Subject: {series_event.get('subject')}")
    print(f"\nFields in occurrence response:")
    print(f"  eventMode: '{series_event.get('eventMode', 'MISSING')}'")
    print(f"  seriesSchema: {series_event.get('seriesSchema', 'MISSING')}")

    print(f"\n{'='*80}")
    print(f"Step 2: Fetch full event with fields=['all']")
    print(f"{'='*80}\n")

    # Fetch full event
    full_event = await client.get_calendar_event(event_key, fields=["all"])

    print(f"Full event fields:")
    print(f"  Key: {full_event.get('key')}")
    print(f"  Subject: {full_event.get('subject')}")
    print(f"  Event Mode: '{full_event.get('eventMode')}'")
    print(f"  Series Start Date: {full_event.get('seriesStartDate')}")
    print(f"  Series End Date: {full_event.get('seriesEndDate')}")
    print(f"  Occurrence Start Time: {full_event.get('occurrenceStartTime')}")
    print(f"  Occurrence End Time: {full_event.get('occurrenceEndTime')}")
    print(f"  Whole Day Event: {full_event.get('wholeDayEvent')}")

    series_schema = full_event.get('seriesSchema')
    if series_schema:
        print(f"\n  Series Schema:")
        print(f"    {json.dumps(series_schema, indent=4)}")
    else:
        print(f"\n  Series Schema: MISSING!")

    print(f"\n{'='*80}")
    print(f"VERIFICATION:")
    print(f"{'='*80}\n")

    required_fields = [
        ("eventMode", full_event.get("eventMode")),
        ("seriesSchema", full_event.get("seriesSchema")),
        ("seriesStartDate", full_event.get("seriesStartDate")),
        ("occurrenceStartTime", full_event.get("occurrenceStartTime")),
        ("occurrenceEndTime", full_event.get("occurrenceEndTime")),
    ]

    all_present = True
    for field_name, field_value in required_fields:
        if field_value:
            print(f"✓ {field_name}: Present")
        else:
            print(f"✗ {field_name}: MISSING!")
            all_present = False

    if all_present:
        print(f"\n✓ All required fields are present!")
        print(f"  Current implementation should work correctly.")
    else:
        print(f"\n✗ Some required fields are missing!")
        print(f"  This could cause issues with RRULE generation.")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
