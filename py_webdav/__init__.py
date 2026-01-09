"""A Python library for WebDAV, CalDAV and CardDAV."""

from .client import Client
from .fs_local import LocalFileSystem
from .server import Handler, create_app
from .webdav import (
    ConditionalMatch,
    CopyOptions,
    CreateOptions,
    FileInfo,
    MoveOptions,
    RemoveAllOptions,
)

__version__ = "0.1.0"

__all__ = [
    "Client",
    "LocalFileSystem",
    "Handler",
    "create_app",
    "ConditionalMatch",
    "CopyOptions",
    "CreateOptions",
    "FileInfo",
    "MoveOptions",
    "RemoveAllOptions",
]
