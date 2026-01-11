#!/usr/bin/env python3
"""Test series events through CalDAV backend workflow.

This script tests the full workflow:
1. Create a recurring event via CalDAV
2. List calendar objects (which uses occurrences API)
3. Verify the returned iCalendar has correct RRULE
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, '/home/user/py-webdav')

from unittest.mock import Mock

from py_webdav.caldav import InformCalDAVBackend


async def test_caldav_series_workflow():
    """Test creating and retrieving a series event through CalDAV."""
    print("=" * 80)
    print("TEST: CalDAV Series Event Workflow")
    print("=" * 80)

    backend = InformCalDAVBackend(owner_key="INFO", debug=False)

    # Create a mock request object
    request = Mock()

    try:
        # Create a recurring event in iCalendar format
        start_date = datetime.now(UTC).date()
        end_date = start_date + timedelta(days=14)

        ical_data = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-caldav-series-{start_date}
SUMMARY:Daily Standup
DESCRIPTION:Daily team standup
LOCATION:Office
DTSTART:{start_date.strftime('%Y%m%d')}T090000Z
DTEND:{start_date.strftime('%Y%m%d')}T091500Z
RRULE:FREQ=DAILY;INTERVAL=1;UNTIL={end_date.strftime('%Y%m%d')}T235959Z
CLASS:PUBLIC
END:VEVENT
END:VCALENDAR"""

        print("\n1. Creating recurring event via CalDAV put_calendar_object:")
        print(ical_data)

        # Create the event
        calendar_path = "/calendars/INFO/default/"
        object_path = f"{calendar_path}test-caldav-series-{start_date}.ics"

        created_obj = await backend.put_calendar_object(
            request=request,
            path=object_path,
            ical_data=ical_data,
        )

        event_key = backend._parse_object_path(created_obj.path)
        print(f"\n✓ Created event with key: {event_key}")
        print(f"✓ Object path: {created_obj.path}")

        # Retrieve the event directly via get_calendar_object
        print("\n\n2. Retrieving event via get_calendar_object:")
        retrieved_obj = await backend.get_calendar_object(request, created_obj.path)

        print("\nRetrieved iCalendar data:")
        print(retrieved_obj.data)

        # Parse and verify the RRULE is present
        from icalendar import Calendar as iCalendar

        cal = iCalendar.from_ical(retrieved_obj.data)
        event = None
        for component in cal.walk():
            if component.name == "VEVENT":
                event = component
                break

        if event:
            print("\n✓ Event parsed successfully")
            print(f"✓ Summary: {event.get('summary')}")
            print(f"✓ RRULE: {event.get('rrule')}")

            if event.get('rrule'):
                print("✅ RRULE is present in retrieved event")
            else:
                print("❌ RRULE is MISSING in retrieved event!")
                return False

        # Now test list_calendar_objects which uses occurrences API
        print("\n\n3. Listing calendar objects (uses occurrences API):")
        objects = await backend.list_calendar_objects(
            request=request,
            calendar_path=calendar_path,
        )

        # Find our event in the list
        our_event = None
        for obj in objects:
            if event_key in obj.path:
                our_event = obj
                break

        if our_event:
            print(f"\n✓ Found our event in list: {our_event.path}")
            print("\nRetrieved iCalendar data from list:")
            print(our_event.data)

            # Parse and verify
            cal = iCalendar.from_ical(our_event.data)
            event = None
            for component in cal.walk():
                if component.name == "VEVENT":
                    event = component
                    break

            if event:
                print("\n✓ Event parsed successfully")
                print(f"✓ Summary: {event.get('summary')}")
                print(f"✓ RRULE: {event.get('rrule')}")

                if event.get('rrule'):
                    print("✅ RRULE is present in listed event")
                else:
                    print("❌ RRULE is MISSING in listed event!")
                    print("\nThis means when fetching occurrences, the series schema is not being retrieved!")
                    return False
        else:
            print(f"❌ Could not find event {event_key} in list of {len(objects)} objects")
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
    """Run the test."""
    success = await test_caldav_series_workflow()

    print("\n" + "=" * 80)
    if success:
        print("✅ TEST PASSED")
    else:
        print("❌ TEST FAILED")
    print("=" * 80)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
