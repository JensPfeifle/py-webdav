"""Debug logging utilities for WebDAV server."""

from __future__ import annotations

import json
import logging
from typing import Any

from lxml import etree

logger = logging.getLogger("py_webdav")
inform_logger = logging.getLogger("py_webdav.inform")


def format_xml(xml_bytes: bytes | str) -> str:
    """Format XML with proper indentation.

    Args:
        xml_bytes: XML content as bytes or string

    Returns:
        Pretty-formatted XML string
    """
    try:
        if isinstance(xml_bytes, str):
            xml_bytes = xml_bytes.encode("utf-8")

        # Parse and pretty-print XML
        parser = etree.XMLParser(remove_blank_text=True)
        root = etree.fromstring(xml_bytes, parser)
        return etree.tostring(root, pretty_print=True, encoding="unicode")
    except Exception:
        # If parsing fails, return as-is
        if isinstance(xml_bytes, bytes):
            return xml_bytes.decode("utf-8", errors="replace")
        return str(xml_bytes)


def is_xml_content(content_type: str | None) -> bool:
    """Check if content type is XML.

    Args:
        content_type: Content-Type header value

    Returns:
        True if content type indicates XML
    """
    if not content_type:
        return False

    xml_types = ["application/xml", "text/xml", "application/x-www-form-urlencoded"]
    return any(xml_type in content_type.lower() for xml_type in xml_types)


def log_request(method: str, path: str, headers: dict[str, str], body: bytes | None) -> None:
    """Log an incoming HTTP request.

    Args:
        method: HTTP method
        path: Request path
        headers: Request headers
        body: Request body (if any)
    """
    logger.info("=" * 80)
    logger.info(f">>> INCOMING REQUEST: {method} {path}")
    logger.info("-" * 80)

    # Log interesting headers
    interesting_headers = [
        "Content-Type",
        "Content-Length",
        "Depth",
        "Destination",
        "Overwrite",
        "If-Match",
        "If-None-Match",
        "Authorization",
    ]

    logger.info("Headers:")
    for header in interesting_headers:
        value = headers.get(header.lower(), headers.get(header))
        if value:
            # Redact authorization
            if header == "Authorization":
                value = "[REDACTED]"
            logger.info(f"  {header}: {value}")

    # Log body if present
    if body:
        content_type = headers.get("content-type", "")
        logger.info("-" * 80)
        logger.info("Request Body:")

        if is_xml_content(content_type):
            formatted = format_xml(body)
            for line in formatted.split("\n"):
                if line.strip():
                    logger.info(f"  {line}")
        else:
            # Log non-XML bodies with size info
            body_preview = body[:200].decode("utf-8", errors="replace")
            logger.info(f"  [{len(body)} bytes] {body_preview}")
            if len(body) > 200:
                logger.info(f"  ... ({len(body) - 200} more bytes)")

    logger.info("=" * 80)


def log_response(status_code: int, headers: dict[str, Any], body: bytes | None) -> None:
    """Log an outgoing HTTP response.

    Args:
        status_code: HTTP status code
        headers: Response headers
        body: Response body (if any)
    """
    logger.info("=" * 80)
    logger.info(f"<<< OUTGOING RESPONSE: {status_code}")
    logger.info("-" * 80)

    # Log interesting headers
    interesting_headers = ["Content-Type", "Content-Length", "ETag", "DAV", "Allow"]

    logger.info("Headers:")
    for header in interesting_headers:
        value = headers.get(header.lower(), headers.get(header))
        if value:
            logger.info(f"  {header}: {value}")

    # Log body if present
    if body:
        content_type = headers.get("content-type", "")
        logger.info("-" * 80)
        logger.info("Response Body:")

        if is_xml_content(content_type):
            formatted = format_xml(body)
            for line in formatted.split("\n"):
                if line.strip():
                    logger.info(f"  {line}")
        else:
            # Log non-XML bodies with size info
            body_preview = body[:200].decode("utf-8", errors="replace")
            logger.info(f"  [{len(body)} bytes] {body_preview}")
            if len(body) > 200:
                logger.info(f"  ... ({len(body) - 200} more bytes)")

    logger.info("=" * 80)
    logger.info("")  # Empty line for readability


def log_inform_request(method: str, url: str, headers: dict[str, Any], body: Any) -> None:
    """Log an outgoing INFORM API request in JSON format.

    Args:
        method: HTTP method
        url: Request URL
        headers: Request headers
        body: Request body (dict, list, or None)
    """
    request_data = {
        "type": "request",
        "method": method,
        "url": url,
        "headers": {k: "[REDACTED]" if k.lower() == "authorization" else v for k, v in headers.items()},
    }

    if body is not None:
        request_data["body"] = body

    inform_logger.info(json.dumps(request_data, indent=2, ensure_ascii=False))


def log_inform_response(status_code: int, body: Any) -> None:
    """Log an incoming INFORM API response in JSON format.

    Args:
        status_code: HTTP status code
        headers: Response headers
        body: Response body (dict, list, or None)
    """
    response_data = {
        "type": "response",
        "status_code": status_code,
    }

    if body is not None:
        response_data["body"] = body

    inform_logger.info(json.dumps(response_data, indent=2, ensure_ascii=False))


def setup_debug_logging() -> None:
    """Configure debug logging for the WebDAV server."""
    # Configure logger
    logger.setLevel(logging.DEBUG)

    # Create console handler with custom formatter
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)

    # Simple format - just the message (since we format the logs ourselves)
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(handler)

    # Prevent propagation to avoid duplicate logs
    logger.propagate = False


def setup_inform_debug_logging() -> None:
    """Configure debug logging for INFORM API requests/responses."""
    # Configure logger
    inform_logger.setLevel(logging.DEBUG)

    # Create console handler with custom formatter
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)

    # Simple format - just the message (since we format the logs ourselves)
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)

    # Add handler to logger
    inform_logger.addHandler(handler)

    # Prevent propagation to avoid duplicate logs
    inform_logger.propagate = False
