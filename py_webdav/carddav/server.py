"""CardDAV server implementation."""

from __future__ import annotations

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
) -> Response:
    """Handle CardDAV PROPFIND request.

    Args:
        request: Starlette request
        propfind: PropFind request
        depth: Depth header value
        addressbook_home_path: Path to addressbook home set
        principal_path: Path to user principal

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

            # TODO: If depth > 0, list all addressbooks within the home set
            # For now, just list the home set itself

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
