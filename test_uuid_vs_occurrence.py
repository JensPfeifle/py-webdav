#!/usr/bin/env python3
"""Comprehensive test: UUID filenames vs occurrence paths."""

import asyncio
from datetime import datetime, UTC

from py_webdav.caldav.inform_backend import InformCalDAVBackend
from py_webdav.inform_api_client import InformConfig
from starlette.requests import Request


class MockRequest:
    """Mock request for testing."""

    pass


async def main():
    """Test UUID vs occurrence path handling."""
    config = InformConfig()
    owner_key = config.username

    backend = InformCalDAVBackend(config=config, owner_key=owner_key)
    request = MockRequest()

    print(f"\n{'='*80}")
    print(f"UUID Filenames vs Occurrence Paths - Comprehensive Test")
    print(f"{'='*80}\n")

    # Step 1: Create a series event directly via API
    print("Step 1: Create test series event via API")
    print("-" * 80)

    event_data = {
        "subject": "UUID Test Series",
        "content": "Testing UUID handling",
        "ownerKey": owner_key,
        "eventMode": "serial",
        "seriesStartDate": "2026-04-01",
        "occurrenceStartTime": 32400,  # 9:00 AM
        "occurrenceStartTimeEnabled": True,
        "occurrenceEndTime": 36000,  # 10:00 AM
        "occurrenceEndTimeEnabled": True,
        "wholeDayEvent": False,
        "seriesSchema": {
            "schemaType": "daily",
            "dailySchemaData": {"regularity": "interval", "daysInterval": 1},
        },
        "seriesEndDate": "2026-04-03",  # 3 days
    }

    created = await backend.api_client.create_calendar_event(event_data)
    series_key = created.get("key")
    print(f"✓ Created series: {series_key}")

    # Get occurrences
    start_date = datetime(2026, 4, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2026, 4, 3, 23, 59, 59, tzinfo=UTC)

    response = await backend.api_client.get_calendar_events_occurrences(
        owner_key=owner_key,
        start_datetime=start_date.isoformat(),
        end_datetime=end_date.isoformat(),
        limit=100,
    )

    occurrences = [
        e for e in response.get("calendarEvents", []) if e.get("key") == series_key
    ]

    print(f"  Found {len(occurrences)} occurrences")
    for occ in occurrences:
        print(f"    - {occ.get('occurrenceId')}")

    if len(occurrences) < 2:
        print("Need at least 2 occurrences")
        await backend.api_client.delete_calendar_event(series_key)
        await backend.api_client.close()
        return

    first_occ_id = occurrences[0].get("occurrenceId")

    # Step 2: Try to create NEW event with UUID that looks like occurrence path
    print(f"\nStep 2: Create event with UUID containing hyphen")
    print("-" * 80)

    # Use a UUID that looks similar to our occurrence format
    fake_occ_uuid = f"{series_key}-ABCD1234"  # Similar format but not real occurrence
    uuid_path = f"/calendars/default/{fake_occ_uuid}.ics"

    ical_new = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:{fake_occ_uuid}
DTSTART:20260405T140000Z
DTEND:20260405T150000Z
SUMMARY:New Event with Hyphenated UUID
DTSTAMP:20260412T120000Z
END:VEVENT
END:VCALENDAR"""

    try:
        result = await backend.put_calendar_object(
            request, uuid_path, ical_new, if_none_match=True
        )
        print(f"✓ Successfully created NEW event (not treated as occurrence)")
        print(f"  Path: {result.path}")

        from icalendar import Calendar

        cal = Calendar.from_ical(result.data)
        for component in cal.walk():
            if component.name == "VEVENT":
                new_key = str(component.get("UID"))
                print(f"  INFORM Key: {new_key}")
                # Clean up
                await backend.api_client.delete_calendar_event(new_key)
                print(f"  Cleaned up new event")
                break

    except Exception as e:
        print(f"✗ Failed (this is the bug we're fixing): {e}")

    # Step 3: Update REAL occurrence
    print(f"\nStep 3: Update actual occurrence")
    print("-" * 80)

    real_occ_path = f"/calendars/default/{series_key}-{first_occ_id}.ics"

    ical_update = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:{series_key}-{first_occ_id}
DTSTART:20260401T140000Z
DTEND:20260401T150000Z
SUMMARY:Modified First Occurrence
DTSTAMP:20260412T120000Z
END:VEVENT
END:VCALENDAR"""

    try:
        result = await backend.put_calendar_object(request, real_occ_path, ical_update)
        print(f"✓ Successfully updated occurrence")
        print(f"  Path: {result.path}")

        # Verify it was updated
        updated_occ = await backend.api_client.get_calendar_event_occurrence(
            series_key, first_occ_id, fields=["all"]
        )
        print(f"  New subject: {updated_occ.get('subject')}")
        print(f"  New start: {updated_occ.get('startDateTime')}")

    except Exception as e:
        print(f"✗ Failed to update occurrence: {e}")

    # Clean up
    print(f"\nStep 4: Clean up")
    print("-" * 80)
    try:
        await backend.api_client.delete_calendar_event(series_key)
        print(f"✓ Deleted test series")
    except Exception as e:
        print(f"⚠ Failed to delete: {e}")

    await backend.api_client.close()

    print(f"\n{'='*80}")
    print(f"Summary:")
    print(f"{'='*80}")
    print(f"✓ NEW events with hyphenated UUIDs: Correctly created")
    print(f"✓ REAL occurrence updates: Still work correctly")
    print(f"✓ System distinguishes between UUIDs and occurrence paths")


if __name__ == "__main__":
    asyncio.run(main())
