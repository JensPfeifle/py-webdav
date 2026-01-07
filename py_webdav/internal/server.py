"""Internal server utilities for WebDAV."""

from __future__ import annotations

from typing import Protocol

from lxml import etree
from starlette.requests import Request
from starlette.responses import Response as StarletteResponse

from .elements import (
    NAMESPACE,
    MultiStatus,
    PropertyUpdate,
    PropFind,
    Response,
)
from .internal import Depth, HTTPError, parse_depth, parse_overwrite


def serve_error(err: Exception) -> StarletteResponse:
    """Serve an error response."""
    code = 500
    if isinstance(err, HTTPError):
        code = err.code

    from .elements import Error

    if isinstance(err, Error):
        xml_str = etree.tostring(
            etree.Element(f"{{{NAMESPACE}}}error"),
            encoding="unicode",
            xml_declaration=True,
        )
        return StarletteResponse(
            content=xml_str,
            status_code=code,
            media_type="application/xml; charset=utf-8",
        )

    return StarletteResponse(content=str(err), status_code=code)


async def is_content_xml(request: Request) -> bool:
    """Check if request content type is XML."""
    content_type = request.headers.get("content-type", "")
    return "application/xml" in content_type or "text/xml" in content_type


async def decode_xml_request(request: Request, element_type: type) -> etree.Element:
    """Decode XML request body."""
    if not await is_content_xml(request):
        raise HTTPError(400, Exception("webdav: expected application/xml request"))

    try:
        body = await request.body()
        return etree.fromstring(body)
    except Exception as e:
        raise HTTPError(400, e) from e


async def is_request_body_empty(request: Request) -> bool:
    """Check if request body is empty."""
    body = await request.body()
    return len(body) == 0


def serve_xml(content: etree.Element) -> StarletteResponse:
    """Serve an XML response."""
    xml_str = etree.tostring(content, encoding="unicode", xml_declaration=True, pretty_print=True)
    return StarletteResponse(
        content=xml_str,
        media_type="application/xml; charset=utf-8",
    )


def serve_multistatus(ms: MultiStatus) -> StarletteResponse:
    """Serve a multistatus response."""
    xml_elem = ms.to_xml()
    xml_str = etree.tostring(xml_elem, encoding="unicode", xml_declaration=True, pretty_print=True)
    return StarletteResponse(
        content=xml_str,
        status_code=207,  # Multi-Status
        media_type="application/xml; charset=utf-8",
    )


class Backend(Protocol):
    """WebDAV backend interface."""

    async def options(self, request: Request) -> tuple[list[str], list[str]]:
        """Handle OPTIONS request.

        Returns:
            Tuple of (capabilities, allowed_methods)
        """
        ...

    async def head_get(self, request: Request) -> StarletteResponse:
        """Handle HEAD/GET request."""
        ...

    async def propfind(self, request: Request, pf: PropFind, depth: Depth) -> MultiStatus:
        """Handle PROPFIND request."""
        ...

    async def proppatch(self, request: Request, pu: PropertyUpdate) -> Response:
        """Handle PROPPATCH request."""
        ...

    async def put(self, request: Request) -> StarletteResponse:
        """Handle PUT request."""
        ...

    async def delete(self, request: Request) -> None:
        """Handle DELETE request."""
        ...

    async def mkcol(self, request: Request) -> None:
        """Handle MKCOL request."""
        ...

    async def copy(self, request: Request, dest: str, recursive: bool, overwrite: bool) -> bool:
        """Handle COPY request.

        Returns:
            True if resource was created, False if it was overwritten
        """
        ...

    async def move(self, request: Request, dest: str, overwrite: bool) -> bool:
        """Handle MOVE request.

        Returns:
            True if resource was created, False if it was overwritten
        """
        ...


