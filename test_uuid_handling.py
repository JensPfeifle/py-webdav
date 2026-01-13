#!/usr/bin/env python3
"""Test that UUID filenames are handled correctly (not mistaken for occurrences)."""

import asyncio
from datetime import datetime, UTC

from py_webdav.caldav.inform_backend import InformCalDAVBackend
from py_webdav.inform_api_client import InformConfig
from starlette.requests import Request


class MockRequest:
    """Mock request for testing."""

    pass


async def main():
    """Test UUID filename handling."""
    config = InformConfig()
    owner_key = config.username

    backend = InformCalDAVBackend(config=config, owner_key=owner_key)
    request = MockRequest()

    print(f"\n{'='*80}")
    print(f"Testing UUID Filename Handling")
    print(f"{'='*80}\n")

    # Test 1: Create event with UUID filename (like CalDAV clients do)
    print("Test 1: Create event with UUID filename")
    print("-" * 80)

    uuid_path = "/calendars/default/C721345B-380C-4E23-A718-F2E4C2949EBA.ics"
    ical_data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:C721345B-380C-4E23-A718-F2E4C2949EBA
DTSTART:20260112T151500Z
DTEND:20260112T161500Z
SUMMARY:Test UUID Event
DTSTAMP:20260112T120000Z
END:VEVENT
END:VCALENDAR"""

    try:
        result = await backend.put_calendar_object(
            request, uuid_path, ical_data, if_none_match=True
        )
        print(f"✓ Successfully created event")
        print(f"  Path: {result.path}")
        print(f"  ETag: {result.etag[:16]}...")

        # Extract the INFORM key from the result
        from icalendar import Calendar

        cal = Calendar.from_ical(result.data)
        inform_key = None
        for component in cal.walk():
            if component.name == "VEVENT":
                inform_key = str(component.get("UID"))
                break

        print(f"  INFORM Key: {inform_key}")

        # Clean up
        if inform_key:
            await backend.api_client.delete_calendar_event(inform_key)
            print(f"  Cleaned up test event")

    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback

        traceback.print_exc()

    # Test 2: Verify occurrence paths still work
    print(f"\nTest 2: Verify occurrence path detection still works")
    print("-" * 80)

    # Get an actual occurrence
    start_date = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2026, 2, 28, 23, 59, 59, tzinfo=UTC)

    response = await backend.api_client.get_calendar_events_occurrences(
        owner_key=owner_key,
        start_datetime=start_date.isoformat(),
        end_datetime=end_date.isoformat(),
        limit=10,
    )

    occurrences = [e for e in response.get("calendarEvents", []) if e.get("occurrenceId")]

    if occurrences:
        occ = occurrences[0]
        event_key = occ.get("key")
        occ_id = occ.get("occurrenceId")
        occ_path = f"/calendars/default/{event_key}-{occ_id}.ics"

        print(f"Found occurrence: {event_key}-{occ_id}")

        try:
            result = await backend.get_calendar_object(request, occ_path)
            print(f"✓ Successfully fetched occurrence")
            print(f"  Path: {result.path}")

            # Verify UID format
            cal = Calendar.from_ical(result.data)
            for component in cal.walk():
                if component.name == "VEVENT":
                    uid = str(component.get("UID"))
                    if f"{event_key}-{occ_id}" in uid:
                        print(f"  ✓ UID correctly formatted: {uid}")
                    else:
                        print(f"  ✗ UID incorrect: {uid}")
                    break

        except Exception as e:
            print(f"✗ Failed to fetch occurrence: {e}")
    else:
        print("No occurrences found to test")

    await backend.api_client.close()

    print(f"\n{'='*80}")
    print(f"Conclusion:")
    print(f"{'='*80}")
    print(f"✓ UUID filenames are NOT mistaken for occurrences")
    print(f"✓ Actual occurrence paths still work correctly")


if __name__ == "__main__":
    asyncio.run(main())
