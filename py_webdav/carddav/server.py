"""CardDAV server implementation."""

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
    """CardDAV resource types based on path depth."""

    ROOT = 0
    USER_PRINCIPAL = 1
    ADDRESSBOOK_HOME_SET = 1
    ADDRESSBOOK = 2
    ADDRESS_OBJECT = 3


class CardDAVBackend(Protocol):
    """CardDAV backend interface."""

    async def current_user_principal(self, request: Request) -> str:
        """Get current user principal path."""
        ...

    async def addressbook_home_set_path(self, request: Request) -> str:
        """Get addressbook home set path."""
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
    return ResourceType(min(depth, ResourceType.ADDRESS_OBJECT))


async def handle_carddav_propfind(
    request: Request,
    propfind: PropFind,
    depth: Depth,
    addressbook_home_path: str,
    principal_path: str,
    backend: CardDAVBackend | None = None,
) -> Response:
    """Handle CardDAV PROPFIND request.

    Args:
        request: Starlette request
        propfind: PropFind request
        depth: Depth header value
        addressbook_home_path: Path to addressbook home set
        principal_path: Path to user principal
        backend: CardDAV backend instance (optional)

    Returns:
        Multi-status response
    """
    resource_type = detect_resource_type(request.url.path)
    responses = []

    if resource_type == ResourceType.ADDRESSBOOK_HOME_SET:
        if request.url.path == addressbook_home_path:
            # This is the addressbook home set
            resp = _propfind_addressbook_home_set(
                addressbook_home_path, propfind, principal_path, addressbook_home_path
            )
            responses.append(resp)

            # If depth > 0, list all addressbooks within the home set
            if depth == Depth.ONE and backend is not None:
                addressbooks = await backend.list_addressbooks(request)
                for addressbook in addressbooks:
                    resp = _propfind_addressbook(addressbook, propfind, principal_path, addressbook_home_path)
                    responses.append(resp)

    elif resource_type == ResourceType.ADDRESSBOOK:
        # Individual addressbook PROPFIND
        if backend is not None:
            try:
                addressbook = await backend.get_addressbook(request, request.url.path)
                resp = _propfind_addressbook(addressbook, propfind, principal_path, addressbook_home_path)
                responses.append(resp)

                # If depth > 0, list address objects
                if depth == Depth.ONE:
                    objects = await backend.list_address_objects(request, addressbook.path)
                    for obj in objects:
                        resp = _propfind_address_object(obj, propfind)
                        responses.append(resp)
            except Exception:
                # Addressbook not found or error
                pass

    ms = MultiStatus(responses=responses)
    return serve_multistatus(ms)


def _propfind_addressbook_home_set(
    path: str, propfind: PropFind, principal_path: str, home_set_path: str
) -> WebDAVResponse:
    """Create PROPFIND response for addressbook home set.

    Args:
        path: Home set path
        propfind: PropFind request
        principal_path: User principal path
        home_set_path: Addressbook home set path

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

    # Addressbook home set - self-reference
    props["{urn:ietf:params:xml:ns:carddav}addressbook-home-set"] = (
        lambda: _create_addressbook_home_set(home_set_path)
    )

    # Display name
    props[f"{{{NAMESPACE}}}displayname"] = lambda: _create_displayname("Contacts")

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


def _create_addressbook_home_set(path: str) -> etree.Element:
    """Create addressbook-home-set XML element."""
    elem = etree.Element("{urn:ietf:params:xml:ns:carddav}addressbook-home-set")
    href = etree.SubElement(elem, f"{{{NAMESPACE}}}href")
    href.text = path
    return elem


def _create_displayname(name: str) -> etree.Element:
    """Create displayname XML element."""
    elem = etree.Element(f"{{{NAMESPACE}}}displayname")
    elem.text = name
    return elem


def _propfind_addressbook(
    addressbook, propfind: PropFind, principal_path: str, home_set_path: str
) -> WebDAVResponse:
    """Create PROPFIND response for an addressbook collection.

    Args:
        addressbook: AddressBook object
        propfind: PropFind request
        principal_path: User principal path
        home_set_path: Addressbook home set path

    Returns:
        WebDAV Response
    """
    from ..internal.elements import Prop, PropStat, Status

    # Build property functions
    props: dict[str, callable] = {}

    # Resource type - collection with addressbook
    props[f"{{{NAMESPACE}}}resourcetype"] = lambda: _create_addressbook_resourcetype()

    # Current user principal
    props[f"{{{NAMESPACE}}}current-user-principal"] = (
        lambda: _create_current_user_principal(principal_path)
    )

    # Addressbook home set
    props["{urn:ietf:params:xml:ns:carddav}addressbook-home-set"] = (
        lambda: _create_addressbook_home_set(home_set_path)
    )

    # Display name
    props[f"{{{NAMESPACE}}}displayname"] = lambda: _create_displayname(addressbook.name)

    # Supported address data (vCard versions)
    props["{urn:ietf:params:xml:ns:carddav}supported-address-data"] = (
        lambda: _create_supported_address_data()
    )

    # Current user privilege set (read/write)
    props[f"{{{NAMESPACE}}}current-user-privilege-set"] = (
        lambda: _create_current_user_privilege_set()
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
        hrefs=[Href.from_string(addressbook.path)],
        propstats=propstats,
        status=None,
    )


def _propfind_address_object(obj, propfind: PropFind) -> WebDAVResponse:
    """Create PROPFIND response for an address object.

    Args:
        obj: AddressObject
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
    props[f"{{{NAMESPACE}}}getcontenttype"] = lambda: _create_content_type("text/vcard")

    # Last modified
    if obj.mod_time:
        props[f"{{{NAMESPACE}}}getlastmodified"] = lambda: _create_last_modified(obj.mod_time)

    # Address data (the actual vCard content)
    CARDDAV_NS = "urn:ietf:params:xml:ns:carddav"
    props[f"{{{CARDDAV_NS}}}address-data"] = lambda: _create_address_data(obj.data)

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


