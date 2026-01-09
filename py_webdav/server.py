"""WebDAV server implementation."""

from __future__ import annotations

from io import BytesIO
from typing import BinaryIO, Protocol

from lxml import etree
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response as StarletteResponse
from starlette.responses import StreamingResponse
from starlette.routing import Route

from .internal import (
    Depth,
    GetContentLength,
    GetContentType,
    GetETag,
    GetLastModified,
    HTTPError,
    MultiStatus,
    PropertyUpdate,
    PropFind,
    ResourceType,
    Response,
    is_not_found,
)
from .internal import Handler as InternalHandler
from .internal import elements as elem
from .webdav import (
    ConditionalMatch,
    CopyOptions,
    CreateOptions,
    FileInfo,
    MoveOptions,
    RemoveAllOptions,
)


class FileSystem(Protocol):
    """WebDAV server backend interface."""

    async def open(self, name: str) -> BinaryIO:
        """Open a file for reading."""
        ...

    async def stat(self, name: str) -> FileInfo:
        """Get file information."""
        ...

    async def read_dir(self, name: str, recursive: bool = False) -> list[FileInfo]:
        """List directory contents."""
        ...

    async def create(
        self, name: str, body: BinaryIO, opts: CreateOptions | None = None
    ) -> tuple[FileInfo, bool]:
        """Create or update a file.

        Returns:
            Tuple of (file_info, created) where created is True if file was created
        """
        ...

    async def remove_all(self, name: str, opts: RemoveAllOptions | None = None) -> None:
        """Remove a file or directory recursively."""
        ...

    async def mkdir(self, name: str) -> None:
        """Create a directory."""
        ...

    async def copy(self, name: str, dest: str, options: CopyOptions | None = None) -> bool:
        """Copy a file or directory.

        Returns:
            True if destination was created, False if it was overwritten
        """
        ...

    async def move(self, name: str, dest: str, options: MoveOptions | None = None) -> bool:
        """Move a file or directory.

        Returns:
            True if destination was created, False if it was overwritten
        """
        ...


