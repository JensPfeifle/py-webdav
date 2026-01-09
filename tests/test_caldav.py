"""Tests for CalDAV functionality."""

import pytest

from py_webdav.caldav import validate_calendar_object


def test_validate_calendar_object_vevent():
    """Test validating a calendar event."""
    ical_data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-event-123
DTSTART:20240101T100000Z
DTEND:20240101T110000Z
SUMMARY:Test Event
END:VEVENT
END:VCALENDAR"""

    event_type, uid = validate_calendar_object(ical_data)

    assert event_type == "VEVENT", f"Expected VEVENT, got {event_type}"
    assert uid == "test-event-123", f"Expected test-event-123, got {uid}"


def test_validate_calendar_object_vtodo():
    """Test validating a calendar todo."""
    ical_data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VTODO
UID:test-todo-456
SUMMARY:Test Todo
DUE:20240201T100000Z
END:VTODO
END:VCALENDAR"""

    event_type, uid = validate_calendar_object(ical_data)

    assert event_type == "VTODO", f"Expected VTODO, got {event_type}"
    assert uid == "test-todo-456", f"Expected test-todo-456, got {uid}"


def test_validate_calendar_object_with_method_fails():
    """Test that calendar with METHOD property is rejected."""
    ical_data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:test-event-789
DTSTART:20240101T100000Z
SUMMARY:Test Event
END:VEVENT
END:VCALENDAR"""

    with pytest.raises(ValueError, match="must not specify METHOD"):
        validate_calendar_object(ical_data)


def test_validate_calendar_object_conflicting_types():
    """Test that calendar with multiple event types is rejected."""
    ical_data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-event-1
DTSTART:20240101T100000Z
SUMMARY:Test Event
END:VEVENT
BEGIN:VTODO
UID:test-todo-1
SUMMARY:Test Todo
END:VTODO
END:VCALENDAR"""

    with pytest.raises(ValueError, match="conflicting event types"):
        validate_calendar_object(ical_data)


def test_validate_calendar_object_conflicting_uids():
    """Test that calendar with conflicting UIDs is rejected."""
    ical_data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-event-1
DTSTART:20240101T100000Z
SUMMARY:Test Event 1
END:VEVENT
BEGIN:VEVENT
UID:test-event-2
DTSTART:20240102T100000Z
SUMMARY:Test Event 2
END:VEVENT
END:VCALENDAR"""

    with pytest.raises(ValueError, match="conflicting UID"):
        validate_calendar_object(ical_data)
