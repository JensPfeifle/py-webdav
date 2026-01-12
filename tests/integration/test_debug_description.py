#!/usr/bin/env python3
"""Test debug info in description."""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

sys.path.insert(0, '/home/user/py-webdav')

from py_webdav.caldav import InformCalDAVBackend


async def test_debug_info():
    """Test that debug info is added to description."""
    print("=" * 80)
    print("TEST: Debug Info in Description")
    print("=" * 80)

    backend = InformCalDAVBackend(owner_key="INFO", debug=False)
    request = Mock()
    calendar_path = "/calendars/INFO/default/"

    try:
        start_date = datetime.now(UTC).date()
        end_date = start_date + timedelta(days=7)

        # Create a recurring event
        ical_create = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-debug-{start_date}
SUMMARY:Test Event
DESCRIPTION:Original description
DTSTART:{start_date.strftime('%Y%m%d')}T100000Z
DTEND:{start_date.strftime('%Y%m%d')}T110000Z
RRULE:FREQ=DAILY;INTERVAL=1;UNTIL={end_date.strftime('%Y%m%d')}T235959Z
END:VEVENT
END:VCALENDAR"""

        print("\n1. Creating recurring event")
        object_path = f"{calendar_path}test-debug-{start_date}.ics"
        created = await backend.put_calendar_object(request, object_path, ical_create)
        event_key = backend._parse_object_path(created.path)

        print(f"✓ Created event with key: {event_key}")

        # Retrieve the event
        print("\n2. Retrieving event to check debug info")
        retrieved = await backend.get_calendar_object(request, created.path)

        print("\n" + "=" * 80)
        print("RETRIEVED ICALENDAR DATA:")
        print("=" * 80)
        print(retrieved.data)

        # Parse and check description
        from icalendar import Calendar as iCalendar
        cal = iCalendar.from_ical(retrieved.data)
        for component in cal.walk():
            if component.name == "VEVENT":
                description = component.get('description')
                rrule = component.get('rrule')

                print("\n" + "=" * 80)
                print("EXTRACTED DATA:")
                print("=" * 80)
                print(f"\nDescription:\n{description}")
                print(f"\nRRULE: {rrule}")

                # Check if debug info is present
                if description and "[DEBUG]" in str(description):
                    print("\n✅ Debug information is present in description")
                    if "Event ID" in str(description):
                        print("  ✓ Event ID found")
                    if "Event Mode" in str(description):
                        print("  ✓ Event Mode found")
                    if "Generated RRULE" in str(description):
                        print("  ✓ Generated RRULE found")
                else:
                    print("\n❌ Debug information missing!")

        # Cleanup
        await backend.delete_calendar_object(request, created.path)
        print(f"\n✓ Deleted event {event_key}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await backend.api_client.close()


if __name__ == "__main__":
    asyncio.run(test_debug_info())
