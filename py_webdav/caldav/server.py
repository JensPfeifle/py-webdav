"""CalDAV server implementation."""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import Protocol

from lxml import etree
from starlette.requests import Request
from starlette.responses import Response

from ..internal import (
    CurrentUserPrincipal,
    Depth,
    Href,
    MultiStatus,
    PropFind,
)
from ..internal import Response as WebDAVResponse
from ..internal.elements import COLLECTION, NAMESPACE
from ..internal.server import serve_multistatus


class ResourceType(IntEnum):
    """CalDAV resource types based on path depth."""

    ROOT = 0
    USER_PRINCIPAL = 1
    CALENDAR_HOME_SET = 1
    CALENDAR = 2
    CALENDAR_OBJECT = 3


class CalDAVBackend(Protocol):
    """CalDAV backend interface."""

    async def current_user_principal(self, request: Request) -> str:
        """Get current user principal path."""
        ...

    async def calendar_home_set_path(self, request: Request) -> str:
        """Get calendar home set path."""
        ...


def detect_resource_type(path: str, prefix: str = "") -> ResourceType:
    """Detect resource type based on path depth.

    Args:
        path: Request path
        prefix: Path prefix to strip

    Returns:
        Resource type
    """
    # Clean and normalize path
    p = path
    if prefix:
        p = p.removeprefix(prefix.rstrip("/"))
    if not p.startswith("/"):
        p = "/" + p

    if p == "/":
        return ResourceType.ROOT

    # Count path segments (depth)
    depth = len([s for s in p.split("/") if s])
    return ResourceType(min(depth, ResourceType.CALENDAR_OBJECT))


async def handle_caldav_propfind(
    request: Request,
    propfind: PropFind,
    depth: Depth,
    calendar_home_path: str,
    principal_path: str,
    backend: CalDAVBackend | None = None,
) -> Response:
    """Handle CalDAV PROPFIND request.

    Args:
        request: Starlette request
        propfind: PropFind request
        depth: Depth header value
        calendar_home_path: Path to calendar home set
        principal_path: Path to user principal
        backend: CalDAV backend instance (optional)

    Returns:
        Multi-status response
    """
    resource_type = detect_resource_type(request.url.path)
    responses = []

    if resource_type == ResourceType.CALENDAR_HOME_SET:
        if request.url.path == calendar_home_path:
            # This is the calendar home set
            resp = _propfind_calendar_home_set(
                calendar_home_path, propfind, principal_path, calendar_home_path
            )
            responses.append(resp)

            # If depth > 0, list all calendars within the home set
            if depth == Depth.ONE and backend is not None:
                calendars = await backend.list_calendars(request)
                for calendar in calendars:
                    resp = _propfind_calendar(calendar, propfind, principal_path, calendar_home_path)
                    responses.append(resp)

    elif resource_type == ResourceType.CALENDAR:
        # Individual calendar PROPFIND
        if backend is not None:
            try:
                calendar = await backend.get_calendar(request, request.url.path)
                resp = _propfind_calendar(calendar, propfind, principal_path, calendar_home_path)
                responses.append(resp)

                # If depth > 0, list calendar objects
                if depth == Depth.ONE:
                    objects = await backend.list_calendar_objects(request, calendar.path)
                    for obj in objects:
                        resp = _propfind_calendar_object(obj, propfind)
                        responses.append(resp)
            except Exception:
                # Calendar not found or error
                pass

    ms = MultiStatus(responses=responses)
    return serve_multistatus(ms)


