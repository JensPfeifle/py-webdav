#!/usr/bin/env python3
"""Test what CalDAV clients see when retrieving a series event.

This script creates a series event and then retrieves it as a CalDAV client would.
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

sys.path.insert(0, '/home/user/py-webdav')

from py_webdav.caldav import InformCalDAVBackend


async def test_caldav_retrieval():
    """Test CalDAV retrieval of a series event."""
    print("=" * 80)
    print("TEST: CalDAV Series Event Retrieval")
    print("=" * 80)

    backend = InformCalDAVBackend(owner_key="INFO", debug=False)
    request = Mock()

    try:
        # Create a recurring event
        start_date = datetime.now(UTC).date()
        end_date = start_date + timedelta(days=14)

        ical_create = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-retrieval-{start_date}
SUMMARY:Daily Standup
DTSTART:{start_date.strftime('%Y%m%d')}T090000Z
DTEND:{start_date.strftime('%Y%m%d')}T091500Z
RRULE:FREQ=DAILY;INTERVAL=1;UNTIL={end_date.strftime('%Y%m%d')}T235959Z
END:VEVENT
END:VCALENDAR"""

        print("\n1. Creating event with RRULE:")
        print(ical_create)

        # Create via CalDAV
        calendar_path = "/calendars/INFO/default/"
        object_path = f"{calendar_path}test-retrieval-{start_date}.ics"

        created_obj = await backend.put_calendar_object(
            request=request,
            path=object_path,
            ical_data=ical_create,
        )

        event_key = backend._parse_object_path(created_obj.path)
        print(f"\n✓ Created event with key: {event_key}")

        # Retrieve via get_calendar_object (what CalDAV clients call)
        print("\n\n2. Retrieving via get_calendar_object:")
        retrieved_obj = await backend.get_calendar_object(request, created_obj.path)

        print("\nRetrieved iCalendar data:")
        print(retrieved_obj.data)

        # Parse and check
        from icalendar import Calendar as iCalendar

        cal = iCalendar.from_ical(retrieved_obj.data)
        event = None
        for component in cal.walk():
            if component.name == "VEVENT":
                event = component
                break

        if event:
            print("\n" + "=" * 80)
            print("VERIFICATION")
            print("=" * 80)
            print(f"✓ Summary: {event.get('summary')}")
            print(f"✓ DTSTART: {event.get('dtstart')}")
            print(f"✓ DTEND: {event.get('dtend')}")

            rrule = event.get('rrule')
            if rrule:
                print(f"✅ RRULE PRESENT: {rrule}")
                print("\nThis event should appear as recurring in CalDAV clients")
            else:
                print("❌ RRULE MISSING!")
                print("\nThis event will appear as a SINGLE event in CalDAV clients")
                print("\nDebugging - let's check the raw event data from INFORM API:")

                # Fetch directly from API
                event_data = await backend.api_client.get_calendar_event(
                    event_key, fields=["all"]
                )

                import json
                print("\nRaw INFORM event data:")
                print(json.dumps(event_data, indent=2))

                print("\nChecking critical fields:")
                print(f"  eventMode: {event_data.get('eventMode')}")
                print(f"  seriesSchema: {event_data.get('seriesSchema')}")
                print(f"  seriesStartDate: {event_data.get('seriesStartDate')}")
                print(f"  seriesEndDate: {event_data.get('seriesEndDate')}")

                return False

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
    success = await test_caldav_retrieval()

    print("\n" + "=" * 80)
    if success:
        print("✅ TEST PASSED - Series event properly returned to CalDAV client")
    else:
        print("❌ TEST FAILED - Series event NOT properly returned to CalDAV client")
    print("=" * 80)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
