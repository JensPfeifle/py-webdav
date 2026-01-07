"""CalDAV types and calendar support.

CalDAV is defined in RFC 4791.

TODO: Full implementation pending - this is a minimal stub to allow imports.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Calendar:
    """CalDAV calendar."""

    path: str
    name: str = ""
    description: str = ""
    max_resource_size: int = 0
    supported_component_set: list[str] | None = None


@dataclass
class CalendarObject:
    """CalDAV calendar object."""

    path: str
    data: str  # iCalendar data
    etag: str = ""
    content_type: str = "text/calendar"


# Capability constant
CAPABILITY_CALENDAR = "calendar-access"


def validate_calendar_object(ical_data: str) -> tuple[str, str]:
    """Validate a calendar object according to RFC 4791 section 4.1.

    Args:
        ical_data: iCalendar data

    Returns:
        Tuple of (event_type, uid)

    Raises:
        ValueError: If validation fails

    TODO: Implement full validation
    """
    # Minimal implementation - just return dummy values
    return "VEVENT", "placeholder-uid"
