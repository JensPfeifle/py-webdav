"""WebDAV server command-line tool."""

import argparse
import sys
from pathlib import Path


def main() -> None:
    """Main entry point for WebDAV server."""
    parser = argparse.ArgumentParser(
        description="WebDAV server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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

    # Create WebDAV app
    from py_webdav import LocalFileSystem, create_app

    filesystem = LocalFileSystem(directory)
    app = create_app(filesystem)

    # Run with uvicorn
    import uvicorn

    print(f"WebDAV server listening on {args.addr}:{args.port}")
    print(f"Serving directory: {directory}")

    uvicorn.run(
        app,
        host=args.addr,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
