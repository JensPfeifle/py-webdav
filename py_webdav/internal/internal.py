"""Low-level helpers for WebDAV clients and servers."""

from __future__ import annotations

from enum import IntEnum
from typing import Any
from urllib.parse import ParseResult as URL


class Depth(IntEnum):
    """Depth indicates whether a request applies to the resource's members.

    Defined in RFC 4918 section 10.2.
    """

    ZERO = 0  # Request applies only to the resource
    ONE = 1  # Request applies to resource and its internal members only
    INFINITY = -1  # Request applies to resource and all of its members


def parse_depth(s: str) -> Depth:
    """Parse a Depth header."""
    if s == "0":
        return Depth.ZERO
    elif s == "1":
        return Depth.ONE
    elif s == "infinity":
        return Depth.INFINITY
    else:
        raise ValueError("webdav: invalid Depth value")


def depth_to_string(d: Depth) -> str:
    """Format the depth."""
    if d == Depth.ZERO:
        return "0"
    elif d == Depth.ONE:
        return "1"
    elif d == Depth.INFINITY:
        return "infinity"
    else:
        raise ValueError("webdav: invalid Depth value")


def parse_overwrite(s: str) -> bool:
    """Parse an Overwrite header."""
    if s == "T":
        return True
    elif s == "F":
        return False
    else:
        raise ValueError("webdav: invalid Overwrite value")


def format_overwrite(overwrite: bool) -> str:
    """Format an Overwrite header."""
    return "T" if overwrite else "F"


class HTTPError(Exception):
    """HTTP error with status code."""

    def __init__(self, code: int, err: Exception | None = None):
        self.code = code
        self.err = err
        super().__init__(str(self))

    def __str__(self) -> str:
        from http import HTTPStatus

        try:
            text = HTTPStatus(self.code).phrase
        except ValueError:
            text = "Unknown"

        s = f"{self.code} {text}"
        if self.err:
            return f"{s}: {self.err}"
        return s


def http_error_from_error(err: Exception | None) -> HTTPError | None:
    """Convert an error to an HTTPError."""
    if err is None:
        return None
    if isinstance(err, HTTPError):
        return err
    else:
        return HTTPError(500, err)


def is_not_found(err: Exception | None) -> bool:
    """Check if an error is a 404 Not Found."""
    if isinstance(err, HTTPError):
        return err.code == 404
    return False


def http_errorf(code: int, format_str: str, *args: Any) -> HTTPError:
    """Create an HTTPError with a formatted message."""
    return HTTPError(code, Exception(format_str % args if args else format_str))


class HrefError(Exception):
    """Error associated with a specific href."""

    def __init__(self, href: URL, err: Exception):
        self.href = href
        self.err = err
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"{self.href.geturl()}: {self.err}"
