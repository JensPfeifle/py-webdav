"""WebDAV types and file information."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class FileInfo:
    """Information about a WebDAV file."""

    path: str
    size: int = 0
    mod_time: datetime | None = None
    is_dir: bool = False
    mime_type: str = ""
    etag: str = ""


@dataclass
class CreateOptions:
    """Options for creating a file."""

    if_match: ConditionalMatch | None = None
    if_none_match: ConditionalMatch | None = None


@dataclass
class RemoveAllOptions:
    """Options for removing files."""

    if_match: ConditionalMatch | None = None
    if_none_match: ConditionalMatch | None = None


@dataclass
class CopyOptions:
    """Options for copying files."""

    no_recursive: bool = False
    no_overwrite: bool = False


@dataclass
class MoveOptions:
    """Options for moving files."""

    no_overwrite: bool = False


class ConditionalMatch(str):
    """Conditional match value from If-Match or If-None-Match headers.

    According to RFC 2068 section 14.25 and 14.26.
    The value can either be a wildcard (*) or an ETag.
    """

    def is_set(self) -> bool:
        """Check if the conditional match is set."""
        return bool(self)

    def is_wildcard(self) -> bool:
        """Check if the conditional match is a wildcard."""
        return self == "*"

    def get_etag(self) -> str:
        """Get the ETag value.

        Returns:
            ETag value without quotes

        Raises:
            ValueError: If the value is not a valid ETag
        """
        if not self or self == "*":
            return ""

        # Remove quotes if present
        value = self.strip('"')
        return value

    def match_etag(self, etag: str) -> bool:
        """Check if the conditional match matches an ETag.

        Args:
            etag: ETag to match against

        Returns:
            True if matches, False otherwise
        """
        if not etag:
            return False
        if self.is_wildcard():
            return True

        return self.get_etag() == etag
