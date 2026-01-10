#!/usr/bin/env python3
"""Test immediate resync after creating a recurring event.

This reproduces the issue where:
1. Client creates event with RRULE
2. Client immediately requests the event back (resync)
3. RRULE should be present in the returned data
"""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

sys.path.insert(0, '/home/user/py-webdav')

from py_webdav.caldav import InformCalDAVBackend
from py_webdav.inform_api_client import InformAPIClient, InformConfig


async def test_immediate_resync():
    """Test creating and immediately retrieving a series event."""
    print("=" * 80)
    print("TEST: Immediate Resync After Creating Recurring Event")
    print("=" * 80)

    backend = InformCalDAVBackend(owner_key="INFO", debug=False)
    request = Mock()
    calendar_path = "/calendars/INFO/default/"

    try:
        start_date = datetime.now(UTC).date()
        end_date = start_date + timedelta(days=7)

        # Step 1: Client creates recurring event
        print("\n1. CLIENT: Creating recurring event")
        print("-" * 60)

        ical_create = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Client//Client//EN
BEGIN:VEVENT
UID:test-resync-{start_date}
SUMMARY:Daily Meeting
DTSTART:{start_date.strftime('%Y%m%d')}T100000Z
DTEND:{start_date.strftime('%Y%m%d')}T110000Z
RRULE:FREQ=DAILY;INTERVAL=1;UNTIL={end_date.strftime('%Y%m%d')}T235959Z
END:VEVENT
END:VCALENDAR"""

        print(ical_create)

        object_path = f"{calendar_path}test-resync-{start_date}.ics"

        # Create the event
        created = await backend.put_calendar_object(request, object_path, ical_create)
        event_key = backend._parse_object_path(created.path)

        print(f"\n✓ Event created with key: {event_key}")
        print(f"✓ Server returned path: {created.path}")

        # What does the server return immediately after creation?
        print("\nServer's immediate response:")
        print(created.data)

        from icalendar import Calendar as iCalendar
        cal = iCalendar.from_ical(created.data)
        for component in cal.walk():
            if component.name == "VEVENT":
                rrule = component.get('rrule')
                print(f"\n✓ RRULE in creation response: {rrule is not None}")
                if not rrule:
                    print("❌ RRULE MISSING in creation response!")

        # Step 2: Check what was actually saved to INFORM
        print("\n" + "=" * 80)
        print("2. Checking INFORM API directly")
        print("=" * 80)

        direct_get = await backend.api_client.get_calendar_event(event_key, fields=["all"])
        print("\nDirect API response (with fields=['all']):")
        print(json.dumps(direct_get, indent=2))

        print(f"\n✓ Has seriesSchema: {bool(direct_get.get('seriesSchema'))}")
        print(f"✓ Has seriesStartDate: {bool(direct_get.get('seriesStartDate'))}")
        print(f"✓ Has seriesEndDate: {bool(direct_get.get('seriesEndDate'))}")
        print(f"✓ eventMode: {direct_get.get('eventMode')}")

        # Step 3: Client requests the event (resync)
        print("\n" + "=" * 80)
        print("3. CLIENT: Requesting event (resync)")
        print("=" * 80)

        resynced = await backend.get_calendar_object(request, created.path)
        print("\nResynced data:")
        print(resynced.data)

        cal2 = iCalendar.from_ical(resynced.data)
        for component in cal2.walk():
            if component.name == "VEVENT":
                rrule2 = component.get('rrule')
                summary2 = component.get('summary')
                print(f"\n✓ Summary: {summary2}")
                print(f"✓ RRULE present: {rrule2 is not None}")
                if rrule2:
                    print(f"  {rrule2}")
                    print("\n✅ SUCCESS: RRULE preserved on resync")
                    success = True
                else:
                    print("❌ FAILURE: RRULE missing on resync!")
                    print("\nThis is the reported bug!")
                    success = False

        # Step 4: Test via list (another common sync method)
        print("\n" + "=" * 80)
        print("4. CLIENT: List sync")
        print("=" * 80)

        objects = await backend.list_calendar_objects(request, calendar_path)
        for obj in objects:
            if event_key in obj.path:
                print("\nEvent from list:")
                print(obj.data)

                cal3 = iCalendar.from_ical(obj.data)
                for component in cal3.walk():
                    if component.name == "VEVENT":
                        rrule3 = component.get('rrule')
                        print(f"\n✓ RRULE in list: {rrule3 is not None}")
                        if not rrule3:
                            print("❌ RRULE missing in list!")
                            success = False

        # Cleanup
        await backend.delete_calendar_object(request, created.path)
        print(f"\n✓ Deleted event {event_key}")

        return success

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await backend.api_client.close()


async def main():
    success = await test_immediate_resync()

    print("\n" + "=" * 80)
    if success:
        print("✅ TEST PASSED - RRULE preserved on immediate resync")
    else:
        print("❌ TEST FAILED - RRULE lost on resync (BUG REPRODUCED)")
    print("=" * 80)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
