#!/usr/bin/env python3
"""Create sample calendar and addressbook data."""

import json
from pathlib import Path

# Sample iCalendar event
SAMPLE_EVENT = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Example Corp//CalDAV Client//EN
BEGIN:VEVENT
UID:event-001@example.com
DTSTAMP:20250109T120000Z
DTSTART:20250115T100000Z
DTEND:20250115T110000Z
SUMMARY:Team Meeting
DESCRIPTION:Weekly team sync
LOCATION:Conference Room A
END:VEVENT
END:VCALENDAR
"""

# Sample vCard
SAMPLE_VCARD = """BEGIN:VCARD
VERSION:3.0
UID:contact-001@example.com
FN:John Doe
N:Doe;John;;;
EMAIL;TYPE=INTERNET:john.doe@example.com
TEL;TYPE=CELL:+1-555-0100
END:VCARD
"""


def create_sample_data(data_dir: Path):
    """Create sample calendar and addressbook data.

    Args:
        data_dir: Root directory for data
    """
    # Create calendars directory
    calendars_dir = data_dir / "calendars"
    calendars_dir.mkdir(parents=True, exist_ok=True)

    # Create a sample calendar
    work_calendar = calendars_dir / "work"
    work_calendar.mkdir(exist_ok=True)

    # Write calendar metadata
    metadata = {
        "name": "Work Calendar",
        "description": "Work events and meetings",
        "max_resource_size": 0,
        "supported_component_set": ["VEVENT", "VTODO"],
    }
    with open(work_calendar / ".metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    # Write sample event
    with open(work_calendar / "event-001.ics", "w") as f:
        f.write(SAMPLE_EVENT.strip())

    print(f"Created work calendar at: {work_calendar}")

    # Create contacts directory
    contacts_dir = data_dir / "contacts"
    contacts_dir.mkdir(parents=True, exist_ok=True)

    # Create a sample addressbook
    personal_contacts = contacts_dir / "personal"
    personal_contacts.mkdir(exist_ok=True)

    # Write addressbook metadata
    metadata = {
        "name": "Personal Contacts",
        "description": "Personal address book",
        "max_resource_size": 0,
    }
    with open(personal_contacts / ".metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    # Write sample vCard
    with open(personal_contacts / "contact-001.vcf", "w") as f:
        f.write(SAMPLE_VCARD.strip())

    print(f"Created personal contacts at: {personal_contacts}")


if __name__ == "__main__":
    import tempfile

    # Create temporary directory
    temp_dir = Path(tempfile.mkdtemp(prefix="webdav_sample_"))
    print(f"Creating sample data in: {temp_dir}\n")

    create_sample_data(temp_dir)

    print(f"\nSample data created successfully!")
    print(f"\nYou can use this directory with the CalDAV/CardDAV server:")
    print(f"  python examples/caldav_carddav_server.py")
