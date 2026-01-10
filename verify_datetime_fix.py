#!/usr/bin/env python3
"""Verify that the datetime fix preserves event times correctly."""

import asyncio
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, '/home/user/py-webdav')

from py_webdav.caldav.inform_backend import InformCalDAVBackend
from py_webdav.inform_api_client import InformConfig
from unittest.mock import MagicMock


async def test_datetime_preservation():
    """Test that event times are preserved correctly."""
    print("=" * 80)
    print("DateTime Fix Verification")
    print("=" * 80)

    config = InformConfig()
    backend = InformCalDAVBackend(config=config, owner_key=config.username)
    request = MagicMock()
    calendar_path = backend._get_calendar_path()

    # Create event with specific time (2:30 PM)
    now = datetime.now(UTC)
    start_time = now.replace(hour=14, minute=30, second=0, microsecond=0)
    end_time = start_time + timedelta(hours=1, minutes=30)  # 4:00 PM

    print(f"\nTest: Creating event with specific times")
    print(f"  Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')} (14:30:00)")
    print(f"  End:   {end_time.strftime('%Y-%m-%d %H:%M:%S')} (16:00:00)")

    ical_data = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:verify-datetime-fix-{now.timestamp()}
DTSTART:{start_time.strftime('%Y%m%dT%H%M%SZ')}
DTEND:{end_time.strftime('%Y%m%dT%H%M%SZ')}
SUMMARY:DateTime Fix Verification
DESCRIPTION:Testing that times are preserved
LOCATION:Test Location
CLASS:PUBLIC
END:VEVENT
END:VCALENDAR"""

    try:
        # Create the event
        object_path = f"{calendar_path}verify-datetime-{now.timestamp()}.ics"
        calendar_object = await backend.put_calendar_object(
            request, object_path, ical_data, if_none_match=True
        )

        print(f"\n✓ Event created successfully")
        print(f"  Path: {calendar_object.path}")

        # Parse the returned iCal to check times
        print(f"\nReturned iCalendar data:")
        print("-" * 80)
        print(calendar_object.data)
        print("-" * 80)

        # Check if times are preserved
        if "14:30" in calendar_object.data or "T143000Z" in calendar_object.data:
            print("\n✅ SUCCESS: Start time (14:30) preserved!")
        else:
            print("\n❌ FAIL: Start time was modified!")
            print(f"Expected to find 14:30 or T143000Z in the data")

        if "16:00" in calendar_object.data or "T160000Z" in calendar_object.data:
            print("✅ SUCCESS: End time (16:00) preserved!")
        else:
            print("❌ FAIL: End time was modified!")
            print(f"Expected to find 16:00 or T160000Z in the data")

        # Cleanup
        await backend.delete_calendar_object(request, calendar_object.path)
        print(f"\n✓ Test event cleaned up")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await backend.api_client.close()

    print("\n" + "=" * 80)
    print("Verification Complete")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_datetime_preservation())
