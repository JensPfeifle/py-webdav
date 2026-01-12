#!/usr/bin/env python3
"""Check if DTSTART matches the first actual occurrence from INFORM."""

import asyncio
import os
from datetime import datetime, timedelta, UTC

from py_webdav.inform_api_client import InformAPIClient, InformConfig
from py_webdav.caldav.inform_backend import InformCalDAVBackend
from icalendar import Calendar


async def main():
    """Check DTSTART vs first occurrence."""
    config = InformConfig()
    owner_key = os.getenv("INFORM_OWNER_KEY", config.username).strip('"')

    backend = InformCalDAVBackend(config=config, owner_key=owner_key)
    client = InformAPIClient(config)

    # Get occurrences
    start_date = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    end_date = datetime(2026, 2, 28, 23, 59, 59, tzinfo=UTC)

    response = await client.get_calendar_events_occurrences(
        owner_key=owner_key,
        start_datetime=start_date.isoformat(),
        end_datetime=end_date.isoformat(),
        limit=1000,
    )

    events = response.get("calendarEvents", [])

    # Find a series event and its occurrences
    series_key = None
    occurrences = []

    for event in events:
        if event.get("occurrenceId"):
            key = event.get("key")
            if not series_key:
                series_key = key
            if key == series_key:
                occurrences.append(event)

    if not occurrences:
        print("No series events found!")
        return

    # Sort by start time
    occurrences.sort(key=lambda e: e.get("startDateTime", ""))

    print(f"\n{'='*80}")
    print(f"INFORM API Occurrences for Event: {occurrences[0].get('subject')}")
    print(f"Event Key: {series_key}")
    print(f"{'='*80}\n")

    print(f"Total occurrences: {len(occurrences)}\n")
    print("First 5 occurrences from INFORM:")
    for i, occ in enumerate(occurrences[:5], 1):
        start_dt = occ.get("startDateTime", "")
        occ_id = occ.get("occurrenceId", "")
        if start_dt:
            dt = datetime.fromisoformat(start_dt.replace("Z", "+00:00"))
            weekday = dt.strftime("%A")
            print(f"  {i}. {dt.strftime('%Y-%m-%d %H:%M %Z')} ({weekday}) - Occ ID: {occ_id}")

    # Get full event
    full_event = await client.get_calendar_event(series_key, fields=["all"])

    print(f"\n{'='*80}")
    print(f"Full Event Details from INFORM")
    print(f"{'='*80}\n")
    print(f"Series Start Date: {full_event.get('seriesStartDate')}")
    print(f"Series End Date: {full_event.get('seriesEndDate')}")
    print(f"Occurrence Start Time: {full_event.get('occurrenceStartTime')} seconds")
    print(f"Event Mode: {full_event.get('eventMode')}")

    # Convert to iCalendar
    ical_data = backend._inform_event_to_ical(full_event)
    cal = Calendar.from_ical(ical_data)

    for component in cal.walk():
        if component.name == "VEVENT":
            dtstart = component.get('DTSTART').dt
            rrule = component.get('RRULE')

            print(f"\n{'='*80}")
            print(f"Generated iCalendar")
            print(f"{'='*80}\n")
            print(f"DTSTART: {dtstart.strftime('%Y-%m-%d %H:%M %Z')} ({dtstart.strftime('%A')})")
            if rrule:
                print(f"RRULE: {rrule.to_ical().decode('utf-8')}")

    # Compare
    first_inform_occ = datetime.fromisoformat(occurrences[0].get("startDateTime", "").replace("Z", "+00:00"))

    print(f"\n{'='*80}")
    print(f"Comparison")
    print(f"{'='*80}\n")
    print(f"DTSTART from series:      {dtstart.strftime('%Y-%m-%d %H:%M')} ({dtstart.strftime('%A')})")
    print(f"First INFORM occurrence:  {first_inform_occ.strftime('%Y-%m-%d %H:%M')} ({first_inform_occ.strftime('%A')})")

    if dtstart.date() == first_inform_occ.date():
        print("\n✓ DTSTART matches first occurrence date")
    else:
        print(f"\n✗ MISMATCH!")
        print(f"  DTSTART is {(first_inform_occ.date() - dtstart.date()).days} days before first occurrence")
        print(f"  This might cause CalDAV clients to show incorrect occurrences")
        print(f"\n  RECOMMENDED FIX:")
        print(f"    Use first actual occurrence date as DTSTART instead of seriesStartDate")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
