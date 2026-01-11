#!/usr/bin/env python3
"""Test that the RRULE can be parsed correctly by standard libraries."""

import asyncio
import os
from datetime import datetime, timedelta, UTC
from dateutil.rrule import rrulestr

from py_webdav.inform_api_client import InformAPIClient, InformConfig
from py_webdav.caldav.inform_backend import InformCalDAVBackend
from icalendar import Calendar


async def main():
    """Test RRULE parsing."""
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
            series_event = await client.get_calendar_event(event_key, fields=["all"])
            break

    if not series_event:
        print("No series event found!")
        return

    print(f"\n{'='*80}")
    print(f"Testing RRULE Parsing")
    print(f"{'='*80}\n")

    # Convert to iCalendar
    ical_data = backend._inform_event_to_ical(series_event)

    # Parse the calendar
    cal = Calendar.from_ical(ical_data)

    for component in cal.walk():
        if component.name == "VEVENT":
            print(f"Event: {component.get('SUMMARY')}")
            print(f"UID: {component.get('UID')}")

            dtstart = component.get('DTSTART')
            print(f"DTSTART: {dtstart.dt}")

            if 'RRULE' in component:
                rrule = component.get('RRULE')
                print(f"\nRRULE object: {rrule}")
                print(f"RRULE type: {type(rrule)}")

                # Convert to ical format
                rrule_ical = rrule.to_ical().decode('utf-8')
                print(f"\nRRULE (iCalendar format): {rrule_ical}")

                # Parse with dateutil to generate occurrences
                print(f"\n{'='*80}")
                print(f"Testing with dateutil.rrule (what CalDAV clients use)")
                print(f"{'='*80}\n")

                try:
                    # Build RRULE string for dateutil
                    rrule_string = f"DTSTART:{dtstart.dt.strftime('%Y%m%dT%H%M%SZ')}\nRRULE:{rrule_ical}"
                    print(f"Parsing: {rrule_string}")
                    print()

                    # Parse and generate first 10 occurrences
                    rule = rrulestr(rrule_string)
                    occurrences = list(rule[:10])

                    print(f"✓ Successfully parsed RRULE!")
                    print(f"  First 10 occurrences:")
                    for i, occ in enumerate(occurrences, 1):
                        print(f"    {i}. {occ.strftime('%Y-%m-%d %H:%M:%S %Z')}")

                    # Verify it matches expected pattern
                    print(f"\n{'='*80}")
                    print(f"Verification:")
                    print(f"{'='*80}\n")

                    if 'BYDAY=MO,TU,WE,TH,FR' in rrule_ical:
                        # Should be weekdays only
                        weekdays = [occ.weekday() for occ in occurrences]
                        if all(wd < 5 for wd in weekdays):
                            print("✓ All occurrences are weekdays (Mon-Fri)")
                        else:
                            print("✗ Some occurrences are weekends!")

                    if 'FREQ=WEEKLY' in rrule_ical:
                        # Check spacing
                        if len(occurrences) >= 2:
                            gaps = [(occurrences[i] - occurrences[i-1]).days
                                    for i in range(1, min(6, len(occurrences)))]
                            print(f"  Day gaps between occurrences: {gaps}")
                            if all(g == 1 for g in gaps[:4]):
                                print("  ✓ Consecutive weekdays as expected")

                    print("\n✓ RRULE is correctly formatted and parseable!")
                    print("  CalDAV clients should interpret this correctly.")

                except Exception as e:
                    print(f"✗ Failed to parse RRULE: {e}")
                    print(f"  This could cause issues with CalDAV clients")

            else:
                print("No RRULE found (not a recurring event)")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
