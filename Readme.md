# py-webdav

A Python library for WebDAV, CalDAV, and CardDAV with INFORM API integration.

## Features

- **WebDAV** (RFC 4918) - File access and management
- **CalDAV** (RFC 4791) - Calendar synchronization
- **CardDAV** (RFC 6352) - Contact synchronization
- **ICS Feed** - Read-only calendar subscription endpoint
- **INFORM API Integration** - Direct integration with IN-FORM calendar and contact data

## Installation

```bash
pip install py-webdav
```

## Quick Start

### Basic WebDAV Server

Start a WebDAV server serving the current directory:

```bash
py-webdav-server
```

Or specify a directory:

```bash
py-webdav-server /path/to/directory
```

### CalDAV Server

Enable CalDAV support with INFORM API integration:

```bash
py-webdav-server --caldav --debug-inform
```

Access CalDAV at: `http://localhost:8080/.well-known/caldav`

### ICS Feed (Calendar Subscriptions)

Enable read-only calendar subscription endpoint:

```bash
py-webdav-server --ics-feed --debug-inform
```

Subscribe to calendar feed at: `http://localhost:8080/feed.ics?calendar=OWNER_KEY`

Where `OWNER_KEY` is the employee key (e.g., `INFO`).

**Customize sync range:**

```bash
py-webdav-server --ics-feed --ics-feed-weeks 4
```

This syncs 4 weeks before and after the current date (default is 2 weeks).

### Combined Server

Run all features together:

```bash
py-webdav-server --caldav --carddav --ics-feed --debug --debug-inform
```

## Command-Line Options

```
usage: py-webdav-server [-h] [--addr ADDR] [--port PORT] [--caldav] [--carddav]
                        [--debug] [--debug-inform] [--ics-feed]
                        [--ics-feed-weeks ICS_FEED_WEEKS]
                        [directory]

positional arguments:
  directory             directory to serve (default: current directory)

optional arguments:
  -h, --help            show this help message and exit
  --addr ADDR           listening address (default: 127.0.0.1)
  --port PORT           listening port (default: 8080)
  --caldav              enable CalDAV calendar support
  --carddav             enable CardDAV contact support
  --debug               enable debug logging (logs request/response bodies with formatted XML)
  --debug-inform        enable debug logging for INFORM API requests/responses in JSON format
  --ics-feed            enable ICS feed endpoint for calendar subscriptions
  --ics-feed-weeks N    number of weeks before/after current date to include in ICS feed (default: 2)
```

## ICS Feed Endpoint

The ICS feed endpoint provides a simple read-only calendar subscription URL that can be used with any calendar client that supports iCalendar subscriptions (Apple Calendar, Google Calendar, Thunderbird, etc.).

### Usage

**URL Format:**
```
GET /feed.ics?calendar=OWNER_KEY
```

**Example:**
```
http://localhost:8080/feed.ics?calendar=INFO
```

### Features

- **Read-only access** - Events cannot be modified through the feed
- **Automatic updates** - Calendar clients will periodically refresh the feed
- **Standard format** - Uses standard iCalendar (RFC 5545) format
- **Recurring events** - Full support for recurring events with RRULE
- **Timezone handling** - Proper conversion from INFORM server timezone to UTC
- **Configurable sync window** - Control how many weeks of events to include

### Differences from CalDAV

| Feature | CalDAV | ICS Feed |
|---------|--------|----------|
| **Protocol** | WebDAV with PROPFIND/REPORT | Simple HTTP GET |
| **Access** | Read + Write | Read-only |
| **Authentication** | Required | Query parameter (owner_key) |
| **Output** | Multiple VCALENDAR (one per event) | Single VCALENDAR with all events |
| **Client Support** | Sync clients (Apple Calendar, etc.) | Any iCalendar subscriber |
| **Use Case** | Two-way sync | One-way subscription |

### Calendar Client Setup

**Apple Calendar:**
1. File → New Calendar Subscription
2. Enter URL: `http://localhost:8080/feed.ics?calendar=INFO`
3. Click Subscribe
4. Set refresh interval (recommended: Every 15 minutes)

**Google Calendar:**
1. Settings → Add calendar → From URL
2. Enter URL: `http://localhost:8080/feed.ics?calendar=INFO`
3. Add calendar

**Thunderbird:**
1. File → New → Calendar
2. On the Network → iCalendar (ICS)
3. Enter URL: `http://localhost:8080/feed.ics?calendar=INFO`

## Configuration

### Environment Variables

The INFORM API client requires the following environment variables:

```bash
export INFORM_CLIENT_ID="your_client_id"
export INFORM_CLIENT_SECRET="your_client_secret"
export INFORM_LICENSE="your_license"
export INFORM_USER="your_username"
export INFORM_PASSWORD="your_password"
export INFORM_TIMEZONE="Europe/Berlin"  # Server timezone (optional, default: Europe/Berlin)
```

Create a `.env` file for development (see `.env.example`):

```bash
cp .env.example .env
# Edit .env with your credentials
```

## Architecture

### Shared Components

The library uses a shared architecture for calendar event conversion:

```
┌─────────────────────────────────┐
│   InformAPIClient               │  ← OAuth2, REST API
└─────────────────────────────────┘
            ↓
┌─────────────────────────────────┐
│   InformCalendarConverter       │  ← Event conversion logic
│   - Timezone conversion         │     (shared by CalDAV & ICS Feed)
│   - RRULE generation            │
│   - INFORM → iCalendar          │
└─────────────────────────────────┘
            ↓
    ┌───────────┴──────────┐
    ↓                      ↓
┌──────────────────┐  ┌─────────────────┐
│ CalDAV Backend   │  │ ICS Feed Handler│
│ (Read/Write)     │  │ (Read-only)     │
└──────────────────┘  └─────────────────┘
```

This architecture ensures:
- **Single source of truth** for event conversion
- **Consistent behavior** between CalDAV and ICS feed
- **All INFORM API quirks** handled in one place
- **Easy maintenance** - bug fixes benefit both endpoints

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run CalDAV tests only
pytest tests/ -k caldav

# Run with coverage
pytest --cov=py_webdav
```

### Code Formatting

```bash
# Check formatting
ruff check .

# Format code
ruff format .
```

## Known Issues & Quirks

The INFORM API has several quirks that are handled by the library:

1. **Occurrence times in server timezone** - The API returns times in the server's local timezone, not UTC
2. **Series start date vs first occurrence** - For recurring events, the start date may not match the first actual occurrence
3. **Missing series metadata** - The occurrences endpoint doesn't include full series information

See [INFORM_API_QUIRKS.md](INFORM_API_QUIRKS.md) and [EVENT_KEY_HANDLING.md](EVENT_KEY_HANDLING.md) for detailed documentation.

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
