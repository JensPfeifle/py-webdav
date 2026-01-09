"""CardDAV REPORT request handling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lxml import etree

NAMESPACE = "DAV:"
CARDDAV_NAMESPACE = "urn:ietf:params:xml:ns:carddav"


@dataclass
class AddressBookQueryReport:
    """CardDAV addressbook-query REPORT request."""

    prop: list[str] | None = None
    allprop: bool = False
    propname: bool = False
    filter: Any | None = None  # PropFilter from query


@dataclass
class AddressBookMultigetReport:
    """CardDAV addressbook-multiget REPORT request."""

    hrefs: list[str]
    prop: list[str] | None = None
    allprop: bool = False
    propname: bool = False


def parse_addressbook_report(root: etree._Element) -> AddressBookQueryReport | AddressBookMultigetReport:
    """Parse CardDAV REPORT request body.

    Args:
        root: XML root element

    Returns:
        Parsed REPORT request

    Raises:
        ValueError: If the REPORT request is invalid
    """
    # Check if it's addressbook-query
    if root.tag == f"{{{CARDDAV_NAMESPACE}}}addressbook-query":
        return _parse_addressbook_query(root)
    # Check if it's addressbook-multiget
    elif root.tag == f"{{{CARDDAV_NAMESPACE}}}addressbook-multiget":
        return _parse_addressbook_multiget(root)
    else:
        raise ValueError(f"Unknown CardDAV REPORT type: {root.tag}")


def _parse_addressbook_query(root: etree._Element) -> AddressBookQueryReport:
    """Parse addressbook-query REPORT."""
    report = AddressBookQueryReport()

    # Parse prop/allprop/propname
    for child in root:
        if child.tag == f"{{{NAMESPACE}}}prop":
            report.prop = [prop.tag for prop in child]
        elif child.tag == f"{{{NAMESPACE}}}allprop":
            report.allprop = True
        elif child.tag == f"{{{NAMESPACE}}}propname":
            report.propname = True
        elif child.tag == f"{{{CARDDAV_NAMESPACE}}}filter":
            # For now, we'll just note that there's a filter
            # Full filter parsing would go here
            report.filter = child

    return report


def _parse_addressbook_multiget(root: etree._Element) -> AddressBookMultigetReport:
    """Parse addressbook-multiget REPORT."""
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

    return AddressBookMultigetReport(
        hrefs=hrefs,
        prop=prop,
        allprop=allprop,
        propname=propname,
    )
