"""CalDAV REPORT request handling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lxml import etree

NAMESPACE = "DAV:"
CALDAV_NAMESPACE = "urn:ietf:params:xml:ns:caldav"


@dataclass
class CalendarQueryReport:
    """CalDAV calendar-query REPORT request."""

    prop: list[str] | None = None
    allprop: bool = False
    propname: bool = False
    filter: Any | None = None  # CompFilter from query


@dataclass
class CalendarMultigetReport:
    """CalDAV calendar-multiget REPORT request."""

    hrefs: list[str]
    prop: list[str] | None = None
    allprop: bool = False
    propname: bool = False


def parse_calendar_report(root: etree._Element) -> CalendarQueryReport | CalendarMultigetReport:
    """Parse CalDAV REPORT request body.

    Args:
        root: XML root element

    Returns:
        Parsed REPORT request

    Raises:
        ValueError: If the REPORT request is invalid
    """
    # Check if it's calendar-query
    if root.tag == f"{{{CALDAV_NAMESPACE}}}calendar-query":
        return _parse_calendar_query(root)
    # Check if it's calendar-multiget
    elif root.tag == f"{{{CALDAV_NAMESPACE}}}calendar-multiget":
        return _parse_calendar_multiget(root)
    else:
        raise ValueError(f"Unknown CalDAV REPORT type: {root.tag}")


def _parse_calendar_query(root: etree._Element) -> CalendarQueryReport:
    """Parse calendar-query REPORT."""
    report = CalendarQueryReport()

    # Parse prop/allprop/propname
    for child in root:
        if child.tag == f"{{{NAMESPACE}}}prop":
            report.prop = [prop.tag for prop in child]
        elif child.tag == f"{{{NAMESPACE}}}allprop":
            report.allprop = True
        elif child.tag == f"{{{NAMESPACE}}}propname":
            report.propname = True
        elif child.tag == f"{{{CALDAV_NAMESPACE}}}filter":
            # For now, we'll just note that there's a filter
            # Full filter parsing would go here
            report.filter = child

    return report


def _parse_calendar_multiget(root: etree._Element) -> CalendarMultigetReport:
    """Parse calendar-multiget REPORT."""
    hrefs: list[str] = []
    prop: list[str] | None = None
    allprop = False
    propname = False

    # Parse hrefs and prop/allprop/propname
    for child in root:
        if child.tag == f"{{{NAMESPACE}}}href":
            if child.text:
                hrefs.append(child.text)
        elif child.tag == f"{{{NAMESPACE}}}prop":
            prop = [p.tag for p in child]
        elif child.tag == f"{{{NAMESPACE}}}allprop":
            allprop = True
        elif child.tag == f"{{{NAMESPACE}}}propname":
            propname = True

    return CalendarMultigetReport(
        hrefs=hrefs,
        prop=prop,
        allprop=allprop,
        propname=propname,
    )
