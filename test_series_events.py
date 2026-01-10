#!/usr/bin/env python3
"""Test series (recurring) events behavior.

This script verifies:
1. CalDAV to INFORM series event conversion
2. Series schema and date handling
3. Occurrence retrieval
4. Round-trip conversion (CalDAV -> INFORM -> CalDAV)
"""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, '/home/user/py-webdav')

from py_webdav.inform_api_client import InformAPIClient, InformConfig
from py_webdav.caldav import InformCalDAVBackend


async def test_series_event_conversion():
    """Test CalDAV to INFORM series event conversion."""
    print("=" * 80)
    print("TEST 1: CalDAV to INFORM Series Event Conversion")
    print("=" * 80)

    backend = InformCalDAVBackend(owner_key="INFO", debug=False)

    # Create a daily recurring event in iCalendar format
    start_date = datetime.now(UTC).date()
    end_date = start_date + timedelta(days=7)

    ical_data = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-series-{start_date}
SUMMARY:Daily Team Standup
DESCRIPTION:Daily team meeting
LOCATION:Conference Room
DTSTART:{start_date.strftime('%Y%m%d')}T090000Z
DTEND:{start_date.strftime('%Y%m%d')}T093000Z
RRULE:FREQ=DAILY;INTERVAL=1;UNTIL={end_date.strftime('%Y%m%d')}T235959Z
CLASS:PUBLIC
END:VEVENT
END:VCALENDAR"""

    print("\nOriginal iCalendar data:")
    print(ical_data)

    # Convert to INFORM format
    inform_event = backend._ical_to_inform_event(ical_data)

    print("\n\nConverted INFORM event data:")
    print(json.dumps(inform_event, indent=2))

    # Verify critical fields
    print("\n\nVerifying series event fields:")
    print(f"✓ Event Mode: {inform_event.get('eventMode')}")
    assert inform_event.get('eventMode') == 'serial', "Event mode should be 'serial'"

    print(f"✓ Series Start Date: {inform_event.get('seriesStartDate')}")
    assert inform_event.get('seriesStartDate') is not None, "Series start date is missing"

    print(f"✓ Series End Date: {inform_event.get('seriesEndDate')}")
    assert inform_event.get('seriesEndDate') is not None, "Series end date is missing"

    print(f"✓ Occurrence Start Time: {inform_event.get('occurrenceStartTime')}")
    assert inform_event.get('occurrenceStartTime') == 32400, "Occurrence start time should be 32400 (09:00)"

    print(f"✓ Occurrence End Time: {inform_event.get('occurrenceEndTime')}")
    assert inform_event.get('occurrenceEndTime') == 34200, "Occurrence end time should be 34200 (09:30)"

    print(f"✓ Series Schema: {json.dumps(inform_event.get('seriesSchema'), indent=2)}")
    assert inform_event.get('seriesSchema') is not None, "Series schema is missing"
    assert inform_event['seriesSchema']['schemaType'] == 'daily', "Schema type should be 'daily'"

    print("\n✅ All series event fields are correctly converted")

    await backend.api_client.close()


async def test_series_event_creation_and_retrieval():
    """Test creating a series event and retrieving it with full details."""
    print("\n\n" + "=" * 80)
    print("TEST 2: Series Event Creation and Retrieval")
    print("=" * 80)

    config = InformConfig()
    client = InformAPIClient(config)

    try:
        start_date = datetime.now(UTC).date()
        end_date = start_date + timedelta(days=14)

        # Create weekly recurring event
        event_data = {
            "eventMode": "serial",
            "subject": "Weekly Team Meeting",
            "content": "Weekly sync with the team",
            "location": "Meeting Room A",
            "ownerKey": config.username,
            "seriesStartDate": start_date.strftime("%Y-%m-%d"),
            "seriesEndDate": end_date.strftime("%Y-%m-%d"),
            "occurrenceStartTime": 50400,  # 14:00
            "occurrenceStartTimeEnabled": True,
            "occurrenceEndTime": 54000,  # 15:00
            "occurrenceEndTimeEnabled": True,
            "wholeDayEvent": False,
            "seriesSchema": {
                "schemaType": "weekly",
                "weeklySchemaData": {
                    "weekdays": ["monday", "wednesday", "friday"],
                    "weeksInterval": 1,
                },
            },
        }

        print("\nCreating series event:")
        print(json.dumps(event_data, indent=2))

        created = await client.create_calendar_event(event_data)
        event_key = created["key"]
        print(f"\n✓ Created event with key: {event_key}")

        # Retrieve the event with all fields
        print("\n\nRetrieving event with all fields...")
        retrieved = await client.get_calendar_event(event_key, fields=["all"])

        print("\nRetrieved event data:")
        print(json.dumps(retrieved, indent=2))

        # Verify all critical fields are present
        print("\n\nVerifying retrieved series event:")
        print(f"✓ Event Mode: {retrieved.get('eventMode')}")
        assert retrieved.get('eventMode') == 'serial', "Event mode should be 'serial'"

        print(f"✓ Series Start Date: {retrieved.get('seriesStartDate')}")
        assert retrieved.get('seriesStartDate') == start_date.strftime('%Y-%m-%d'), "Series start date mismatch"

        print(f"✓ Series End Date: {retrieved.get('seriesEndDate')}")
        assert retrieved.get('seriesEndDate') == end_date.strftime('%Y-%m-%d'), "Series end date mismatch"

        print(f"✓ Occurrence Start Time: {retrieved.get('occurrenceStartTime')}")
        assert retrieved.get('occurrenceStartTime') == 50400, "Occurrence start time mismatch"

        print(f"✓ Occurrence End Time: {retrieved.get('occurrenceEndTime')}")
        assert retrieved.get('occurrenceEndTime') == 54000, "Occurrence end time mismatch"

        print(f"✓ Series Schema: {json.dumps(retrieved.get('seriesSchema'), indent=2)}")
        schema = retrieved.get('seriesSchema')
        assert schema is not None, "Series schema is missing"
        assert schema['schemaType'] == 'weekly', "Schema type should be 'weekly'"
        assert 'monday' in schema['weeklySchemaData']['weekdays'], "Monday should be in weekdays"

        print("\n✅ All series event fields are preserved on retrieval")

        # Now test occurrences API
        print("\n\n" + "-" * 80)
        print("Testing Occurrences API")
        print("-" * 80)

        # Fetch occurrences
        occurrences_response = await client.get_calendar_events_occurrences(
            owner_key=config.username,
            start_datetime=start_date.strftime("%Y-%m-%dT00:00:00Z"),
            end_datetime=end_date.strftime("%Y-%m-%dT23:59:59Z"),
            fields=["all"],
        )

        print(f"\nFound {occurrences_response.get('count')} occurrences")

        # Find our event in the occurrences
        our_occurrences = [
            e for e in occurrences_response.get('calendarEvents', [])
            if e.get('key') == event_key
        ]

        print(f"Our event has {len(our_occurrences)} occurrences in the date range")

        if our_occurrences:
            print("\nFirst occurrence:")
            first_occ = our_occurrences[0]
            print(json.dumps(first_occ, indent=2))

            # Check if occurrence has occurrenceId
            if 'occurrenceId' in first_occ:
                print(f"\n✓ Occurrence ID: {first_occ['occurrenceId']}")
                print("✓ This is an occurrence of a series event")
            else:
                print("\n✓ This is the series event definition itself")

        # Cleanup
        await client.delete_calendar_event(event_key)
        print(f"\n✓ Deleted event {event_key}")
        print("\n✅ Occurrences API test completed successfully")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()


async def test_round_trip_conversion():
    """Test round-trip conversion: CalDAV -> INFORM -> CalDAV."""
    print("\n\n" + "=" * 80)
    print("TEST 3: Round-Trip Conversion (CalDAV -> INFORM -> CalDAV)")
    print("=" * 80)

    backend = InformCalDAVBackend(owner_key="INFO", debug=False)

    # Create a monthly recurring event
    start_date = datetime.now(UTC).date()

    original_ical = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-monthly-{start_date}
SUMMARY:Monthly Review
DESCRIPTION:Monthly team review meeting
DTSTART:{start_date.strftime('%Y%m%d')}T100000Z
DTEND:{start_date.strftime('%Y%m%d')}T110000Z
RRULE:FREQ=MONTHLY;BYMONTHDAY=15;INTERVAL=1
CLASS:PUBLIC
END:VEVENT
END:VCALENDAR"""

    print("\nOriginal iCalendar:")
    print(original_ical)

    # Convert to INFORM
    inform_event = backend._ical_to_inform_event(original_ical)
    print("\n\nINFORM format:")
    print(json.dumps(inform_event, indent=2))

    # Add required fields for API
    inform_event['ownerKey'] = 'INFO'
    inform_event['key'] = f'test-monthly-{start_date}'

    # Convert back to iCalendar
    converted_ical = backend._inform_event_to_ical(inform_event)
    print("\n\nConverted back to iCalendar:")
    print(converted_ical)

    # Parse and compare
    from icalendar import Calendar as iCalendar

    original_cal = iCalendar.from_ical(original_ical)
    converted_cal = iCalendar.from_ical(converted_ical)

    original_event = None
    for component in original_cal.walk():
        if component.name == "VEVENT":
            original_event = component
            break

    converted_event = None
    for component in converted_cal.walk():
        if component.name == "VEVENT":
            converted_event = component
            break

    print("\n\nComparing original vs converted:")
    print(f"✓ Summary: '{original_event.get('summary')}' vs '{converted_event.get('summary')}'")
    assert str(original_event.get('summary')) == str(converted_event.get('summary')), "Summary mismatch"

    print(f"✓ RRULE present in both: {bool(original_event.get('rrule'))} vs {bool(converted_event.get('rrule'))}")
    assert original_event.get('rrule') is not None, "Original should have RRULE"
    assert converted_event.get('rrule') is not None, "Converted should have RRULE"

    print("\n✅ Round-trip conversion successful")

    await backend.api_client.close()


async def main():
    """Run all tests."""
    print("Testing Series Events Behavior\n")

    try:
        await test_series_event_conversion()
        await test_series_event_creation_and_retrieval()
        await test_round_trip_conversion()

        print("\n\n" + "=" * 80)
        print("✅ ALL TESTS PASSED")
        print("=" * 80)

    except AssertionError as e:
        print(f"\n\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