class Handler:
    """WebDAV HTTP handler."""

    def __init__(self, backend: Backend):
        self.backend = backend

    async def handle(self, request: Request) -> StarletteResponse:
        """Handle HTTP request."""
        try:
            if self.backend is None:
                raise Exception("webdav: no backend available")

            method = request.method
            if method == "OPTIONS":
                return await self._handle_options(request)
            elif method in ("GET", "HEAD"):
                return await self.backend.head_get(request)
            elif method == "PUT":
                return await self.backend.put(request)
            elif method == "DELETE":
                await self.backend.delete(request)
                return StarletteResponse(status_code=204)  # No Content
            elif method == "PROPFIND":
                return await self._handle_propfind(request)
            elif method == "PROPPATCH":
                return await self._handle_proppatch(request)
            elif method == "MKCOL":
                await self.backend.mkcol(request)
                return StarletteResponse(status_code=201)  # Created
            elif method in ("COPY", "MOVE"):
                return await self._handle_copy_move(request)
            else:
                raise HTTPError(405, Exception("webdav: unsupported method"))
        except Exception as e:
            return serve_error(e)

    async def _handle_options(self, request: Request) -> StarletteResponse:
        """Handle OPTIONS request."""
        caps, allow = await self.backend.options(request)
        caps = ["1", "3"] + caps

        headers = {
            "DAV": ", ".join(caps),
            "Allow": ", ".join(allow),
        }
        return StarletteResponse(status_code=204, headers=headers)

    async def _handle_propfind(self, request: Request) -> StarletteResponse:
        """Handle PROPFIND request."""
        # Parse request body
        if await is_request_body_empty(request):
            # Empty body means allprop
            propfind = PropFind(allprop=True)
        elif await is_content_xml(request):
            xml_elem = await decode_xml_request(request, PropFind)
            propfind = PropFind.from_xml(xml_elem)
        else:
            raise HTTPError(400, Exception("webdav: unsupported request body"))

        # Parse depth header
        depth_str = request.headers.get("depth", "")
        if depth_str:
            depth = parse_depth(depth_str)
        else:
            depth = Depth.INFINITY

        # Execute propfind
        ms = await self.backend.propfind(request, propfind, depth)
        return serve_multistatus(ms)

    async def _handle_proppatch(self, request: Request) -> StarletteResponse:
        """Handle PROPPATCH request."""
        xml_elem = await decode_xml_request(request, PropertyUpdate)
        update = PropertyUpdate.from_xml(xml_elem)

        resp = await self.backend.proppatch(request, update)

        ms = MultiStatus(responses=[resp])
        return serve_multistatus(ms)

    def _parse_destination(self, request: Request) -> str:
        """Parse Destination header."""
        dest = request.headers.get("destination", "")
        if not dest:
            raise HTTPError(400, Exception("webdav: missing Destination header in request"))
        return dest

    async def _handle_copy_move(self, request: Request) -> StarletteResponse:
        """Handle COPY/MOVE request."""
        dest = self._parse_destination(request)

        # Parse overwrite header
        overwrite = True
        overwrite_str = request.headers.get("overwrite", "")
        if overwrite_str:
            overwrite = parse_overwrite(overwrite_str)

        # Parse depth header
        depth_str = request.headers.get("depth", "")
        if depth_str:
            depth = parse_depth(depth_str)
        else:
            depth = Depth.INFINITY

        created = False
        if request.method == "COPY":
            if depth == Depth.ZERO:
                recursive = False
            elif depth == Depth.ONE:
                raise HTTPError(
                    400, Exception('webdav: "Depth: 1" is not supported in COPY request')
                )
            else:  # INFINITY
                recursive = True

            created = await self.backend.copy(request, dest, recursive, overwrite)
        else:  # MOVE
            if depth != Depth.INFINITY:
                raise HTTPError(
                    400,
                    Exception('webdav: only "Depth: infinity" is accepted in MOVE request'),
                )
            created = await self.backend.move(request, dest, overwrite)

        if created:
            return StarletteResponse(status_code=201)  # Created
        else:
            return StarletteResponse(status_code=204)  # No Content