class WebDAVBackend:
    """Adapter between FileSystem and internal Backend."""

    def __init__(self, filesystem: FileSystem):
        self.filesystem = filesystem

    async def options(self, request: Request) -> tuple[list[str], list[str]]:
        """Handle OPTIONS request."""
        try:
            fi = await self.filesystem.stat(request.url.path)
            allow = [
                "OPTIONS",
                "DELETE",
                "PROPFIND",
                "COPY",
                "MOVE",
            ]
            if not fi.is_dir:
                allow.extend(["HEAD", "GET", "PUT"])
            return [], allow
        except Exception as err:
            if is_not_found(err):
                return [], ["OPTIONS", "PUT", "MKCOL"]
            raise

    async def head_get(self, request: Request) -> StarletteResponse:
        """Handle HEAD/GET request."""
        fi = await self.filesystem.stat(request.url.path)
        if fi.is_dir:
            raise HTTPError(405)  # Method Not Allowed

        f = await self.filesystem.open(request.url.path)

        headers = {
            "Content-Length": str(fi.size),
        }
        if fi.mime_type:
            headers["Content-Type"] = fi.mime_type
        if fi.mod_time:
            headers["Last-Modified"] = fi.mod_time.strftime("%a, %d %b %Y %H:%M:%S GMT")
        if fi.etag:
            headers["ETag"] = f'"{fi.etag}"'

        if request.method == "HEAD":
            return StarletteResponse(headers=headers)

        return StreamingResponse(f, headers=headers)

    async def propfind(self, request: Request, propfind: PropFind, depth: Depth) -> MultiStatus:
        """Handle PROPFIND request."""
        fi = await self.filesystem.stat(request.url.path)

        responses: list[Response] = []
        if depth != Depth.ZERO and fi.is_dir:
            children = await self.filesystem.read_dir(
                request.url.path, recursive=(depth == Depth.INFINITY)
            )
            for child in children:
                resp = await self._propfind_file(propfind, child)
                responses.append(resp)
        else:
            resp = await self._propfind_file(propfind, fi)
            responses.append(resp)

        return MultiStatus(responses=responses)

    async def _propfind_file(self, propfind: PropFind, fi: FileInfo) -> Response:
        """Create PROPFIND response for a file."""
        from urllib.parse import urlparse

        from .internal.elements import Href

        # Build properties
        props: dict[str, etree.Element] = {}

        # Resource type
        if fi.is_dir:
            rt = ResourceType(types=[elem.COLLECTION])
        else:
            rt = ResourceType(types=[])
        props[elem.RESOURCE_TYPE] = rt.to_xml()

        if not fi.is_dir:
            # Content length
            props[elem.GET_CONTENT_LENGTH] = GetContentLength(length=fi.size).to_xml()

            # Last modified
            if fi.mod_time:
                props[elem.GET_LAST_MODIFIED] = GetLastModified(last_modified=fi.mod_time).to_xml()

            # Content type
            if fi.mime_type:
                props[elem.GET_CONTENT_TYPE] = GetContentType(content_type=fi.mime_type).to_xml()

            # ETag
            if fi.etag:
                props[elem.GET_ETAG] = GetETag(etag=fi.etag).to_xml()

        # Build response based on propfind type
        from .internal.elements import Prop, PropStat, Status

        href = Href(url=urlparse(fi.path))
        propstats: list[PropStat] = []

        if propfind.propname:
            # Return just property names
            prop_elements = [etree.Element(tag) for tag in props.keys()]
            propstats.append(
                PropStat(
                    prop=Prop(raw=prop_elements),
                    status=Status(code=200),
                )
            )
        elif propfind.allprop:
            # Return all properties
            prop_elements = list(props.values())
            propstats.append(
                PropStat(
                    prop=Prop(raw=prop_elements),
                    status=Status(code=200),
                )
            )
        elif propfind.prop:
            # Return requested properties
            ok_props: list[etree.Element] = []
            notfound_props: list[etree.Element] = []

            for req_elem in propfind.prop.raw:
                tag = req_elem.tag
                if tag in props:
                    ok_props.append(props[tag])
                else:
                    notfound_props.append(etree.Element(tag))

            if ok_props:
                propstats.append(
                    PropStat(
                        prop=Prop(raw=ok_props),
                        status=Status(code=200),
                    )
                )
            if notfound_props:
                propstats.append(
                    PropStat(
                        prop=Prop(raw=notfound_props),
                        status=Status(code=404),
                    )
                )

        return Response(hrefs=[href], propstats=propstats)

    async def proppatch(self, request: Request, update: PropertyUpdate) -> Response:
        """Handle PROPPATCH request."""
        fi = await self.filesystem.stat(request.url.path)

        from urllib.parse import urlparse

        from .internal.elements import Href, Prop, PropStat, Status

        href = Href(url=urlparse(fi.path))
        propstats: list[PropStat] = []

        # All property updates are forbidden (not supported)
        forbidden_props: list[etree.Element] = []

        for prop in update.set_props:
            forbidden_props.extend(prop.raw)

        for prop in update.remove:
            forbidden_props.extend(prop.raw)

        if forbidden_props:
            propstats.append(
                PropStat(
                    prop=Prop(raw=forbidden_props),
                    status=Status(code=403),  # Forbidden
                )
            )

        if not propstats:
            raise HTTPError(400, Exception("webdav: request missing properties to update"))

        return Response(hrefs=[href], propstats=propstats)

    async def put(self, request: Request) -> StarletteResponse:
        """Handle PUT request."""
        if_none_match = ConditionalMatch(request.headers.get("if-none-match", ""))
        if_match = ConditionalMatch(request.headers.get("if-match", ""))

        opts = CreateOptions(if_match=if_match, if_none_match=if_none_match)

        # Read body into BytesIO
        body_bytes = await request.body()
        body = BytesIO(body_bytes)

        fi, created = await self.filesystem.create(request.url.path, body, opts)

        headers: dict[str, str] = {}
        if fi.mime_type:
            headers["Content-Type"] = fi.mime_type
        if fi.mod_time:
            headers["Last-Modified"] = fi.mod_time.strftime("%a, %d %b %Y %H:%M:%S GMT")
        if fi.etag:
            headers["ETag"] = f'"{fi.etag}"'

        status_code = 201 if created else 204
        return StarletteResponse(status_code=status_code, headers=headers)

    async def delete(self, request: Request) -> None:
        """Handle DELETE request."""
        if_none_match = ConditionalMatch(request.headers.get("if-none-match", ""))
        if_match = ConditionalMatch(request.headers.get("if-match", ""))

        opts = RemoveAllOptions(if_match=if_match, if_none_match=if_none_match)
        await self.filesystem.remove_all(request.url.path, opts)

    async def mkcol(self, request: Request) -> None:
        """Handle MKCOL request."""
        if request.headers.get("content-type"):
            raise HTTPError(415, Exception("webdav: request body not supported in MKCOL request"))

        try:
            await self.filesystem.mkdir(request.url.path)
        except Exception as err:
            if is_not_found(err):
                raise HTTPError(409, err) from err  # Conflict
            raise

    async def copy(self, request: Request, dest: str, recursive: bool, overwrite: bool) -> bool:
        """Handle COPY request."""
        from urllib.parse import urlparse

        dest_path = urlparse(dest).path

        options = CopyOptions(no_recursive=not recursive, no_overwrite=not overwrite)

        try:
            created = await self.filesystem.copy(request.url.path, dest_path, options)
            return created
        except FileExistsError as err:
            raise HTTPError(412, err) from err  # Precondition Failed

    async def move(self, request: Request, dest: str, overwrite: bool) -> bool:
        """Handle MOVE request."""
        from urllib.parse import urlparse

        dest_path = urlparse(dest).path

        options = MoveOptions(no_overwrite=not overwrite)

        try:
            created = await self.filesystem.move(request.url.path, dest_path, options)
            return created
        except FileExistsError as err:
            raise HTTPError(412, err) from err  # Precondition Failed


