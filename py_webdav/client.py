"""WebDAV client implementation."""

from __future__ import annotations

from io import BytesIO
from typing import BinaryIO

import httpx

from .internal import Client as InternalClient
from .internal import Depth, PropFind
from .internal import elements as elem
from .webdav import CopyOptions, FileInfo, MoveOptions


async def file_info_from_response(resp: elem.Response) -> FileInfo:
    """Convert internal Response to FileInfo.

    Args:
        resp: Internal response

    Returns:
        FileInfo object

    Raises:
        Exception: If response contains an error
    """
    path, err = resp.path()
    if err:
        raise err

    fi = FileInfo(path=path)

    # Get resource type
    res_type_elem = None
    for propstat in resp.propstats:
        res_type_elem = propstat.prop.get(elem.RESOURCE_TYPE)
        if res_type_elem is not None:
            break

    if res_type_elem is not None:
        res_type = elem.ResourceType.from_xml(res_type_elem)
        if res_type.is_type(elem.COLLECTION):
            fi.is_dir = True

    if not fi.is_dir:
        # Get content length
        for propstat in resp.propstats:
            len_elem = propstat.prop.get(elem.GET_CONTENT_LENGTH)
            if len_elem is not None and len_elem.text:
                fi.size = int(len_elem.text)
                break

        # Get content type
        for propstat in resp.propstats:
            type_elem = propstat.prop.get(elem.GET_CONTENT_TYPE)
            if type_elem is not None and type_elem.text:
                fi.mime_type = type_elem.text
                break

        # Get ETag
        for propstat in resp.propstats:
            etag_elem = propstat.prop.get(elem.GET_ETAG)
            if etag_elem is not None and etag_elem.text:
                # Remove quotes
                fi.etag = etag_elem.text.strip('"')
                break

    # Get last modified
    for propstat in resp.propstats:
        mod_elem = propstat.prop.get(elem.GET_LAST_MODIFIED)
        if mod_elem is not None and mod_elem.text:
            from datetime import datetime

            fi.mod_time = datetime.strptime(
                mod_elem.text, "%a, %d %b %Y %H:%M:%S %Z"
            )
            break

    return fi


# PROPFIND request for file info
FILE_INFO_PROPFIND = PropFind(
    prop=elem.Prop(
        raw=[
            elem.etree.Element(elem.RESOURCE_TYPE),
            elem.etree.Element(elem.GET_CONTENT_LENGTH),
            elem.etree.Element(elem.GET_LAST_MODIFIED),
            elem.etree.Element(elem.GET_CONTENT_TYPE),
            elem.etree.Element(elem.GET_ETAG),
        ]
    )
)


class Client:
    """WebDAV client for accessing remote WebDAV servers."""

    def __init__(
        self, http_client: httpx.AsyncClient | None = None, endpoint: str = ""
    ):
        """Initialize WebDAV client.

        Args:
            http_client: HTTP client to use
            endpoint: WebDAV server endpoint URL
        """
        self.internal_client = InternalClient(http_client, endpoint)

    async def find_current_user_principal(self) -> str:
        """Find the current user's principal path.

        Returns:
            Principal path

        Raises:
            Exception: If unauthenticated or error occurs
        """
        propfind = PropFind(
            prop=elem.Prop(raw=[elem.etree.Element(elem.CURRENT_USER_PRINCIPAL)])
        )

        resp = await self.internal_client.propfind_flat("", propfind)

        # Parse current user principal
        for propstat in resp.propstats:
            principal_elem = propstat.prop.get(elem.CURRENT_USER_PRINCIPAL)
            if principal_elem is not None:
                principal = elem.CurrentUserPrincipal.from_xml(principal_elem)
                if principal.unauthenticated:
                    raise Exception("webdav: unauthenticated")
                if principal.href:
                    return principal.href.url.path
                break

        raise Exception("webdav: could not find current user principal")

    async def stat(self, name: str) -> FileInfo:
        """Get file information.

        Args:
            name: File path

        Returns:
            FileInfo object
        """
        resp = await self.internal_client.propfind_flat(name, FILE_INFO_PROPFIND)
        return await file_info_from_response(resp)

    async def open(self, name: str) -> BinaryIO:
        """Open a file for reading.

        Args:
            name: File path

        Returns:
            Binary file object
        """
        resp = await self.internal_client.request("GET", name)
        # Return BytesIO with content
        return BytesIO(resp.content)

    async def read_dir(self, name: str, recursive: bool = False) -> list[FileInfo]:
        """List directory contents.

        Args:
            name: Directory path
            recursive: Whether to list recursively

        Returns:
            List of FileInfo objects
        """
        depth = Depth.INFINITY if recursive else Depth.ONE

        ms = await self.internal_client.propfind(name, depth, FILE_INFO_PROPFIND)

        files: list[FileInfo] = []
        errors: list[Exception] = []

        for resp in ms.responses:
            try:
                fi = await file_info_from_response(resp)
                files.append(fi)
            except Exception as e:
                errors.append(e)

        if errors:
            # For now, just raise the first error
            raise errors[0]

        return files

    async def create(self, name: str, content: bytes) -> None:
        """Create or update a file.

        Args:
            name: File path
            content: File content
        """
        await self.internal_client.request("PUT", name, content=content)

    async def remove_all(self, name: str) -> None:
        """Remove a file or directory recursively.

        Args:
            name: Path to remove
        """
        await self.internal_client.request("DELETE", name)

    async def mkdir(self, name: str) -> None:
        """Create a directory.

        Args:
            name: Directory path
        """
        await self.internal_client.request("MKCOL", name)

    async def copy(
        self, name: str, dest: str, options: CopyOptions | None = None
    ) -> None:
        """Copy a file or directory.

        Args:
            name: Source path
            dest: Destination path
            options: Copy options
        """
        if options is None:
            options = CopyOptions()

        from .internal import depth_to_string, format_overwrite

        depth = Depth.ZERO if options.no_recursive else Depth.INFINITY

        headers = {
            "Destination": self.internal_client.resolve_href(dest),
            "Overwrite": format_overwrite(not options.no_overwrite),
            "Depth": depth_to_string(depth),
        }

        await self.internal_client.request("COPY", name, headers=headers)

    async def move(
        self, name: str, dest: str, options: MoveOptions | None = None
    ) -> None:
        """Move a file or directory.

        Args:
            name: Source path
            dest: Destination path
            options: Move options
        """
        if options is None:
            options = MoveOptions()

        from .internal import format_overwrite

        headers = {
            "Destination": self.internal_client.resolve_href(dest),
            "Overwrite": format_overwrite(not options.no_overwrite),
        }

        await self.internal_client.request("MOVE", name, headers=headers)

    async def close(self) -> None:
        """Close the client."""
        await self.internal_client.close()
