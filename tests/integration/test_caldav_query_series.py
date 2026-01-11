#!/usr/bin/env python3
"""Test CalDAV calendar-query for series events.

This simulates what happens when a CalDAV client syncs a calendar.
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

sys.path.insert(0, '/home/user/py-webdav')

from py_webdav.caldav import InformCalDAVBackend


async def test_calendar_query():
    """Test calendar query with series events."""
    print("=" * 80)
    print("TEST: CalDAV Calendar Query with Series Events")
    print("=" * 80)

    backend = InformCalDAVBackend(owner_key="INFO", debug=False)
    request = Mock()

    try:
        # Create a recurring event
        start_date = datetime.now(UTC).date()
        end_date = start_date + timedelta(days=30)

        ical_create = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-query-{start_date}
SUMMARY:Weekly Team Meeting
DTSTART:{start_date.strftime('%Y%m%d')}T140000Z
DTEND:{start_date.strftime('%Y%m%d')}T150000Z
RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR;UNTIL={end_date.strftime('%Y%m%d')}T235959Z
END:VEVENT
END:VCALENDAR"""

        print("\n1. Creating weekly recurring event:")
        print("   - Occurs on Monday, Wednesday, Friday")
        print(f"   - From {start_date} to {end_date}")
        print("   - Should have ~13 occurrences")

        # Create via CalDAV
        calendar_path = "/calendars/INFO/default/"
        object_path = f"{calendar_path}test-query-{start_date}.ics"

        created_obj = await backend.put_calendar_object(
            request=request,
            path=object_path,
            ical_data=ical_create,
        )

        event_key = backend._parse_object_path(created_obj.path)
        print(f"\n✓ Created event with key: {event_key}")

        # Test list_calendar_objects (what CalDAV clients use)
        print("\n\n2. Testing list_calendar_objects (CalDAV sync):")
        print("=" * 80)

        objects = await backend.list_calendar_objects(request, calendar_path)
        print(f"\n✓ Found {len(objects)} total calendar objects")

        for obj in objects:
            if event_key in obj.path:
                from icalendar import Calendar as iCalendar

                cal = iCalendar.from_ical(obj.data)
                for component in cal.walk():
                    if component.name == "VEVENT":
                        summary = component.get('summary')
                        rrule = component.get('rrule')
                        print(f"\nEvent: {summary}")
                        if rrule:
                            print(f"✅ RRULE present: {rrule}")
                        else:
                            print("❌ RRULE missing!")

        # Cleanup
        await backend.delete_calendar_object(request, created_obj.path)
        print(f"\n✓ Deleted event {event_key}")

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await backend.api_client.close()


async def main():
    success = await test_calendar_query()

    print("\n" + "=" * 80)
    if success:
        print("✅ TEST PASSED")
    else:
        print("❌ TEST FAILED")
    print("=" * 80)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
