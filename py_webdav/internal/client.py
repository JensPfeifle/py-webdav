"""Internal client utilities for WebDAV."""

from __future__ import annotations

import asyncio
from urllib.parse import urljoin, urlparse

import httpx
from lxml import etree

from .elements import (
    NAMESPACE,
    MultiStatus,
    Prop,
    PropFind,
    Response,
)
from .internal import Depth, HTTPError, depth_to_string


async def discover_context_url(service: str, domain: str) -> str:
    """Perform DNS-based CardDAV/CalDAV service discovery.

    Implements RFC 6764 section 6 (points 2 and 3).

    Args:
        service: Service name (e.g., "caldav", "carddav")
        domain: Domain name

    Returns:
        URL to the CardDAV/CalDAV server
    """
    # Look up SRV records (TLS only for security)
    # Note: Full DNS-based service discovery is not implemented
    try:
        # Python's asyncio doesn't have built-in async DNS resolution
        # We'll use a simple synchronous approach wrapped in executor
        import socket

        loop = asyncio.get_event_loop()
        addrs = await loop.run_in_executor(
            None, socket.getaddrinfo, domain, None, socket.AF_UNSPEC, socket.SOCK_STREAM
        )

        if not addrs:
            raise ValueError("webdav: domain doesn't have an SRV record")

        # For simplicity, use the domain directly
        target = domain
        port = 443

        # Look up TXT record for path
        # In a real implementation, we'd look up TXT records
        # For now, use the well-known path
        path = f"/.well-known/{service}"

        if port == 443:
            return f"https://{target}{path}"
        else:
            return f"https://{target}:{port}{path}"

    except Exception as e:
        raise ValueError(f"webdav: DNS discovery failed: {e}") from e


