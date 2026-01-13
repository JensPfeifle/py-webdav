#!/usr/bin/env python3
"""Test occurrence-per-event approach."""

import asyncio
import os
from datetime import datetime, timedelta, UTC

from py_webdav.inform_api_client import InformAPIClient, InformConfig
from py_webdav.caldav.inform_backend import InformCalDAVBackend
from starlette.requests import Request


class MockRequest:
    """Mock request for testing."""

    pass


async def main():
    """Test occurrence-per-event behavior."""
    config = InformConfig()
    owner_key = os.getenv("INFORM_OWNER_KEY", config.username).strip('"')

    backend = InformCalDAVBackend(config=config, owner_key=owner_key)
    request = MockRequest()

    print(f"\n{'='*80}")
    print(f"Testing Occurrence-Per-Event Approach")
    print(f"{'='*80}\n")

    # List calendar objects
    print("Step 1: List calendar objects")
    print("-" * 80)

    calendar_path = "/calendars/test/calendar/"
    objects = await backend.list_calendar_objects(request, calendar_path)

    print(f"Total objects returned: {len(objects)}")

    # Group by event key
    by_key = {}
    for obj in objects:
        path = obj.path
        # Extract key and occurrence ID from path
        filename = path.split("/")[-1].replace(".ics", "")
        if "-" in filename:
            key, occ_id = filename.rsplit("-", 1)
        else:
            key = filename
            occ_id = None

        if key not in by_key:
            by_key[key] = []
        by_key[key].append(occ_id if occ_id else "single")

    print(f"\nEvents breakdown:")
    for key, occs in sorted(by_key.items()):
        if len(occs) > 1:
            print(f"  {key}: {len(occs)} occurrences")
            if len(occs) <= 5:
                for occ in occs:
                    print(f"    - {occ}")
        else:
            print(f"  {key}: single event")

    print(f"\n{'='*80}")
    print(f"Step 2: Examine individual objects")
    print(f"{'='*80}\n")

    # Show first 3 objects
    for i, obj in enumerate(objects[:3], 1):
        print(f"\nObject {i}:")
        print(f"  Path: {obj.path}")
        print(f"  ETag: {obj.etag[:16]}...")

        # Parse the iCalendar data to show UID
        from icalendar import Calendar

        cal = Calendar.from_ical(obj.data)
        for component in cal.walk():
            if component.name == "VEVENT":
                uid = component.get("UID")
                summary = component.get("SUMMARY")
                dtstart = component.get("DTSTART")
                has_rrule = "RRULE" in component

                print(f"  UID: {uid}")
                print(f"  Summary: {summary}")
                print(f"  DTSTART: {dtstart.dt if dtstart else 'N/A'}")
                print(f"  Has RRULE: {has_rrule}")

    print(f"\n{'='*80}")
    print(f"Verification:")
    print(f"{'='*80}\n")

    # Verify each occurrence has unique UID
    uids = set()
    paths = set()
    for obj in objects:
        paths.add(obj.path)
        cal = Calendar.from_ical(obj.data)
        for component in cal.walk():
            if component.name == "VEVENT":
                uid = str(component.get("UID"))
                uids.add(uid)
                # Check if has RRULE
                if "RRULE" in component:
                    print(f"✗ WARNING: Object {obj.path} has RRULE (should be single event)")

    print(f"✓ Total objects: {len(objects)}")
    print(f"✓ Unique paths: {len(paths)}")
    print(f"✓ Unique UIDs: {len(uids)}")

    if len(objects) == len(paths) == len(uids):
        print(f"\n✓ All objects have unique paths and UIDs")
    else:
        print(f"\n✗ WARNING: Mismatch in object/path/UID counts")

    # Count series events
    series_count = sum(1 for occs in by_key.values() if len(occs) > 1)
    single_count = sum(1 for occs in by_key.values() if len(occs) == 1)

    print(f"\n✓ Series events (returned as multiple objects): {series_count}")
    print(f"✓ Single events: {single_count}")

    await backend.api_client.close()


if __name__ == "__main__":
    asyncio.run(main())