def _create_addressbook_resourcetype() -> etree.Element:
    """Create resourcetype XML element for addressbook."""
    rt = etree.Element(f"{{{NAMESPACE}}}resourcetype")
    etree.SubElement(rt, COLLECTION)
    etree.SubElement(rt, "{urn:ietf:params:xml:ns:carddav}addressbook")
    return rt


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


def _create_supported_address_data() -> etree.Element:
    """Create supported-address-data XML element."""
    CARDDAV_NS = "urn:ietf:params:xml:ns:carddav"
    elem = etree.Element(f"{{{CARDDAV_NS}}}supported-address-data")

    # Add vCard 3.0 support
    addr_data_type = etree.SubElement(elem, f"{{{CARDDAV_NS}}}address-data-type")
    addr_data_type.set("content-type", "text/vcard")
    addr_data_type.set("version", "3.0")

    # Add vCard 4.0 support
    addr_data_type = etree.SubElement(elem, f"{{{CARDDAV_NS}}}address-data-type")
    addr_data_type.set("content-type", "text/vcard")
    addr_data_type.set("version", "4.0")

    return elem


def _create_current_user_privilege_set() -> etree.Element:
    """Create current-user-privilege-set XML element."""
    elem = etree.Element(f"{{{NAMESPACE}}}current-user-privilege-set")

    # Add read privilege
    privilege = etree.SubElement(elem, f"{{{NAMESPACE}}}privilege")
    etree.SubElement(privilege, f"{{{NAMESPACE}}}read")

    # Add write privilege
    privilege = etree.SubElement(elem, f"{{{NAMESPACE}}}privilege")
    etree.SubElement(privilege, f"{{{NAMESPACE}}}write")

    return elem


def _create_address_data(vcard_data: str) -> etree.Element:
    """Create address-data XML element with vCard content."""
    CARDDAV_NS = "urn:ietf:params:xml:ns:carddav"
    elem = etree.Element(f"{{{CARDDAV_NS}}}address-data")
    elem.text = vcard_data
    return elem


async def handle_carddav_report(
    request: Request,
    addressbook_home_path: str,
    principal_path: str,
    backend,  # CardDAVBackend
) -> Response:
    """Handle CardDAV REPORT request.

    Args:
        request: Starlette request
        addressbook_home_path: Path to addressbook home set
        principal_path: Path to user principal
        backend: CardDAV backend instance

    Returns:
        Multi-status response
    """
    from .report import AddressBookMultigetReport, AddressBookQueryReport, parse_addressbook_report

    # Parse REPORT request body
    body = await request.body()
    root = etree.fromstring(body)

    try:
        report = parse_addressbook_report(root)
    except ValueError as e:
        from starlette.responses import Response as StarletteResponse

        return StarletteResponse(content=str(e), status_code=400)

    if isinstance(report, AddressBookQueryReport):
        return await _handle_addressbook_query(request, report, addressbook_home_path, principal_path, backend)
    elif isinstance(report, AddressBookMultigetReport):
        return await _handle_addressbook_multiget(request, report, addressbook_home_path, principal_path, backend)
    else:
        from starlette.responses import Response as StarletteResponse

        return StarletteResponse(content="Unknown REPORT type", status_code=400)


async def _handle_addressbook_query(
    request: Request,
    query: AddressBookQueryReport,
    addressbook_home_path: str,
    principal_path: str,
    backend,  # CardDAVBackend
) -> Response:
    """Handle addressbook-query REPORT."""
    from .carddav import AddressBookQuery
    from ..internal.elements import Prop

    # Build AddressBookQuery from the parsed report
    # For now, we'll return all objects (filtering not yet implemented)
    ab_query = AddressBookQuery()

    # Query address objects
    try:
        objects = await backend.query_address_objects(request, request.url.path, ab_query)
    except Exception:
        # If query fails, return empty list
        objects = []

    # Build PropFind from query
    prop_obj = None
    if query.prop:
        # Convert tag names to etree.Element objects
        prop_elements = [etree.Element(tag) for tag in query.prop]
        prop_obj = Prop(raw=prop_elements)

    propfind = PropFind(
        prop=prop_obj,
        allprop=query.allprop,
        propname=query.propname,
    )

    # Build responses for each object
    responses = []
    for obj in objects:
        resp = _propfind_address_object(obj, propfind)
        responses.append(resp)

    ms = MultiStatus(responses=responses)
    return serve_multistatus(ms)


async def _handle_addressbook_multiget(
    request: Request,
    multiget: AddressBookMultigetReport,
    addressbook_home_path: str,
    principal_path: str,
    backend,  # CardDAVBackend
) -> Response:
    """Handle addressbook-multiget REPORT."""
    from ..internal.elements import Prop

    # Build PropFind from multiget
    prop_obj = None
    if multiget.prop:
        # Convert tag names to etree.Element objects
        prop_elements = [etree.Element(tag) for tag in multiget.prop]
        prop_obj = Prop(raw=prop_elements)

    propfind = PropFind(
        prop=prop_obj,
        allprop=multiget.allprop,
        propname=multiget.propname,
    )

    # Fetch each requested href
    responses = []
    for href in multiget.hrefs:
        try:
            obj = await backend.get_address_object(request, href)
            resp = _propfind_address_object(obj, propfind)
            responses.append(resp)
        except Exception:
            # If object not found, skip it
            continue

    ms = MultiStatus(responses=responses)
    return serve_multistatus(ms)
