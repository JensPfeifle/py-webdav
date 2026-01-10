#!/usr/bin/env python3
"""Test series event update cycle.

This simulates:
1. Create recurring event via CalDAV
2. Get it back (sync)
3. Update it (e.g., change title)
4. Get it again (resync)
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

sys.path.insert(0, '/home/user/py-webdav')

from py_webdav.caldav import InformCalDAVBackend


async def test_update_cycle():
    """Test series event through update cycle."""
    print("=" * 80)
    print("TEST: Series Event Update Cycle")
    print("=" * 80)

    backend = InformCalDAVBackend(owner_key="INFO", debug=False)
    request = Mock()
    calendar_path = "/calendars/INFO/default/"

    try:
        start_date = datetime.now(UTC).date()
        end_date = start_date + timedelta(days=7)

        # Step 1: Create recurring event
        print("\n1. CREATE: Creating recurring event via CalDAV")
        print("-" * 60)

        ical_create = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-update-{start_date}
SUMMARY:Original Title
DTSTART:{start_date.strftime('%Y%m%d')}T140000Z
DTEND:{start_date.strftime('%Y%m%d')}T150000Z
RRULE:FREQ=DAILY;INTERVAL=1;UNTIL={end_date.strftime('%Y%m%d')}T235959Z
END:VEVENT
END:VCALENDAR"""

        print(ical_create)

        object_path = f"{calendar_path}test-update-{start_date}.ics"
        created = await backend.put_calendar_object(request, object_path, ical_create)
        event_key = backend._parse_object_path(created.path)

        print(f"\n✓ Created event with key: {event_key}")
        print(f"✓ Path: {created.path}")

        # Step 2: Retrieve (first sync)
        print("\n\n2. SYNC 1: Retrieving event (first sync)")
        print("-" * 60)

        retrieved1 = await backend.get_calendar_object(request, created.path)
        print(retrieved1.data)

        from icalendar import Calendar as iCalendar
        cal1 = iCalendar.from_ical(retrieved1.data)
        event1 = None
        for component in cal1.walk():
            if component.name == "VEVENT":
                event1 = component
                break

        if event1:
            rrule1 = event1.get('rrule')
            summary1 = event1.get('summary')
            print(f"\n✓ Summary: {summary1}")
            print(f"✓ RRULE: {rrule1 is not None}")
            if rrule1:
                print(f"  {rrule1}")
            else:
                print("  ❌ MISSING RRULE after first sync!")
                return False

        # Step 3: Update the event (change title)
        print("\n\n3. UPDATE: Changing event title")
        print("-" * 60)

        ical_update = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:{event_key}
SUMMARY:Updated Title
DTSTART:{start_date.strftime('%Y%m%d')}T140000Z
DTEND:{start_date.strftime('%Y%m%d')}T150000Z
RRULE:FREQ=DAILY;INTERVAL=1;UNTIL={end_date.strftime('%Y%m%d')}T235959Z
END:VEVENT
END:VCALENDAR"""

        print(ical_update)

        updated = await backend.put_calendar_object(request, created.path, ical_update)

        print(f"\n✓ Updated event")

        # Step 4: Retrieve again (resync)
        print("\n\n4. SYNC 2: Retrieving event after update (resync)")
        print("-" * 60)

        retrieved2 = await backend.get_calendar_object(request, created.path)
        print(retrieved2.data)

        cal2 = iCalendar.from_ical(retrieved2.data)
        event2 = None
        for component in cal2.walk():
            if component.name == "VEVENT":
                event2 = component
                break

        if event2:
            rrule2 = event2.get('rrule')
            summary2 = event2.get('summary')
            print(f"\n✓ Summary: {summary2}")
            print(f"✓ RRULE: {rrule2 is not None}")
            if rrule2:
                print(f"  {rrule2}")
                print("\n✅ RRULE PRESERVED after update!")
            else:
                print("  ❌ RRULE LOST after update!")
                print("\n🔍 This is the problem! Recurrence information lost on update/resync")
                return False

        # Step 5: List calendar objects (another type of sync)
        print("\n\n5. SYNC 3: List calendar objects")
        print("-" * 60)

        objects = await backend.list_calendar_objects(request, calendar_path)
        our_event = None
        for obj in objects:
            if event_key in obj.path:
                our_event = obj
                break

        if our_event:
            print(our_event.data)

            cal3 = iCalendar.from_ical(our_event.data)
            for component in cal3.walk():
                if component.name == "VEVENT":
                    rrule3 = component.get('rrule')
                    summary3 = component.get('summary')
                    print(f"\n✓ Summary: {summary3}")
                    print(f"✓ RRULE: {rrule3 is not None}")
                    if rrule3:
                        print(f"  {rrule3}")
                        print("\n✅ RRULE PRESERVED in list!")
                    else:
                        print("  ❌ RRULE LOST in list!")
                        return False

        # Cleanup
        await backend.delete_calendar_object(request, created.path)
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
    success = await test_update_cycle()

    print("\n" + "=" * 80)
    if success:
        print("✅ TEST PASSED - Series info preserved through update cycle")
    else:
        print("❌ TEST FAILED - Series info lost during update cycle")
    print("=" * 80)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
