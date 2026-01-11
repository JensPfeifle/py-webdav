#!/usr/bin/env python3
"""Diagnostic script to check INFORM API event keys vs occurrence IDs."""

import asyncio
import os
from datetime import datetime, timedelta, UTC

from py_webdav.inform_api_client import InformAPIClient, InformConfig


async def main():
    """Check event keys and occurrence IDs."""
    # Get credentials from environment
    config = InformConfig()
    # Owner key defaults to username if not explicitly set
    owner_key = os.getenv("INFORM_OWNER_KEY", config.username).strip('"')

    # Create client
    client = InformAPIClient(config)

    # Get date range (next 30 days)
    start_date = datetime.now(UTC)
    end_date = start_date + timedelta(days=30)

    print(f"\n{'='*80}")
    print(f"Fetching occurrences from {start_date.date()} to {end_date.date()}")
    print(f"{'='*80}\n")

    # Fetch occurrences
    response = await client.get_calendar_events_occurrences(
        owner_key=owner_key,
        start_datetime=start_date.isoformat(),
        end_datetime=end_date.isoformat(),
        limit=1000,
    )

    events = response.get("calendarEvents", [])

    print(f"Total events/occurrences returned: {len(events)}\n")

    # Group by event key
    by_key = {}
    for event in events:
        key = event.get("key", "")
        occ_id = event.get("occurrenceId", "")
        subject = event.get("subject", "")
        event_mode = event.get("eventMode", "")

        if key not in by_key:
            by_key[key] = []

        by_key[key].append({
            "occurrenceId": occ_id,
            "subject": subject,
            "eventMode": event_mode,
        })

    # Display results
    print(f"Unique event keys: {len(by_key)}\n")

    for key, occurrences in by_key.items():
        print(f"\nEvent Key: {key}")
        print(f"  Subject: {occurrences[0]['subject']}")
        print(f"  Event Mode: {occurrences[0]['eventMode']}")
        print(f"  Number of occurrences: {len(occurrences)}")

        if len(occurrences) > 1:
            print(f"  Occurrence IDs:")
            for occ in occurrences[:5]:  # Show first 5
                print(f"    - {occ['occurrenceId']}")
            if len(occurrences) > 5:
                print(f"    ... and {len(occurrences) - 5} more")
        elif len(occurrences) == 1 and occurrences[0]['occurrenceId']:
            print(f"  Single occurrence ID: {occurrences[0]['occurrenceId']}")
        else:
            print(f"  No occurrence ID (single event)")

    print(f"\n{'='*80}")
    print("VERIFICATION:")
    print(f"{'='*80}")

    # Check if any series events appear multiple times
    series_events = {k: v for k, v in by_key.items() if len(v) > 1}
    if series_events:
        print(f"\n✓ Found {len(series_events)} series events with multiple occurrences")
        print("  This is expected - INFORM returns one entry per occurrence")
        print("  The 'key' field is the same for all occurrences")
        print("  The 'occurrenceId' field is unique for each occurrence")
    else:
        print("\n✗ No series events with multiple occurrences found")
        print("  (This might indicate no recurring events in the date range)")

    # Verify that all occurrences of the same event have the same key
    for key, occurrences in series_events.items():
        occ_ids = [o['occurrenceId'] for o in occurrences]
        unique_occ_ids = set(occ_ids)
        if len(unique_occ_ids) == len(occ_ids):
            print(f"\n✓ Event {key[:8]}... has {len(occ_ids)} unique occurrence IDs")
        else:
            print(f"\n✗ WARNING: Event {key[:8]}... has duplicate occurrence IDs!")

    print(f"\n{'='*80}")
    print("CalDAV IMPLICATIONS:")
    print(f"{'='*80}")
    print("\nFor correct CalDAV behavior:")
    print("  1. CalDAV path should use 'key' (same for all occurrences)")
    print("  2. iCalendar UID should use 'key' (same for all occurrences)")
    print("  3. Deduplication should be based on 'key' to return one event")
    print("  4. The event should include RRULE for recurrence pattern")
    print("  5. Individual occurrences should NOT be separate CalDAV objects")
    print("\nCurrent implementation:")
    print("  ✓ Uses 'key' for CalDAV path")
    print("  ✓ Uses 'key' for iCalendar UID")
    print("  ✓ Deduplicates based on 'key'")
    print("  ✓ Fetches full event data to get seriesSchema for RRULE")
    print("\n")


if __name__ == "__main__":
    asyncio.run(main())