def _propfind_calendar_home_set(
    path: str, propfind: PropFind, principal_path: str, home_set_path: str
) -> WebDAVResponse:
    """Create PROPFIND response for calendar home set.

    Args:
        path: Home set path
        propfind: PropFind request
        principal_path: User principal path
        home_set_path: Calendar home set path

    Returns:
        WebDAV Response
    """
    from ..internal.elements import Prop, PropStat, Status

    # Build property functions
    props: dict[str, callable] = {}

    # Resource type - collection
    props[f"{{{NAMESPACE}}}resourcetype"] = lambda: _create_resource_type_collection()

    # Current user principal
    props[f"{{{NAMESPACE}}}current-user-principal"] = (
        lambda: _create_current_user_principal(principal_path)
    )

    # Calendar home set - self-reference
    props["{urn:ietf:params:xml:ns:caldav}calendar-home-set"] = (
        lambda: _create_calendar_home_set(home_set_path)
    )

    # Display name
    props[f"{{{NAMESPACE}}}displayname"] = lambda: _create_displayname("Calendars")

    # Determine which properties to return
    requested_props = []
    if propfind.allprop:
        requested_props = list(props.keys())
    elif propfind.propname:
        requested_props = list(props.keys())
    elif propfind.prop:
        for prop_elem in propfind.prop.raw:
            # Get the full qualified name
            if "}" in prop_elem.tag:
                prop_name = prop_elem.tag
            else:
                ns = prop_elem.nsmap.get(prop_elem.prefix) if prop_elem.prefix else ""
                tag = prop_elem.tag.split("}")[-1]
                prop_name = f"{{{ns}}}{tag}" if ns else tag
            requested_props.append(prop_name)

    # Build prop element with found properties
    found_props = []
    not_found_props = []

    for prop_name in requested_props:
        if prop_name in props:
            try:
                prop_value = props[prop_name]()
                found_props.append(prop_value)
            except Exception:
                not_found_props.append(prop_name)
        else:
            not_found_props.append(prop_name)

    # Create propstats
    propstats = []

    if found_props:
        prop = Prop(raw=found_props)
        propstat = PropStat(
            prop=prop, status=Status(code=200, text="OK"), response_description=""
        )
        propstats.append(propstat)

    if not_found_props:
        not_found_elements = []
        for prop_name in not_found_props:
            elem = etree.Element(prop_name)
            not_found_elements.append(elem)

        prop = Prop(raw=not_found_elements)
        propstat = PropStat(
            prop=prop, status=Status(code=404, text="Not Found"), response_description=""
        )
        propstats.append(propstat)

    return WebDAVResponse(
        hrefs=[Href.from_string(path)],
        propstats=propstats,
        status=None,
    )


def _create_resource_type_collection() -> etree.Element:
    """Create resourcetype XML element for collection."""
    rt = etree.Element(f"{{{NAMESPACE}}}resourcetype")
    etree.SubElement(rt, COLLECTION)
    return rt


def _create_current_user_principal(path: str) -> etree.Element:
    """Create current-user-principal XML element."""
    cup = CurrentUserPrincipal(href=Href.from_string(path))
    return cup.to_xml()


def _create_calendar_home_set(path: str) -> etree.Element:
    """Create calendar-home-set XML element."""
    elem = etree.Element("{urn:ietf:params:xml:ns:caldav}calendar-home-set")
    href = etree.SubElement(elem, f"{{{NAMESPACE}}}href")
    href.text = path
    return elem


def _create_displayname(name: str) -> etree.Element:
    """Create displayname XML element."""
    elem = etree.Element(f"{{{NAMESPACE}}}displayname")
    elem.text = name
    return elem


def _propfind_calendar(
    calendar, propfind: PropFind, principal_path: str, home_set_path: str
) -> WebDAVResponse:
    """Create PROPFIND response for a calendar collection.

    Args:
        calendar: Calendar object
        propfind: PropFind request
        principal_path: User principal path
        home_set_path: Calendar home set path

    Returns:
        WebDAV Response
    """
    from ..internal.elements import Prop, PropStat, Status

    # Build property functions
    props: dict[str, callable] = {}

    # Resource type - collection with calendar
    props[f"{{{NAMESPACE}}}resourcetype"] = lambda: _create_calendar_resourcetype()

    # Current user principal
    props[f"{{{NAMESPACE}}}current-user-principal"] = (
        lambda: _create_current_user_principal(principal_path)
    )

    # Calendar home set
    props["{urn:ietf:params:xml:ns:caldav}calendar-home-set"] = (
        lambda: _create_calendar_home_set(home_set_path)
    )

    # Display name
    props[f"{{{NAMESPACE}}}displayname"] = lambda: _create_displayname(calendar.name)

    # Supported calendar components
    props["{urn:ietf:params:xml:ns:caldav}supported-calendar-component-set"] = (
        lambda: _create_supported_components(calendar.supported_component_set)
    )

    # Determine which properties to return
    requested_props = []
    if propfind.allprop:
        requested_props = list(props.keys())
    elif propfind.propname:
        requested_props = list(props.keys())
    elif propfind.prop:
        for prop_elem in propfind.prop.raw:
            if "}" in prop_elem.tag:
                prop_name = prop_elem.tag
            else:
                ns = prop_elem.nsmap.get(prop_elem.prefix) if prop_elem.prefix else ""
                tag = prop_elem.tag.split("}")[-1]
                prop_name = f"{{{ns}}}{tag}" if ns else tag
            requested_props.append(prop_name)

    # Build prop element with found properties
    found_props = []
    not_found_props = []

    for prop_name in requested_props:
        if prop_name in props:
            try:
                prop_value = props[prop_name]()
                found_props.append(prop_value)
            except Exception:
                not_found_props.append(prop_name)
        else:
            not_found_props.append(prop_name)

    # Create propstats
    propstats = []

    if found_props:
        prop = Prop(raw=found_props)
        propstat = PropStat(
            prop=prop, status=Status(code=200, text="OK"), response_description=""
        )
        propstats.append(propstat)

    if not_found_props:
        not_found_elements = []
        for prop_name in not_found_props:
            elem = etree.Element(prop_name)
            not_found_elements.append(elem)

        prop = Prop(raw=not_found_elements)
        propstat = PropStat(
            prop=prop, status=Status(code=404, text="Not Found"), response_description=""
        )
        propstats.append(propstat)

    return WebDAVResponse(
        hrefs=[Href.from_string(calendar.path)],
        propstats=propstats,
        status=None,
    )


