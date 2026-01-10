#!/usr/bin/env python3
"""Diagnostic script to trace series event fetching during CalDAV sync.

This simulates what happens when a CalDAV client syncs and examines
exactly what data we're getting from the INFORM API.
"""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, '/home/user/py-webdav')

from py_webdav.inform_api_client import InformAPIClient, InformConfig
from py_webdav.caldav import InformCalDAVBackend


async def diagnose():
    """Diagnose series event fetching."""
    print("=" * 80)
    print("DIAGNOSTIC: Series Event Fetching")
    print("=" * 80)

    config = InformConfig()
    client = InformAPIClient(config, debug=False)

    try:
        # Create a series event
        start_date = datetime.now(UTC).date()
        end_date = start_date + timedelta(days=7)

        event_data = {
            "eventMode": "serial",
            "subject": "Debug Series Event",
            "ownerKey": config.username,
            "seriesStartDate": start_date.strftime("%Y-%m-%d"),
            "seriesEndDate": end_date.strftime("%Y-%m-%d"),
            "occurrenceStartTime": 32400,  # 9:00 AM
            "occurrenceStartTimeEnabled": True,
            "occurrenceEndTime": 34200,  # 9:30 AM
            "occurrenceEndTimeEnabled": True,
            "wholeDayEvent": False,
            "seriesSchema": {
                "schemaType": "daily",
                "dailySchemaData": {
                    "regularity": "interval",
                    "daysInterval": 1,
                },
            },
        }

        print("\n1. Creating series event:")
        print(json.dumps(event_data, indent=2))

        created = await client.create_calendar_event(event_data)
        event_key = created["key"]
        print(f"\n✓ Created event with key: {event_key}")

        # Step 2: Fetch via direct GET with fields=["all"]
        print("\n" + "=" * 80)
        print("2. Direct GET /calendarEvents/{key} with fields=['all']")
        print("=" * 80)

        direct_get = await client.get_calendar_event(event_key, fields=["all"])
        print(json.dumps(direct_get, indent=2))

        print("\n✓ Has seriesSchema?", "seriesSchema" in direct_get)
        print("✓ Has seriesStartDate?", "seriesStartDate" in direct_get)
        print("✓ Has seriesEndDate?", "seriesEndDate" in direct_get)
        print("✓ eventMode:", direct_get.get("eventMode"))

        # Step 3: Fetch via occurrences API
        print("\n" + "=" * 80)
        print("3. GET /calendarEvents/occurrences (what CalDAV sync uses)")
        print("=" * 80)

        occurrences = await client.get_calendar_events_occurrences(
            owner_key=config.username,
            start_datetime=start_date.strftime("%Y-%m-%dT00:00:00Z"),
            end_datetime=end_date.strftime("%Y-%m-%dT23:59:59Z"),
            fields=["all"],  # Try requesting all fields
        )

        our_occurrences = [
            e for e in occurrences.get("calendarEvents", [])
            if e.get("key") == event_key
        ]

        print(f"\nFound {len(our_occurrences)} occurrences of our event")

        if our_occurrences:
            print("\nFirst occurrence data:")
            first = our_occurrences[0]
            print(json.dumps(first, indent=2))

            print("\n✓ Has occurrenceId?", "occurrenceId" in first)
            print("✓ Has seriesSchema?", "seriesSchema" in first)
            print("✓ Has seriesStartDate?", "seriesStartDate" in first)
            print("✓ Has seriesEndDate?", "seriesEndDate" in first)
            print("✓ Has eventMode?", "eventMode" in first)
            print("✓ key field:", first.get("key"))

            # Step 4: If occurrence has occurrenceId, fetch full event
            if "occurrenceId" in first:
                print("\n" + "=" * 80)
                print("4. Fetching full event for occurrence")
                print("=" * 80)
                print(f"Occurrence has occurrenceId: {first['occurrenceId']}")
                print(f"Fetching event by key: {first['key']}")

                full_event = await client.get_calendar_event(
                    first["key"], fields=["all"]
                )
                print("\nFull event data:")
                print(json.dumps(full_event, indent=2))

                print("\n✓ Has seriesSchema?", "seriesSchema" in full_event)
                print("✓ Has seriesStartDate?", "seriesStartDate" in full_event)
                print("✓ Has seriesEndDate?", "seriesEndDate" in full_event)
                print("✓ eventMode:", full_event.get("eventMode"))

        # Step 5: Test CalDAV backend conversion
        print("\n" + "=" * 80)
        print("5. CalDAV Backend Conversion")
        print("=" * 80)

        backend = InformCalDAVBackend(owner_key=config.username, debug=False)

        # Use the event data from direct GET
        ical = backend._inform_event_to_ical(direct_get)
        print("\nConverted to iCalendar:")
        print(ical)

        # Parse and check
        from icalendar import Calendar as iCalendar

        cal = iCalendar.from_ical(ical)
        for component in cal.walk():
            if component.name == "VEVENT":
                rrule = component.get("rrule")
                print(f"\n✓ RRULE in iCalendar: {rrule is not None}")
                if rrule:
                    print(f"  RRULE: {rrule}")
                else:
                    print("  ❌ NO RRULE!")

        await backend.api_client.close()

        # Cleanup
        await client.delete_calendar_event(event_key)
        print(f"\n✓ Deleted event {event_key}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(diagnose())