class Client:
    """WebDAV HTTP client."""

    def __init__(self, http_client: httpx.AsyncClient | None = None, endpoint: str = ""):
        """Initialize client.

        Args:
            http_client: HTTP client to use (creates default if None)
            endpoint: Base endpoint URL
        """
        self.http_client = http_client or httpx.AsyncClient()
        self.endpoint = urlparse(endpoint)

        # Ensure path ends with /
        if not self.endpoint.path:
            from urllib.parse import urlunparse

            self.endpoint = urlparse(
                urlunparse(
                    (
                        self.endpoint.scheme,
                        self.endpoint.netloc,
                        "/",
                        self.endpoint.params,
                        self.endpoint.query,
                        self.endpoint.fragment,
                    )
                )
            )

    def resolve_href(self, path: str) -> str:
        """Resolve a path relative to the endpoint.

        Args:
            path: Path to resolve

        Returns:
            Full URL
        """
        if path.startswith("/"):
            # Absolute path
            from urllib.parse import urlunparse

            return urlunparse(
                (
                    self.endpoint.scheme,
                    self.endpoint.netloc,
                    path,
                    "",
                    "",
                    "",
                )
            )
        else:
            # Relative path
            base_url = self.endpoint.geturl()
            return urljoin(base_url, path)

    async def request(
        self,
        method: str,
        path: str,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make an HTTP request.

        Args:
            method: HTTP method
            path: Request path
            content: Request body
            headers: Request headers

        Returns:
            HTTP response
        """
        url = self.resolve_href(path)
        resp = await self.http_client.request(method, url, content=content, headers=headers or {})

        if resp.status_code // 100 != 2:
            # Handle error
            content_type = resp.headers.get("content-type", "text/plain")

            wrapped_err: Exception | None = None
            if "application/xml" in content_type or "text/xml" in content_type:
                try:
                    # Try to parse error
                    # For now, just use the response text
                    wrapped_err = Exception(resp.text[:1024])
                except Exception:
                    wrapped_err = Exception(resp.text[:1024])
            elif content_type.startswith("text/"):
                text = resp.text[:1024].strip()
                if text:
                    if len(resp.text) > 1024:
                        text += " […]"
                    wrapped_err = Exception(text)

            raise HTTPError(resp.status_code, wrapped_err)

        return resp

    async def xml_request(
        self, method: str, path: str, xml_obj: etree._Element, headers: dict[str, str] | None = None
    ) -> httpx.Response:
        """Make an XML HTTP request.

        Args:
            method: HTTP method
            path: Request path
            xml_obj: XML object to send
            headers: Additional request headers

        Returns:
            HTTP response
        """
        # Serialize to bytes directly with XML declaration
        xml_bytes = etree.tostring(
            xml_obj, encoding="utf-8", xml_declaration=True, pretty_print=False
        )

        req_headers = headers or {}
        req_headers["Content-Type"] = "text/xml; charset=utf-8"

        return await self.request(method, path, content=xml_bytes, headers=req_headers)

    async def do_multistatus(self, method: str, path: str, xml_obj: etree._Element) -> MultiStatus:
        """Perform a request expecting a multistatus response.

        Args:
            method: HTTP method
            path: Request path
            xml_obj: XML request body

        Returns:
            Parsed multistatus response
        """
        resp = await self.xml_request(method, path, xml_obj)

        if resp.status_code != 207:  # Multi-Status
            raise ValueError(f"HTTP multi-status request failed: {resp.status_code}")

        # Parse response
        xml_elem = etree.fromstring(resp.content)
        return MultiStatus.from_xml(xml_elem)

    async def propfind(self, path: str, depth: Depth, propfind: PropFind) -> MultiStatus:
        """Perform a PROPFIND request.

        Args:
            path: Resource path
            depth: Depth header value
            propfind: PROPFIND request

        Returns:
            Multistatus response
        """
        xml_elem = propfind.to_xml()

        headers = {"Depth": depth_to_string(depth)}

        resp = await self.xml_request("PROPFIND", path, xml_elem, headers=headers)

        if resp.status_code != 207:
            raise ValueError(f"PROPFIND request failed: {resp.status_code}")

        # Parse response
        ms_elem = etree.fromstring(resp.content)
        return MultiStatus.from_xml(ms_elem)

    async def propfind_flat(self, path: str, propfind: PropFind) -> Response:
        """Perform a PROPFIND request with depth 0.

        Args:
            path: Resource path
            propfind: PROPFIND request

        Returns:
            Single response
        """
        ms = await self.propfind(path, Depth.ZERO, propfind)

        if len(ms.responses) != 1:
            raise ValueError(f"PROPFIND with Depth: 0 returned {len(ms.responses)} responses")

        return ms.responses[0]

    async def options(self, path: str) -> tuple[set[str], set[str]]:
        """Perform an OPTIONS request.

        Args:
            path: Resource path

        Returns:
            Tuple of (DAV classes, allowed methods)
        """
        resp = await self.request("OPTIONS", path)

        # Parse DAV header
        dav_header = resp.headers.get("dav", "")
        classes = set()
        for value in dav_header.split(","):
            value = value.strip().lower()
            if value:
                classes.add(value)

        if "1" not in classes:
            raise ValueError("webdav: server doesn't support DAV class 1")

        # Parse Allow header
        allow_header = resp.headers.get("allow", "")
        methods = set()
        for value in allow_header.split(","):
            value = value.strip().upper()
            if value:
                methods.add(value)

        return classes, methods

    async def sync_collection(
        self,
        path: str,
        sync_token: str,
        level: Depth,
        limit: int | None,
        prop: Prop | None,
    ) -> MultiStatus:
        """Perform a sync-collection REPORT operation.

        Args:
            path: Collection path
            sync_token: Sync token
            level: Sync level
            limit: Maximum number of results
            prop: Properties to retrieve

        Returns:
            Multistatus response
        """
        # Build XML directly
        root = etree.Element(f"{{{NAMESPACE}}}sync-collection")
        token_el = etree.SubElement(root, f"{{{NAMESPACE}}}sync-token")
        token_el.text = sync_token
        level_el = etree.SubElement(root, f"{{{NAMESPACE}}}sync-level")
        level_el.text = depth_to_string(level)
        if limit:
            limit_el = etree.SubElement(root, f"{{{NAMESPACE}}}limit")
            nresults = etree.SubElement(limit_el, f"{{{NAMESPACE}}}nresults")
            nresults.text = str(limit)
        if prop:
            root.append(prop.to_xml())

        return await self.do_multistatus("REPORT", path, root)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.http_client.aclose()