class Handler:
    """WebDAV HTTP handler."""

    def __init__(
        self,
        filesystem: FileSystem,
        enable_principal_discovery: bool = True,
        principal_path: str = "/principals/current/",
        calendar_home_path: str | None = None,
        addressbook_home_path: str | None = None,
        caldav_backend=None,
        carddav_backend=None,
    ):
        """Initialize handler.

        Args:
            filesystem: FileSystem backend
            enable_principal_discovery: Enable CalDAV/CardDAV principal discovery
            principal_path: Path to principal URL (default: /principals/current/)
            calendar_home_path: Path to calendar home set (default: /calendars/)
            addressbook_home_path: Path to addressbook home set (default: /contacts/)
            caldav_backend: Optional CalDAV backend instance
            carddav_backend: Optional CardDAV backend instance
        """
        self.filesystem = filesystem
        self.backend = WebDAVBackend(filesystem)
        self.internal_handler = InternalHandler(self.backend)
        self.enable_principal_discovery = enable_principal_discovery
        self.principal_path = principal_path

        # Set default home paths if not provided
        if calendar_home_path is None:
            calendar_home_path = "/calendars/"
        if addressbook_home_path is None:
            addressbook_home_path = "/contacts/"

        self.calendar_home_path = calendar_home_path
        self.addressbook_home_path = addressbook_home_path
        self.caldav_backend = caldav_backend
        self.carddav_backend = carddav_backend

    async def handle(self, request: Request) -> StarletteResponse:
        """Handle WebDAV HTTP request.

        Args:
            request: Starlette request

        Returns:
            Starlette response
        """
        if self.filesystem is None:
            return StarletteResponse(content="webdav: no filesystem available", status_code=500)

        # Handle principal discovery paths
        if self.enable_principal_discovery:
            # Check for well-known redirects
            if request.url.path == "/.well-known/caldav":
                from starlette.responses import RedirectResponse

                return RedirectResponse(url=self.principal_path, status_code=308)
            if request.url.path == "/.well-known/carddav":
                from starlette.responses import RedirectResponse

                return RedirectResponse(url=self.principal_path, status_code=308)

            # Check if this is a principal path request
            if request.url.path == self.principal_path or request.url.path.startswith(
                self.principal_path.rstrip("/") + "/"
            ):
                from .principal import PrincipalOptions, serve_principal

                options = PrincipalOptions(
                    current_user_principal_path=self.principal_path,
                    calendar_home_set_path=self.calendar_home_path,
                    addressbook_home_set_path=self.addressbook_home_path,
                )
                return await serve_principal(request, options)

            # Check if this is a CalDAV path request (home set or calendars within it)
            if (
                request.method == "PROPFIND"
                and (request.url.path == self.calendar_home_path or request.url.path.startswith(self.calendar_home_path))
            ):
                from .caldav.server import handle_caldav_propfind
                from .internal import parse_depth
                from .internal.server import decode_xml_request, is_request_body_empty

                try:
                    # Parse PROPFIND request
                    if await is_request_body_empty(request):
                        propfind = PropFind(allprop=True)
                    else:
                        xml_elem = await decode_xml_request(request, PropFind)
                        propfind = PropFind.from_xml(xml_elem)

                    # Parse depth header
                    depth_str = request.headers.get("depth", "0")
                    depth = parse_depth(depth_str)

                    return await handle_caldav_propfind(
                        request, propfind, depth, self.calendar_home_path, self.principal_path, self.caldav_backend
                    )
                except HTTPError as e:
                    return StarletteResponse(content=str(e), status_code=e.code)
                except Exception as e:
                    return StarletteResponse(content=f"Internal error: {e}", status_code=500)

            # Check if this is a CardDAV path request (home set or addressbooks within it)
            if (
                request.method == "PROPFIND"
                and (request.url.path == self.addressbook_home_path or request.url.path.startswith(self.addressbook_home_path))
            ):
                from .carddav.server import handle_carddav_propfind
                from .internal import parse_depth
                from .internal.server import decode_xml_request, is_request_body_empty

                try:
                    # Parse PROPFIND request
                    if await is_request_body_empty(request):
                        propfind = PropFind(allprop=True)
                    else:
                        xml_elem = await decode_xml_request(request, PropFind)
                        propfind = PropFind.from_xml(xml_elem)

                    # Parse depth header
                    depth_str = request.headers.get("depth", "0")
                    depth = parse_depth(depth_str)

                    return await handle_carddav_propfind(
                        request, propfind, depth, self.addressbook_home_path, self.principal_path, self.carddav_backend
                    )
                except HTTPError as e:
                    return StarletteResponse(content=str(e), status_code=e.code)
                except Exception as e:
                    return StarletteResponse(content=f"Internal error: {e}", status_code=500)

            # Handle REPORT requests for CalDAV paths
            if (
                request.method == "REPORT"
                and (request.url.path == self.calendar_home_path or request.url.path.startswith(self.calendar_home_path))
                and self.caldav_backend is not None
            ):
                from .caldav.server import handle_caldav_report

                try:
                    return await handle_caldav_report(
                        request, self.calendar_home_path, self.principal_path, self.caldav_backend
                    )
                except HTTPError as e:
                    return StarletteResponse(content=str(e), status_code=e.code)
                except Exception as e:
                    return StarletteResponse(content=f"Internal error: {e}", status_code=500)

            # Handle REPORT requests for CardDAV paths
            if (
                request.method == "REPORT"
                and (request.url.path == self.addressbook_home_path or request.url.path.startswith(self.addressbook_home_path))
                and self.carddav_backend is not None
            ):
                from .carddav.server import handle_carddav_report

                try:
                    return await handle_carddav_report(
                        request, self.addressbook_home_path, self.principal_path, self.carddav_backend
                    )
                except HTTPError as e:
                    return StarletteResponse(content=str(e), status_code=e.code)
                except Exception as e:
                    return StarletteResponse(content=f"Internal error: {e}", status_code=500)

        return await self.internal_handler.handle(request)


def create_app(filesystem: FileSystem) -> Starlette:
    """Create a Starlette app for WebDAV.

    Args:
        filesystem: FileSystem backend

    Returns:
        Starlette application
    """
    handler = Handler(filesystem)

    async def webdav_handler(request: Request) -> StarletteResponse:
        return await handler.handle(request)

    # Create routes for all HTTP methods and WebDAV methods
    routes = [
        Route(
            "/{path:path}",
            webdav_handler,
            methods=[
                "GET",
                "HEAD",
                "PUT",
                "DELETE",
                "OPTIONS",
                "PROPFIND",
                "PROPPATCH",
                "MKCOL",
                "COPY",
                "MOVE",
                "REPORT",
            ],
        ),
    ]

    return Starlette(routes=routes)
