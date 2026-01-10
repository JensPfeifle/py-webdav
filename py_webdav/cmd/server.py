"""WebDAV server command-line tool."""

import argparse
import sys
from pathlib import Path


def main() -> None:
    """Main entry point for WebDAV server."""
    parser = argparse.ArgumentParser(
        description="WebDAV/CalDAV/CardDAV server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start server in current directory
  py-webdav-server

  # Start server on specific port
  py-webdav-server --port 8080 /path/to/directory

  # Enable CalDAV and CardDAV
  py-webdav-server --caldav --carddav /path/to/directory

The server supports:
  - WebDAV (RFC 4918) for file access
  - CalDAV (RFC 4791) for calendar synchronization (with --caldav)
  - CardDAV (RFC 6352) for contact synchronization (with --carddav)

Endpoints:
  - WebDAV:  http://localhost:PORT/
  - CalDAV:  http://localhost:PORT/.well-known/caldav
  - CardDAV: http://localhost:PORT/.well-known/carddav
        """,
    )
    parser.add_argument(
        "--addr",
        default="127.0.0.1",
        help="listening address (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="listening port (default: 8080)",
    )
    parser.add_argument(
        "--caldav",
        action="store_true",
        help="enable CalDAV calendar support",
    )
    parser.add_argument(
        "--carddav",
        action="store_true",
        help="enable CardDAV contact support",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="enable debug logging (logs request/response bodies with formatted XML)",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="directory to serve (default: current directory)",
    )

    args = parser.parse_args()

    # Validate directory
    directory = Path(args.directory).resolve()
    if not directory.exists():
        print(f"Error: directory does not exist: {directory}", file=sys.stderr)
        sys.exit(1)
    if not directory.is_dir():
        print(f"Error: path is not a directory: {directory}", file=sys.stderr)
        sys.exit(1)

    # Setup debug logging if requested
    if args.debug:
        from py_webdav.debug import setup_debug_logging
        setup_debug_logging()

    # Create WebDAV app with CalDAV/CardDAV support if requested
    from starlette.applications import Starlette
    from starlette.routing import Route

    from py_webdav import LocalFileSystem
    from py_webdav.server import Handler

    filesystem = LocalFileSystem(directory)

    # Create backends if CalDAV/CardDAV are enabled
    caldav_backend = None
    carddav_backend = None

    if args.caldav:
        from py_webdav.caldav import InformCalDAVBackend
        caldav_backend = InformCalDAVBackend(owner_key="INFO")

    if args.carddav:
        from py_webdav.carddav import InformCardDAVBackend
        carddav_backend = InformCardDAVBackend()
        
        

    # Create handler with backends
    handler = Handler(
        filesystem,
        enable_principal_discovery=(args.caldav or args.carddav),
        caldav_backend=caldav_backend,
        carddav_backend=carddav_backend,
        debug=args.debug,
    )

    async def webdav_handler(request):  # type: ignore
        return await handler.handle(request)

    # Create Starlette app
    app = Starlette(
        routes=[
            Route(
                "/{path:path}",
                webdav_handler,
                methods=["GET", "HEAD", "PUT", "DELETE", "OPTIONS", "PROPFIND", "PROPPATCH", "MKCOL", "COPY", "MOVE", "REPORT"],
            ),
        ]
    )

    # Run with uvicorn
    import uvicorn

    print(f"WebDAV server listening on {args.addr}:{args.port}")
    print(f"Serving directory: {directory}")
    if args.caldav:
        print(f"CalDAV enabled: http://{args.addr}:{args.port}/.well-known/caldav")
        print(f"  Calendars: {directory}/calendars/")
    if args.carddav:
        print(f"CardDAV enabled: http://{args.addr}:{args.port}/.well-known/carddav")
        print(f"  Contacts: {directory}/contacts/")

    uvicorn.run(
        app,
        host=args.addr,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
