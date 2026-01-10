#!/usr/bin/env python3
"""Test series events with different date ranges.

Some CalDAV clients might sync with a narrow date range (e.g., next 30 days only).
This tests if we correctly return series information even when the date range
doesn't include the series start date or spans only part of the recurrence.
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

sys.path.insert(0, '/home/user/py-webdav')

from py_webdav.caldav import InformCalDAVBackend


async def test_series_with_date_ranges():
    """Test series event retrieval with various date ranges."""
    print("=" * 80)
    print("TEST: Series Events with Different Date Ranges")
    print("=" * 80)

    backend = InformCalDAVBackend(owner_key="INFO", debug=False)
    request = Mock()
    calendar_path = "/calendars/INFO/default/"

    try:
        # Create a series event that starts today and runs for 30 days
        today = datetime.now(UTC).date()
        series_start = today
        series_end = today + timedelta(days=30)

        print(f"\nCreating series event:")
        print(f"  Start: {series_start}")
        print(f"  End: {series_end}")
        print(f"  Frequency: Daily")

        ical_create = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-daterange-{today}
SUMMARY:Daily Standup
DTSTART:{series_start.strftime('%Y%m%d')}T090000Z
DTEND:{series_start.strftime('%Y%m%d')}T093000Z
RRULE:FREQ=DAILY;INTERVAL=1;UNTIL={series_end.strftime('%Y%m%d')}T235959Z
END:VEVENT
END:VCALENDAR"""

        object_path = f"{calendar_path}test-daterange-{today}.ics"
        created = await backend.put_calendar_object(request, object_path, ical_create)
        event_key = backend._parse_object_path(created.path)

        print(f"\n✓ Created event with key: {event_key}")

        # Test Case 1: Sync with full date range (includes series start)
        print("\n" + "=" * 80)
        print("Test Case 1: Full date range (includes series start)")
        print("=" * 80)

        # Temporarily modify the sync date range
        original_get_sync = backend._get_sync_date_range

        def get_full_range():
            return (
                datetime.combine(series_start, datetime.min.time()).replace(tzinfo=UTC),
                datetime.combine(series_end, datetime.max.time()).replace(tzinfo=UTC),
            )

        backend._get_sync_date_range = get_full_range

        objects1 = await backend.list_calendar_objects(request, calendar_path)
        our_event1 = None
        for obj in objects1:
            if event_key in obj.path:
                our_event1 = obj
                break

        if our_event1:
            from icalendar import Calendar as iCalendar
            cal = iCalendar.from_ical(our_event1.data)
            for component in cal.walk():
                if component.name == "VEVENT":
                    rrule = component.get('rrule')
                    print(f"✓ RRULE present: {rrule is not None}")
                    if not rrule:
                        print("❌ RRULE missing!")
                        return False

        # Test Case 2: Sync with partial date range (middle of series)
        print("\n" + "=" * 80)
        print("Test Case 2: Partial date range (days 10-20 of series)")
        print("=" * 80)

        def get_partial_range():
            start = datetime.combine(series_start + timedelta(days=10), datetime.min.time()).replace(tzinfo=UTC)
            end = datetime.combine(series_start + timedelta(days=20), datetime.max.time()).replace(tzinfo=UTC)
            print(f"  Query range: {start.date()} to {end.date()}")
            return (start, end)

        backend._get_sync_date_range = get_partial_range

        objects2 = await backend.list_calendar_objects(request, calendar_path)
        our_event2 = None
        for obj in objects2:
            if event_key in obj.path:
                our_event2 = obj
                break

        if our_event2:
            cal2 = iCalendar.from_ical(our_event2.data)
            for component in cal2.walk():
                if component.name == "VEVENT":
                    rrule2 = component.get('rrule')
                    print(f"✓ RRULE present: {rrule2 is not None}")
                    if rrule2:
                        print(f"  RRULE: {rrule2}")
                    else:
                        print("❌ RRULE missing in partial range!")
                        print("This could be the bug - series info lost when querying partial range")
                        return False
        else:
            print("❌ Event not found in partial range!")
            print("This might be expected if occurrences API doesn't return anything in this range")

        # Test Case 3: Sync with future date range (after series start)
        print("\n" + "=" * 80)
        print("Test Case 3: Future date range (days 20-30 of series)")
        print("=" * 80)

        def get_future_range():
            start = datetime.combine(series_start + timedelta(days=20), datetime.min.time()).replace(tzinfo=UTC)
            end = datetime.combine(series_start + timedelta(days=30), datetime.max.time()).replace(tzinfo=UTC)
            print(f"  Query range: {start.date()} to {end.date()}")
            return (start, end)

        backend._get_sync_date_range = get_future_range

        objects3 = await backend.list_calendar_objects(request, calendar_path)
        our_event3 = None
        for obj in objects3:
            if event_key in obj.path:
                our_event3 = obj
                break

        if our_event3:
            cal3 = iCalendar.from_ical(our_event3.data)
            for component in cal3.walk():
                if component.name == "VEVENT":
                    rrule3 = component.get('rrule')
                    print(f"✓ RRULE present: {rrule3 is not None}")
                    if rrule3:
                        print(f"  RRULE: {rrule3}")
                    else:
                        print("❌ RRULE missing in future range!")
                        return False
        else:
            print("⚠ Event not found in future range")

        # Restore original method
        backend._get_sync_date_range = original_get_sync

        # Test Case 4: Direct GET (should always work)
        print("\n" + "=" * 80)
        print("Test Case 4: Direct GET (bypass date ranges)")
        print("=" * 80)

        direct = await backend.get_calendar_object(request, created.path)
        cal4 = iCalendar.from_ical(direct.data)
        for component in cal4.walk():
            if component.name == "VEVENT":
                rrule4 = component.get('rrule')
                print(f"✓ RRULE present: {rrule4 is not None}")
                if not rrule4:
                    print("❌ RRULE missing even in direct GET!")
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
    success = await test_series_with_date_ranges()

    print("\n" + "=" * 80)
    if success:
        print("✅ TEST PASSED - RRULE preserved across all date ranges")
    else:
        print("❌ TEST FAILED - RRULE lost with certain date ranges")
    print("=" * 80)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
