#!/usr/bin/env python3
"""Example CalDAV/CardDAV server with filesystem backends."""

import tempfile
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route

from py_webdav.caldav import LocalCalDAVBackend
from py_webdav.carddav import LocalCardDAVBackend
from py_webdav.fs import LocalFileSystem
from py_webdav.server import Handler


async def handle_request(request):
    """Handle WebDAV request."""
    return await handler.handle(request)


if __name__ == "__main__":
    # Create temporary directory for data
    temp_dir = Path(tempfile.mkdtemp(prefix="webdav_"))
    print(f"Using data directory: {temp_dir}")

    # Create filesystem backend
    filesystem = LocalFileSystem(temp_dir)

    # Create CalDAV and CardDAV backends
    caldav_backend = LocalCalDAVBackend(temp_dir)
    carddav_backend = LocalCardDAVBackend(temp_dir)

    # Create handler with backends
    handler = Handler(
        filesystem,
        enable_principal_discovery=True,
        caldav_backend=caldav_backend,
        carddav_backend=carddav_backend,
    )

    # Create Starlette app
    app = Starlette(
        routes=[
            Route("/{path:path}", handle_request, methods=["GET", "HEAD", "PUT", "DELETE", "OPTIONS", "PROPFIND", "PROPPATCH", "MKCOL", "COPY", "MOVE"]),
        ]
    )

    print("\nStarting CalDAV/CardDAV server on http://localhost:8000")
    print("\nEndpoints:")
    print("  Principal: http://localhost:8000/principals/current/")
    print("  Calendars: http://localhost:8000/calendars/")
    print("  Contacts:  http://localhost:8000/contacts/")
    print("\nWell-known URLs:")
    print("  CalDAV:  http://localhost:8000/.well-known/caldav")
    print("  CardDAV: http://localhost:8000/.well-known/carddav")
    print("\nPress Ctrl+C to stop")

    uvicorn.run(app, host="0.0.0.0", port=8000)
