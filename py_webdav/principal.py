"""Principal discovery support for CalDAV/CardDAV."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from lxml import etree
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from .internal import (
    CurrentUserPrincipal,
    Href,
    HTTPError,
    MultiStatus,
    PropFind,
)
from .internal import (
    Response as WebDAVResponse,
)
from .internal.elements import COLLECTION, NAMESPACE, PRINCIPAL
from .internal.server import decode_xml_request, is_request_body_empty, serve_multistatus


@dataclass
class PrincipalOptions:
    """Options for serving principal URLs."""

    current_user_principal_path: str = "/principals/current/"
    calendar_home_set_path: str | None = None
    addressbook_home_set_path: str | None = None
    capabilities: list[str] = field(default_factory=lambda: ["calendar-access", "addressbook"])


async def serve_principal(request: Request, options: PrincipalOptions) -> Response:
    """Serve principal URL requests.

    This handles requests to virtual principal paths like /principals/current/
    that are used for CalDAV/CardDAV discovery.

    Args:
        request: Starlette request
        options: Principal options

    Returns:
        Starlette response
    """
    if request.method == "OPTIONS":
        return _handle_principal_options(options)
    elif request.method == "PROPFIND":
        return await _handle_principal_propfind(request, options)
    else:
        return Response(content="Method not allowed", status_code=405)


def _handle_principal_options(options: PrincipalOptions) -> Response:
    """Handle OPTIONS request for principal."""
    caps = ["1", "3"]  # WebDAV class 1 and 3
    if options.capabilities:
        caps.extend(options.capabilities)

    allow = ["OPTIONS", "PROPFIND", "REPORT", "DELETE", "MKCOL"]

    headers = {
        "DAV": ", ".join(caps),
        "Allow": ", ".join(allow),
    }

    return Response(status_code=204, headers=headers)


async def _handle_principal_propfind(request: Request, options: PrincipalOptions) -> Response:
    """Handle PROPFIND request for principal."""
    try:
        # Parse PROPFIND request
        if await is_request_body_empty(request):
            # Empty PROPFIND body means allprop
            propfind = PropFind(allprop=True)
        else:
            xml_elem = await decode_xml_request(request, PropFind)
            propfind = PropFind.from_xml(xml_elem)

        # Build property functions
        props: dict[str, Callable] = {}

        # Resource type - this is a principal
        props[f"{{{NAMESPACE}}}resourcetype"] = lambda: _create_resource_type_principal()

        # Current user principal - self-reference
        props[f"{{{NAMESPACE}}}current-user-principal"] = lambda: _create_current_user_principal(
            options.current_user_principal_path
        )

        # Calendar home set (if configured)
        if options.calendar_home_set_path:
            props["{urn:ietf:params:xml:ns:caldav}calendar-home-set"] = (
                lambda: _create_calendar_home_set(str(options.calendar_home_set_path))
            )

        # Addressbook home set (if configured)
        if options.addressbook_home_set_path:
            props["{urn:ietf:params:xml:ns:carddav}addressbook-home-set"] = (
                lambda: _create_addressbook_home_set(str(options.addressbook_home_set_path))
            )

        # Create response
        resp = _create_propfind_response(request.url.path, propfind, props)
        ms = MultiStatus(responses=[resp])

        return serve_multistatus(ms)

    except HTTPError as e:
        return Response(content=str(e), status_code=e.code)
    except Exception as e:
        return Response(content=f"Internal error: {e}", status_code=500)


def _create_resource_type_principal() -> etree._Element:
    """Create resourcetype XML element for principal."""
    rt = etree.Element(f"{{{NAMESPACE}}}resourcetype")
    etree.SubElement(rt, COLLECTION)
    etree.SubElement(rt, PRINCIPAL)
    return rt


def _create_current_user_principal(path: str) -> etree._Element:
    """Create current-user-principal XML element."""
    cup = CurrentUserPrincipal(href=Href.from_string(path))
    return cup.to_xml()


def _create_calendar_home_set(path: str) -> etree._Element:
    """Create calendar-home-set XML element."""
    elem = etree.Element("{urn:ietf:params:xml:ns:caldav}calendar-home-set")
    href = etree.SubElement(elem, f"{{{NAMESPACE}}}href")
    href.text = path
    return elem


def _create_addressbook_home_set(path: str) -> etree._Element:
    """Create addressbook-home-set XML element."""
    elem = etree.Element("{urn:ietf:params:xml:ns:carddav}addressbook-home-set")
    href = etree.SubElement(elem, f"{{{NAMESPACE}}}href")
    href.text = path
    return elem


def _create_propfind_response(
    href: str, propfind: PropFind, props: dict[str, Callable]
) -> WebDAVResponse:
    """Create a PROPFIND response.

    Args:
        href: Resource href
        propfind: PROPFIND request
        props: Property functions

    Returns:
        WebDAV Response
    """
    from .internal.elements import Prop, PropStat, Status

    # Determine which properties to return
    requested_props = []
    if propfind.allprop:
        requested_props = list(props.keys())
    elif propfind.propname:
        # Return just property names
        requested_props = list(props.keys())
    elif propfind.prop:
        # Return requested properties
        for prop_elem in propfind.prop.raw:
            ns = prop_elem.nsmap.get(prop_elem.prefix, "")
            tag = prop_elem.tag.split("}")[-1]
            prop_name = f"{{{ns}}}{tag}"
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
        propstat = PropStat(prop=prop, status=Status(code=200, text="OK"), response_description="")
        propstats.append(propstat)

    if not_found_props:
        # Create 404 propstat for not found properties
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
        hrefs=[Href.from_string(href)],
        propstats=propstats,
        status=None,
    )


async def handle_well_known_redirect(request: Request, target: str) -> RedirectResponse:
    """Handle /.well-known/* redirects.

    Args:
        request: Starlette request
        target: Target path to redirect to

    Returns:
        Redirect response
    """
    return RedirectResponse(url=target, status_code=308)  # Permanent Redirect