def _propfind_calendar_object(obj, propfind: PropFind) -> WebDAVResponse:
    """Create PROPFIND response for a calendar object.

    Args:
        obj: CalendarObject
        propfind: PropFind request

    Returns:
        WebDAV Response
    """
    from ..internal.elements import Prop, PropStat, Status

    # Build property functions
    props: dict[str, callable] = {}

    # Resource type - empty for non-collections
    props[f"{{{NAMESPACE}}}resourcetype"] = lambda: etree.Element(f"{{{NAMESPACE}}}resourcetype")

    # ETag
    props[f"{{{NAMESPACE}}}getetag"] = lambda: _create_etag(obj.etag)

    # Content length
    props[f"{{{NAMESPACE}}}getcontentlength"] = lambda: _create_content_length(obj.content_length)

    # Content type
    props[f"{{{NAMESPACE}}}getcontenttype"] = lambda: _create_content_type("text/calendar")

    # Last modified
    if obj.mod_time:
        props[f"{{{NAMESPACE}}}getlastmodified"] = lambda: _create_last_modified(obj.mod_time)

    # Determine which properties to return
    requested_props = []
    if propfind.allprop:
        requested_props = list(props.keys())
    elif propfind.propname:
        requested_props = list(props.keys())
    elif propfind.prop:
        for prop_elem in propfind.prop.raw:
            if "}" in prop_elem.tag:
                prop_name = prop_elem.tag
            else:
                ns = prop_elem.nsmap.get(prop_elem.prefix) if prop_elem.prefix else ""
                tag = prop_elem.tag.split("}")[-1]
                prop_name = f"{{{ns}}}{tag}" if ns else tag
            requested_props.append(prop_name)

    # Build prop element with found properties
    found_props = []
    not_found_props = []

    for prop_name in requested_props:
        if prop_name in props:
            try:
                prop_value = props[prop_name]()
                found_props.append(prop_value)
            except Exception:
                not_found_props.append(prop_name)
        else:
            not_found_props.append(prop_name)

    # Create propstats
    propstats = []

    if found_props:
        prop = Prop(raw=found_props)
        propstat = PropStat(
            prop=prop, status=Status(code=200, text="OK"), response_description=""
        )
        propstats.append(propstat)

    if not_found_props:
        not_found_elements = []
        for prop_name in not_found_props:
            elem = etree.Element(prop_name)
            not_found_elements.append(elem)

        prop = Prop(raw=not_found_elements)
        propstat = PropStat(
            prop=prop, status=Status(code=404, text="Not Found"), response_description=""
        )
        propstats.append(propstat)

    return WebDAVResponse(
        hrefs=[Href.from_string(obj.path)],
        propstats=propstats,
        status=None,
    )


def _create_calendar_resourcetype() -> etree.Element:
    """Create resourcetype XML element for calendar."""
    rt = etree.Element(f"{{{NAMESPACE}}}resourcetype")
    etree.SubElement(rt, COLLECTION)
    etree.SubElement(rt, "{urn:ietf:params:xml:ns:caldav}calendar")
    return rt


