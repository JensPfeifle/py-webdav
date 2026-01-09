"""CalDAV types and calendar support.

CalDAV is defined in RFC 4791.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# CalDAV capability
CAPABILITY_CALENDAR = "calendar-access"


@dataclass
class Calendar:
    """CalDAV calendar collection."""

    path: str
    name: str = ""
    description: str = ""
    max_resource_size: int = 0
    supported_component_set: list[str] = field(default_factory=list)


@dataclass
class CalendarObject:
    """CalDAV calendar object (iCalendar data)."""

    path: str
    data: str  # iCalendar data as string
    mod_time: datetime | None = None
    content_length: int = 0
    etag: str = ""


@dataclass
class CalendarCompRequest:
    """Calendar component request for PROPFIND."""

    name: str
    allprops: bool = False
    props: list[str] = field(default_factory=list)
    allcomps: bool = False
    comps: list[CalendarCompRequest] = field(default_factory=list)
    expand: CalendarExpandRequest | None = None


@dataclass
class CalendarExpandRequest:
    """Request to expand recurring events."""

    start: datetime
    end: datetime


@dataclass
class TextMatch:
    """Text matching filter."""

    text: str
    negate_condition: bool = False


@dataclass
class ParamFilter:
    """Parameter filter for calendar queries."""

    name: str
    is_not_defined: bool = False
    text_match: TextMatch | None = None


@dataclass
class PropFilter:
    """Property filter for calendar queries."""

    name: str
    is_not_defined: bool = False
    start: datetime | None = None
    end: datetime | None = None
    text_match: TextMatch | None = None
    param_filters: list[ParamFilter] = field(default_factory=list)


@dataclass
class CompFilter:
    """Component filter for calendar queries."""

    name: str
    is_not_defined: bool = False
    start: datetime | None = None
    end: datetime | None = None
    props: list[PropFilter] = field(default_factory=list)
    comps: list[CompFilter] = field(default_factory=list)


@dataclass
class CalendarQuery:
    """CalDAV calendar-query REPORT request."""

    comp_request: CalendarCompRequest
    comp_filter: CompFilter


@dataclass
class CalendarMultiGet:
    """CalDAV calendar-multiget REPORT request."""

    paths: list[str]
    comp_request: CalendarCompRequest


@dataclass
class SyncQuery:
    """CalDAV sync-collection request."""

    comp_request: CalendarCompRequest
    sync_token: str
    limit: int = 0  # <= 0 means unlimited


@dataclass
class SyncResponse:
    """CalDAV sync-collection response."""

    sync_token: str
    updated: list[CalendarObject] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)


def validate_calendar_object(ical_data: str) -> tuple[str, str]:
    """Validate a calendar object according to RFC 4791 section 4.1.

    Args:
        ical_data: iCalendar data as string

    Returns:
        Tuple of (event_type, uid)

    Raises:
        ValueError: If validation fails
    """
    try:
        from icalendar import Calendar as ICalendar

        cal = ICalendar.from_ical(ical_data)

        # Calendar object resources MUST NOT specify the METHOD property
        if cal.get("METHOD"):
            raise ValueError("calendar resource must not specify METHOD property")

        event_type = ""
        uid = ""

        for component in cal.walk():
            comp_name = component.name

            # Skip VCALENDAR and VTIMEZONE
            if comp_name in ("VCALENDAR", "VTIMEZONE"):
                continue

            # Check for conflicting event types
            if not event_type:
                if comp_name is None:
                    raise ValueError("Event type is None")
                else:
                    event_type = comp_name
            elif event_type != comp_name:
                raise ValueError(f"conflicting event types in calendar: {event_type}, {comp_name}")

            # Check UID
            comp_uid = str(component.get("UID", ""))
            if not uid:
                uid = comp_uid
            elif comp_uid and uid != comp_uid:
                raise ValueError(f"conflicting UID values in calendar: {uid}, {comp_uid}")

        return event_type, uid

    except Exception as e:
        raise ValueError(f"invalid calendar object: {e}") from e
