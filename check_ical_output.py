#!/usr/bin/env python3
"""Check the raw iCalendar output for encoding issues."""

import asyncio
import os
from datetime import datetime, timedelta, UTC

from py_webdav.inform_api_client import InformAPIClient, InformConfig
from py_webdav.caldav.inform_backend import InformCalDAVBackend


async def main():
    """Check iCalendar output."""
    config = InformConfig()
    owner_key = os.getenv("INFORM_OWNER_KEY", config.username).strip('"')

    backend = InformCalDAVBackend(config=config, owner_key=owner_key)
    client = InformAPIClient(config)

    # Get a series event
    start_date = datetime.now(UTC)
    end_date = start_date + timedelta(days=30)

    response = await client.get_calendar_events_occurrences(
        owner_key=owner_key,
        start_datetime=start_date.isoformat(),
        end_datetime=end_date.isoformat(),
        limit=1000,
    )

    events = response.get("calendarEvents", [])

    # Find first series event
    series_event = None
    for event in events:
        if event.get("occurrenceId"):
            event_key = event.get("key")
            # Fetch full event
            series_event = await client.get_calendar_event(event_key, fields=["all"])
            break

    if not series_event:
        print("No series event found!")
        return

    print(f"\n{'='*80}")
    print(f"Event: {series_event.get('subject')}")
    print(f"Key: {series_event.get('key')}")
    print(f"{'='*80}\n")

    # Convert to iCalendar
    ical_data = backend._inform_event_to_ical(series_event)

    print("Raw iCalendar output:")
    print("-" * 80)
    print(ical_data)
    print("-" * 80)

    print("\n\nChecking for issues:")
    print("-" * 80)

    # Check for various encoding issues
    if '\r\n' in ical_data:
        print("✓ Uses CRLF line endings (correct for iCalendar)")
    elif '\n' in ical_data:
        print("⚠ Uses LF line endings (should be CRLF)")

    if '&#13' in ical_data:
        print("✗ Contains HTML entity &#13 (should be literal \\r)")

    if '&#10' in ical_data:
        print("✗ Contains HTML entity &#10 (should be literal \\n)")

    # Check RRULE specifically
    rrule_lines = [line for line in ical_data.split('\n') if 'RRULE' in line]
    if rrule_lines:
        print(f"\nRRULE line(s):")
        for line in rrule_lines:
            print(f"  {repr(line)}")

            if '\\' in line and 'UNTIL' not in line:
                print("  ⚠ Contains backslash (check if correct)")

            # Check for proper format
            if line.startswith('RRULE:'):
                print("  ✓ Starts with RRULE:")
            elif 'RRULE:' in line:
                print("  ✓ Contains RRULE:")

    # Check raw bytes
    print(f"\n\nRaw bytes (first 500):")
    print("-" * 80)
    print(repr(ical_data[:500].encode()))
    print("-" * 80)

    # Parse it back to verify
    print("\n\nParsing back to verify:")
    print("-" * 80)
    try:
        from icalendar import Calendar
        cal = Calendar.from_ical(ical_data)
        print("✓ Successfully parsed back")

        for component in cal.walk():
            if component.name == "VEVENT":
                if 'RRULE' in component:
                    rrule = component['RRULE']
                    print(f"  Parsed RRULE: {rrule}")
                    print(f"  RRULE type: {type(rrule)}")
                    print(f"  RRULE repr: {repr(rrule)}")
    except Exception as e:
        print(f"✗ Failed to parse: {e}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
