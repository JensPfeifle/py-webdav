# py-webdav

A Python library for WebDAV, CalDAV, and CardDAV - converted from the Go library [go-webdav](https://github.com/emersion/go-webdav).

## Status

This is a Python conversion of the original Go library. Current implementation status:

- ✅ **WebDAV Core**: Fully functional
  - HTTP methods: GET, HEAD, PUT, DELETE, OPTIONS, PROPFIND, PROPPATCH, MKCOL, COPY, MOVE
  - LocalFileSystem backend
  - WebDAV client and server
  - Full property support

- ⚠️ **CalDAV**: Minimal stub implementation
  - Basic types defined
  - Full calendar support pending

- ⚠️ **CardDAV**: Minimal stub implementation
  - Basic types defined
  - Full vCard support pending

## Installation

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -e .
```

## Quick Start

### Running the WebDAV Server

```bash
# Using the command-line tool
uv run py-webdav-server --port 8080 /path/to/directory

# Or using Python
python -m py_webdav.cmd.server --port 8080 /path/to/directory
```

### Using as a Library

```python
from py_webdav import LocalFileSystem, create_app
import uvicorn

# Create filesystem backend
filesystem = LocalFileSystem("/path/to/directory")

# Create Starlette app
app = create_app(filesystem)

# Run with uvicorn
uvicorn.run(app, host="127.0.0.1", port=8080)
```

### WebDAV Client

```python
from py_webdav import Client
import asyncio

async def main():
    # Create client
    client = Client(endpoint="http://localhost:8080")

    # List directory
    files = await client.read_dir("/", recursive=False)
    for file in files:
        print(f"{file.path}: {file.size} bytes")

    # Upload file
    await client.create("/test.txt", b"Hello, World!")

    # Download file
    content = await client.open("/test.txt")
    print(content.read())

    await client.close()

asyncio.run(main())
```

## Development

```bash
# Install dev dependencies
uv sync

# Run linter
uv run ruff check py_webdav/

# Format code
uv run ruff format py_webdav/

# Run tests (when available)
uv run pytest
```

## Architecture

- **py_webdav.internal**: Low-level HTTP and XML handling
- **py_webdav**: Core WebDAV implementation
  - `server.py`: WebDAV server with Starlette
  - `client.py`: WebDAV client with httpx
  - `fs_local.py`: Local filesystem backend
  - `webdav.py`: WebDAV types and data structures
- **py_webdav.caldav**: CalDAV support (minimal)
- **py_webdav.carddav**: CardDAV support (minimal)

## Dependencies

- **starlette**: ASGI framework for the server
- **uvicorn**: ASGI server
- **httpx**: Async HTTP client
- **lxml**: XML processing
- **icalendar**: iCalendar support (for CalDAV)
- **vobject**: vCard support (for CardDAV)

## Differences from Go Version

1. **Async by default**: All I/O operations are async using `asyncio`
2. **Type hints**: Full type annotations with Python 3.11+ syntax
3. **Starlette/Uvicorn**: Uses ASGI instead of Go's http.Handler
4. **httpx**: Uses async httpx client instead of Go's http.Client
5. **pathlib**: Uses Path objects for filesystem operations

## License

MIT License (same as original Go library)

## TODO

- [ ] Complete CalDAV implementation
  - [ ] Calendar server backend
  - [ ] Calendar client
  - [ ] iCalendar parsing and validation
  - [ ] REPORT method support

- [ ] Complete CardDAV implementation
  - [ ] Address book server backend
  - [ ] Address book client
  - [ ] vCard parsing and validation

- [ ] Convert tests from Go to pytest
- [ ] Add WebDAV compliance tests
- [ ] Performance optimization
- [ ] Documentation and examples

## References

- [RFC 4918: WebDAV](https://tools.ietf.org/html/rfc4918)
- [RFC 4791: CalDAV](https://tools.ietf.org/html/rfc4791)
- [RFC 6352: CardDAV](https://tools.ietf.org/html/rfc6352)
- [Original Go implementation](https://github.com/emersion/go-webdav)
