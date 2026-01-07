"""WebDAV XML elements."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus
from typing import Any
from urllib.parse import ParseResult as URL, urlparse

from lxml import etree

from .internal import HTTPError

# WebDAV namespace
NAMESPACE = "DAV:"
NS = {"D": NAMESPACE}

# Common XML names
RESOURCE_TYPE = "{DAV:}resourcetype"
DISPLAY_NAME = "{DAV:}displayname"
GET_CONTENT_LENGTH = "{DAV:}getcontentlength"
GET_CONTENT_TYPE = "{DAV:}getcontenttype"
GET_LAST_MODIFIED = "{DAV:}getlastmodified"
GET_ETAG = "{DAV:}getetag"
COLLECTION = "{DAV:}collection"
PRINCIPAL = "{DAV:}principal"
CURRENT_USER_PRINCIPAL = "{DAV:}current-user-principal"
CURRENT_USER_PRIVILEGE_SET = "{DAV:}current-user-privilege-set"


@dataclass
class Status:
    """HTTP status for WebDAV responses."""

    code: int
    text: str = ""

    def to_string(self) -> str:
        """Marshal status to text."""
        text = self.text if self.text else HTTPStatus(self.code).phrase
        return f"HTTP/1.1 {self.code} {text}"

    @staticmethod
    def from_string(s: str) -> Status:
        """Unmarshal status from text."""
        if not s:
            return Status(code=0)

        parts = s.split(" ", 2)
        if len(parts) != 3:
            raise ValueError(f"webdav: invalid HTTP status {s!r}: expected 3 fields")

        try:
            code = int(parts[1])
        except ValueError as e:
            raise ValueError(
                f"webdav: invalid HTTP status {s!r}: failed to parse code: {e}"
            ) from e

        return Status(code=code, text=parts[2])

    def err(self) -> Exception | None:
        """Convert status to error if not OK."""
        if self.code == 200:
            return None
        return HTTPError(self.code)


@dataclass
class Href:
    """WebDAV href element."""

    url: URL

    def __str__(self) -> str:
        return self.url.geturl()

    @staticmethod
    def from_string(s: str) -> Href:
        """Parse href from string."""
        return Href(url=urlparse(s))


@dataclass
class MultiStatus:
    """WebDAV multistatus response."""

    responses: list[Response] = field(default_factory=list)
    response_description: str = ""
    sync_token: str = ""

    def to_xml(self) -> etree.Element:
        """Convert to XML element."""
        root = etree.Element(f"{{{NAMESPACE}}}multistatus")
        for resp in self.responses:
            root.append(resp.to_xml())
        if self.response_description:
            desc = etree.SubElement(root, f"{{{NAMESPACE}}}responsedescription")
            desc.text = self.response_description
        if self.sync_token:
            token = etree.SubElement(root, f"{{{NAMESPACE}}}sync-token")
            token.text = self.sync_token
        return root

    @staticmethod
    def from_xml(element: etree.Element) -> MultiStatus:
        """Parse from XML element."""
        responses = []
        for resp_el in element.findall(f"{{{NAMESPACE}}}response"):
            responses.append(Response.from_xml(resp_el))

        response_desc_el = element.find(f"{{{NAMESPACE}}}responsedescription")
        response_desc = response_desc_el.text if response_desc_el is not None else ""

        sync_token_el = element.find(f"{{{NAMESPACE}}}sync-token")
        sync_token = sync_token_el.text if sync_token_el is not None else ""

        return MultiStatus(
            responses=responses,
            response_description=response_desc,
            sync_token=sync_token,
        )


@dataclass
class Location:
    """WebDAV location element."""

    href: Href

    def to_xml(self) -> etree.Element:
        """Convert to XML element."""
        loc = etree.Element(f"{{{NAMESPACE}}}location")
        href_el = etree.SubElement(loc, f"{{{NAMESPACE}}}href")
        href_el.text = str(self.href)
        return loc


@dataclass
class Error:
    """WebDAV error element."""

    raw: list[etree.Element] = field(default_factory=list)

    def __str__(self) -> str:
        if self.raw:
            return etree.tostring(self.raw[0], encoding="unicode")
        return "webdav error"


@dataclass
class PropStat:
    """WebDAV propstat element."""

    prop: Prop
    status: Status
    response_description: str = ""
    error: Error | None = None

    def to_xml(self) -> etree.Element:
        """Convert to XML element."""
        propstat = etree.Element(f"{{{NAMESPACE}}}propstat")
        propstat.append(self.prop.to_xml())

        status_el = etree.SubElement(propstat, f"{{{NAMESPACE}}}status")
        status_el.text = self.status.to_string()

        if self.response_description:
            desc = etree.SubElement(propstat, f"{{{NAMESPACE}}}responsedescription")
            desc.text = self.response_description

        return propstat

    @staticmethod
    def from_xml(element: etree.Element) -> PropStat:
        """Parse from XML element."""
        prop_el = element.find(f"{{{NAMESPACE}}}prop")
        prop = Prop.from_xml(prop_el) if prop_el is not None else Prop()

        status_el = element.find(f"{{{NAMESPACE}}}status")
        status_text = status_el.text if status_el is not None else ""
        status = Status.from_string(status_text)

        desc_el = element.find(f"{{{NAMESPACE}}}responsedescription")
        desc = desc_el.text if desc_el is not None else ""

        return PropStat(prop=prop, status=status, response_description=desc)


@dataclass
class Prop:
    """WebDAV prop element."""

    raw: list[etree.Element] = field(default_factory=list)

    def to_xml(self) -> etree.Element:
        """Convert to XML element."""
        prop = etree.Element(f"{{{NAMESPACE}}}prop")
        for elem in self.raw:
            prop.append(elem)
        return prop

    @staticmethod
    def from_xml(element: etree.Element) -> Prop:
        """Parse from XML element."""
        return Prop(raw=list(element))

    def get(self, tag: str) -> etree.Element | None:
        """Get a property by tag name."""
        for elem in self.raw:
            if elem.tag == tag:
                return elem
        return None


@dataclass
class Response:
    """WebDAV response element."""

    hrefs: list[Href] = field(default_factory=list)
    propstats: list[PropStat] = field(default_factory=list)
    response_description: str = ""
    status: Status | None = None
    error: Error | None = None
    location: Location | None = None

    def to_xml(self) -> etree.Element:
        """Convert to XML element."""
        resp = etree.Element(f"{{{NAMESPACE}}}response")

        for href in self.hrefs:
            href_el = etree.SubElement(resp, f"{{{NAMESPACE}}}href")
            href_el.text = str(href)

        for propstat in self.propstats:
            resp.append(propstat.to_xml())

        if self.response_description:
            desc = etree.SubElement(resp, f"{{{NAMESPACE}}}responsedescription")
            desc.text = self.response_description

        if self.status:
            status_el = etree.SubElement(resp, f"{{{NAMESPACE}}}status")
            status_el.text = self.status.to_string()

        return resp

    @staticmethod
    def from_xml(element: etree.Element) -> Response:
        """Parse from XML element."""
        hrefs = []
        for href_el in element.findall(f"{{{NAMESPACE}}}href"):
            if href_el.text:
                hrefs.append(Href.from_string(href_el.text))

        propstats = []
        for ps_el in element.findall(f"{{{NAMESPACE}}}propstat"):
            propstats.append(PropStat.from_xml(ps_el))

        desc_el = element.find(f"{{{NAMESPACE}}}responsedescription")
        desc = desc_el.text if desc_el is not None else ""

        status_el = element.find(f"{{{NAMESPACE}}}status")
        status = None
        if status_el is not None and status_el.text:
            status = Status.from_string(status_el.text)

        return Response(
            hrefs=hrefs,
            propstats=propstats,
            response_description=desc,
            status=status,
        )

    def err(self) -> Exception | None:
        """Get error from response if any."""
        if self.status is None or self.status.code // 100 == 2:
            return None

        err: Exception | None = None
        if self.error:
            err = Exception(str(self.error))
        if self.response_description:
            if err:
                err = Exception(f"{self.response_description} ({err})")
            else:
                err = Exception(self.response_description)

        http_err = HTTPError(self.status.code, err)

        if not self.hrefs:
            return http_err

        # Create HrefError for each href
        from .internal import HrefError

        href_errors = []
        for href in self.hrefs:
            href_errors.append(HrefError(href.url, http_err))

        if len(href_errors) == 1:
            return href_errors[0]
        return ExceptionGroup("multiple href errors", href_errors)

    def path(self) -> tuple[str, Exception | None]:
        """Get path from response."""
        err = self.err()
        path = ""
        if len(self.hrefs) == 1:
            path = self.hrefs[0].url.path
        elif err is None:
            err = ValueError(
                f"webdav: malformed response: expected exactly one href element, got {len(self.hrefs)}"
            )
        return path, err


def new_ok_response(path: str) -> Response:
    """Create a new OK response."""
    href = Href(url=urlparse(path))
    return Response(hrefs=[href], status=Status(code=200))


def new_error_response(path: str, err: Exception) -> Response:
    """Create a new error response."""
    code = 500
    if isinstance(err, HTTPError):
        code = err.code

    error_elt = None
    if isinstance(err, Error):
        error_elt = err

    href = Href(url=urlparse(path))
    return Response(
        hrefs=[href],
        status=Status(code=code),
        response_description=str(err),
        error=error_elt,
    )


@dataclass
class PropFind:
    """WebDAV PROPFIND request."""

    prop: Prop | None = None
    allprop: bool = False
    include: list[str] = field(default_factory=list)
    propname: bool = False

    @staticmethod
    def from_xml(element: etree.Element) -> PropFind:
        """Parse from XML element."""
        prop_el = element.find(f"{{{NAMESPACE}}}prop")
        prop = Prop.from_xml(prop_el) if prop_el is not None else None

        allprop = element.find(f"{{{NAMESPACE}}}allprop") is not None
        propname = element.find(f"{{{NAMESPACE}}}propname") is not None

        include: list[str] = []
        include_el = element.find(f"{{{NAMESPACE}}}include")
        if include_el is not None:
            for child in include_el:
                include.append(child.tag)

        return PropFind(prop=prop, allprop=allprop, include=include, propname=propname)

    def to_xml(self) -> etree.Element:
        """Convert to XML element."""
        pf = etree.Element(f"{{{NAMESPACE}}}propfind")

        if self.prop:
            pf.append(self.prop.to_xml())
        elif self.allprop:
            etree.SubElement(pf, f"{{{NAMESPACE}}}allprop")
            if self.include:
                inc = etree.SubElement(pf, f"{{{NAMESPACE}}}include")
                for tag in self.include:
                    etree.SubElement(inc, tag)
        elif self.propname:
            etree.SubElement(pf, f"{{{NAMESPACE}}}propname")

        return pf


@dataclass
class ResourceType:
    """WebDAV resourcetype property."""

    types: list[str] = field(default_factory=list)

    def is_type(self, tag: str) -> bool:
        """Check if resource has a specific type."""
        return tag in self.types

    def to_xml(self) -> etree.Element:
        """Convert to XML element."""
        rt = etree.Element(f"{{{NAMESPACE}}}resourcetype")
        for t in self.types:
            etree.SubElement(rt, t)
        return rt

    @staticmethod
    def from_xml(element: etree.Element) -> ResourceType:
        """Parse from XML element."""
        types = [child.tag for child in element]
        return ResourceType(types=types)


@dataclass
class PropertyUpdate:
    """WebDAV PROPPATCH request."""

    remove: list[Prop] = field(default_factory=list)
    set_props: list[Prop] = field(default_factory=list)

    @staticmethod
    def from_xml(element: etree.Element) -> PropertyUpdate:
        """Parse from XML element."""
        remove_props: list[Prop] = []
        for rem_el in element.findall(f"{{{NAMESPACE}}}remove"):
            prop_el = rem_el.find(f"{{{NAMESPACE}}}prop")
            if prop_el is not None:
                remove_props.append(Prop.from_xml(prop_el))

        set_props: list[Prop] = []
        for set_el in element.findall(f"{{{NAMESPACE}}}set"):
            prop_el = set_el.find(f"{{{NAMESPACE}}}prop")
            if prop_el is not None:
                set_props.append(Prop.from_xml(prop_el))

        return PropertyUpdate(remove=remove_props, set_props=set_props)


@dataclass
class SyncCollectionQuery:
    """WebDAV sync-collection query."""

    sync_token: str
    sync_level: str
    limit: int | None = None
    prop: Prop | None = None

    @staticmethod
    def from_xml(element: etree.Element) -> SyncCollectionQuery:
        """Parse from XML element."""
        token_el = element.find(f"{{{NAMESPACE}}}sync-token")
        sync_token = token_el.text if token_el is not None and token_el.text else ""

        level_el = element.find(f"{{{NAMESPACE}}}sync-level")
        sync_level = level_el.text if level_el is not None and level_el.text else "1"

        limit_el = element.find(f"{{{NAMESPACE}}}limit/{{{NAMESPACE}}}nresults")
        limit = int(limit_el.text) if limit_el is not None and limit_el.text else None

        prop_el = element.find(f"{{{NAMESPACE}}}prop")
        prop = Prop.from_xml(prop_el) if prop_el is not None else None

        return SyncCollectionQuery(
            sync_token=sync_token, sync_level=sync_level, limit=limit, prop=prop
        )


@dataclass
class DisplayName:
    """WebDAV displayname property."""

    name: str

    def to_xml(self) -> etree.Element:
        """Convert to XML element."""
        elem = etree.Element(f"{{{NAMESPACE}}}displayname")
        elem.text = self.name
        return elem


@dataclass
class GetContentLength:
    """WebDAV getcontentlength property."""

    length: int

    def to_xml(self) -> etree.Element:
        """Convert to XML element."""
        elem = etree.Element(f"{{{NAMESPACE}}}getcontentlength")
        elem.text = str(self.length)
        return elem


@dataclass
class GetContentType:
    """WebDAV getcontenttype property."""

    content_type: str

    def to_xml(self) -> etree.Element:
        """Convert to XML element."""
        elem = etree.Element(f"{{{NAMESPACE}}}getcontenttype")
        elem.text = self.content_type
        return elem


@dataclass
class GetLastModified:
    """WebDAV getlastmodified property."""

    last_modified: datetime

    def to_xml(self) -> etree.Element:
        """Convert to XML element."""
        elem = etree.Element(f"{{{NAMESPACE}}}getlastmodified")
        # Use RFC 1123 format (HTTP date format)
        elem.text = self.last_modified.strftime("%a, %d %b %Y %H:%M:%S GMT")
        return elem


@dataclass
class GetETag:
    """WebDAV getetag property."""

    etag: str

    def to_xml(self) -> etree.Element:
        """Convert to XML element."""
        elem = etree.Element(f"{{{NAMESPACE}}}getetag")
        # ETags should be quoted
        elem.text = f'"{self.etag}"' if not self.etag.startswith('"') else self.etag
        return elem


@dataclass
class CurrentUserPrincipal:
    """WebDAV current-user-principal property."""

    href: Href | None = None
    unauthenticated: bool = False

    def to_xml(self) -> etree.Element:
        """Convert to XML element."""
        elem = etree.Element(f"{{{NAMESPACE}}}current-user-principal")
        if self.unauthenticated:
            etree.SubElement(elem, f"{{{NAMESPACE}}}unauthenticated")
        elif self.href:
            href_el = etree.SubElement(elem, f"{{{NAMESPACE}}}href")
            href_el.text = str(self.href)
        return elem