def _create_supported_components(components: list[str]) -> etree.Element:
    """Create supported-calendar-component-set XML element."""
    elem = etree.Element("{urn:ietf:params:xml:ns:caldav}supported-calendar-component-set")
    for comp in components:
        comp_elem = etree.SubElement(elem, "{urn:ietf:params:xml:ns:caldav}comp")
        comp_elem.set("name", comp)
    return elem


def _create_etag(etag: str) -> etree.Element:
    """Create getetag XML element."""
    elem = etree.Element(f"{{{NAMESPACE}}}getetag")
    elem.text = f'"{etag}"'
    return elem


def _create_content_length(length: int) -> etree.Element:
    """Create getcontentlength XML element."""
    elem = etree.Element(f"{{{NAMESPACE}}}getcontentlength")
    elem.text = str(length)
    return elem


def _create_content_type(content_type: str) -> etree.Element:
    """Create getcontenttype XML element."""
    elem = etree.Element(f"{{{NAMESPACE}}}getcontenttype")
    elem.text = content_type
    return elem


def _create_last_modified(dt: datetime) -> etree.Element:
    """Create getlastmodified XML element."""
    from email.utils import format_datetime

    elem = etree.Element(f"{{{NAMESPACE}}}getlastmodified")
    elem.text = format_datetime(dt, usegmt=True)
    return elem


async def handle_caldav_report(
    request: Request,
    calendar_home_path: str,
    principal_path: str,
    backend,  # CalDAVBackend
) -> Response:
    """Handle CalDAV REPORT request.

    Args:
        request: Starlette request
        calendar_home_path: Path to calendar home set
        principal_path: Path to user principal
        backend: CalDAV backend instance

    Returns:
        Multi-status response
    """
    from .report import CalendarMultigetReport, CalendarQueryReport, parse_calendar_report

    # Parse REPORT request body
    body = await request.body()
    root = etree.fromstring(body)

    try:
        report = parse_calendar_report(root)
    except ValueError as e:
        from starlette.responses import Response as StarletteResponse

        return StarletteResponse(content=str(e), status_code=400)

    if isinstance(report, CalendarQueryReport):
        return await _handle_calendar_query(request, report, calendar_home_path, principal_path, backend)
    elif isinstance(report, CalendarMultigetReport):
        return await _handle_calendar_multiget(request, report, calendar_home_path, principal_path, backend)
    else:
        from starlette.responses import Response as StarletteResponse

        return StarletteResponse(content="Unknown REPORT type", status_code=400)


async def _handle_calendar_query(
    request: Request,
    query: CalendarQueryReport,
    calendar_home_path: str,
    principal_path: str,
    backend,  # CalDAVBackend
) -> Response:
    """Handle calendar-query REPORT."""
    from .caldav import CalendarQuery

    # Build CalendarQuery from the parsed report
    # For now, we'll return all objects (filtering not yet implemented)
    cal_query = CalendarQuery()

    # Query calendar objects
    try:
        objects = await backend.query_calendar_objects(request, request.url.path, cal_query)
    except Exception:
        # If query fails, return empty list
        objects = []

    # Build PropFind from query
    propfind = PropFind(
        allprop=query.allprop,
        propname=query.propname,
    )

    # Build responses for each object
    responses = []
    for obj in objects:
        resp = _propfind_calendar_object(obj, propfind)
        responses.append(resp)

    ms = MultiStatus(responses=responses)
    return serve_multistatus(ms)


async def _handle_calendar_multiget(
    request: Request,
    multiget: CalendarMultigetReport,
    calendar_home_path: str,
    principal_path: str,
    backend,  # CalDAVBackend
) -> Response:
    """Handle calendar-multiget REPORT."""
    # Build PropFind from multiget
    propfind = PropFind(
        allprop=multiget.allprop,
        propname=multiget.propname,
    )

    # Fetch each requested href
    responses = []
    for href in multiget.hrefs:
        try:
            obj = await backend.get_calendar_object(request, href)
            resp = _propfind_calendar_object(obj, propfind)
            responses.append(resp)
        except Exception:
            # If object not found, skip it
            continue

    ms = MultiStatus(responses=responses)
    return serve_multistatus(ms)
