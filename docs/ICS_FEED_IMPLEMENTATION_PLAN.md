# ICS Feed Implementation Plan

## Overview

This document outlines the implementation plan for adding a calendar subscription (.ics) HTTP feed endpoint to py-webdav. The new endpoint will provide read-only access to calendar events via a simple HTTP URL.

**Goal**: Implement `/feed.ics?calendar=INFO` endpoint where `INFO` is the OWNER_KEY (employee key)

**Approach**: Reuse existing INFORM API client and extract shared code from CalDAV implementation

---

## Current Architecture Analysis

### Existing CalDAV Components

```
py_webdav/
├── inform_api_client.py         # ✅ Already reusable
├── server.py                     # HTTP handler with CalDAV routing
└── caldav/
    ├── inform_backend.py         # Contains event conversion logic
    ├── server.py                 # CalDAV protocol handlers
    └── backend.py               # CalDAV interface
```

### Key Shared Functionality

The following components from `InformCalDAVBackend` (caldav/inform_backend.py) can be shared:

| Method | Lines | Purpose | Reusability |
|--------|-------|---------|-------------|
| `_inform_event_to_ical()` | 304-495 | INFORM → iCalendar conversion | ✅ 100% reusable |
| `_occurrence_time_to_utc()` | 100-133 | Timezone conversion (server TZ → UTC) | ✅ 100% reusable |
| `_format_datetime_for_inform()` | 78-98 | Format datetime for API | ✅ 100% reusable |
| `_inform_series_schema_to_rrule()` | 135-228 | RRULE generation from series schema | ✅ 100% reusable |
| `_calculate_first_occurrence()` | 274-302 | Calculate first RRULE occurrence | ✅ 100% reusable |
| `_get_sync_date_range()` | 67-76 | Calculate date range (now ± N weeks) | ✅ 100% reusable |

**All conversion logic is independent of CalDAV protocol and can be extracted.**

---

## Implementation Plan

### Phase 1: Extract Shared Code

**Goal**: Create a shared library for INFORM event conversion that both CalDAV and ICS feed can use.

#### 1.1 Create `py_webdav/inform_calendar_utils.py`

New file containing extracted utility functions and a converter class:

```python
class InformCalendarConverter:
    """Shared utilities for converting INFORM events to iCalendar format.

    Can be used by both CalDAV backend and ICS feed endpoint.
    """

    def __init__(self, server_timezone: str = "Europe/Berlin"):
        self.server_timezone = server_timezone

    # Timezone conversion methods
    def format_datetime_for_inform(self, dt: datetime) -> str:
        """Format datetime as YYYY-MM-DDTHH:MM:SSZ for INFORM API."""

    def occurrence_time_to_utc(
        self, date_str: str, seconds_from_midnight: float
    ) -> datetime:
        """Convert INFORM occurrence time (server TZ) to UTC."""

    # RRULE generation methods
    def inform_series_schema_to_rrule(self, series_schema: dict) -> str | None:
        """Convert INFORM seriesSchema to iCalendar RRULE string."""

    def calculate_first_occurrence(
        self, series_start_dt: datetime, rrule_str: str
    ) -> datetime:
        """Calculate first occurrence matching RRULE constraints."""

    # Main conversion method
    def inform_event_to_ical(self, event_data: dict[str, Any]) -> str:
        """Convert INFORM event to iCalendar VEVENT string.

        Handles:
        - Single vs serial (recurring) events
        - Timezone conversion
        - RRULE generation
        - Reminders/alarms
        - Privacy settings

        Returns:
            iCalendar string (BEGIN:VCALENDAR...END:VCALENDAR)
        """

    # Utility methods
    def get_sync_date_range(self, weeks: int = 2) -> tuple[datetime, datetime]:
        """Calculate date range for syncing (now ± N weeks)."""
```

**Files to modify:**
- **CREATE**: `py_webdav/inform_calendar_utils.py` (new shared library)

**Extraction strategy:**
1. Copy methods from `InformCalDAVBackend` (inform_backend.py:78-495)
2. Remove CalDAV-specific code (e.g., CalendarObject creation)
3. Keep only pure conversion logic
4. Add comprehensive docstrings
5. Preserve all INFORM API quirks handling (timezone, first occurrence, etc.)

#### 1.2 Update `InformCalDAVBackend` to use shared library

**Goal**: Refactor CalDAV backend to use the new shared converter.

```python
# caldav/inform_backend.py

from ..inform_calendar_utils import InformCalendarConverter

class InformCalDAVBackend:
    def __init__(self, ...):
        self.api_client = InformAPIClient(config, debug=debug)
        # NEW: Use shared converter
        self.converter = InformCalendarConverter(
            server_timezone=self.api_client.config.server_timezone
        )

    def _inform_event_to_ical(self, event_data: dict[str, Any]) -> str:
        """Convert INFORM event to iCalendar (delegates to converter)."""
        return self.converter.inform_event_to_ical(event_data)

    # Remove duplicated methods, delegate to converter:
    # - _occurrence_time_to_utc() → self.converter.occurrence_time_to_utc()
    # - _format_datetime_for_inform() → self.converter.format_datetime_for_inform()
    # - etc.
```

**Files to modify:**
- **MODIFY**: `py_webdav/caldav/inform_backend.py`
  - Replace internal methods with calls to `InformCalendarConverter`
  - Remove duplicated code (~400 lines)
  - Keep CalDAV-specific logic (CalendarObject creation, path parsing, etc.)

**Benefits:**
- ✅ Single source of truth for event conversion
- ✅ CalDAV backend becomes simpler (~1045 → ~650 lines)
- ✅ Easier to test conversion logic independently
- ✅ Both CalDAV and ICS feed get bug fixes automatically

---

### Phase 2: Create ICS Feed Endpoint

**Goal**: Implement the `/feed.ics?calendar=OWNER_KEY` endpoint.

#### 2.1 Create `py_webdav/ics_feed.py`

New file containing the ICS feed handler:

```python
"""ICS feed endpoint for calendar subscriptions.

Provides read-only HTTP access to calendar events via .ics URL:
    GET /feed.ics?calendar=INFO

Where INFO is the OWNER_KEY (employee key).
"""

from datetime import datetime
from starlette.requests import Request
from starlette.responses import Response

from .inform_api_client import InformAPIClient, InformConfig
from .inform_calendar_utils import InformCalendarConverter


class ICSFeedHandler:
    """Handler for ICS feed endpoint.

    Generates a single .ics file containing all events for a calendar owner.
    """

    def __init__(
        self,
        config: InformConfig | None = None,
        sync_weeks: int = 2,
        debug: bool = False,
    ):
        """Initialize ICS feed handler.

        Args:
            config: INFORM API configuration
            sync_weeks: Number of weeks before/after to sync (default: 2)
            debug: Enable debug logging
        """
        self.api_client = InformAPIClient(config, debug=debug)
        self.converter = InformCalendarConverter(
            server_timezone=self.api_client.config.server_timezone
        )
        self.sync_weeks = sync_weeks

    async def handle_feed_request(self, request: Request) -> Response:
        """Handle GET /feed.ics?calendar=OWNER_KEY

        Process:
        1. Extract calendar parameter (OWNER_KEY)
        2. Fetch events from INFORM API for date range
        3. Deduplicate recurring event occurrences
        4. Convert each event to iCalendar format
        5. Combine into single VCALENDAR with multiple VEVENTs
        6. Return as text/calendar response

        Args:
            request: HTTP request

        Returns:
            Response with Content-Type: text/calendar

        Raises:
            400 Bad Request: Missing calendar parameter
            500 Internal Server Error: API or conversion errors
        """
        # Extract calendar parameter
        owner_key = request.query_params.get("calendar")
        if not owner_key:
            return Response(
                content="Missing 'calendar' parameter",
                status_code=400,
                media_type="text/plain"
            )

        try:
            # Calculate date range
            start_dt, end_dt = self.converter.get_sync_date_range(self.sync_weeks)

            # Fetch events from INFORM API
            start_str = self.converter.format_datetime_for_inform(start_dt)
            end_str = self.converter.format_datetime_for_inform(end_dt)

            events_response = await self.api_client.get_calendar_events_occurrences(
                owner_key=owner_key,
                start_datetime=start_str,
                end_datetime=end_str,
                limit=1000
            )

            events = events_response.get("calendarEvents", [])

            # Deduplicate recurring events (same logic as CalDAV)
            seen_keys = set()
            unique_events = []

            for event_data in events:
                event_key = event_data.get("key", "")
                if event_key in seen_keys:
                    continue

                seen_keys.add(event_key)

                # Fetch full event if this is an occurrence
                # (quirk: occurrences endpoint doesn't include seriesSchema)
                if event_data.get("occurrenceId"):
                    full_event = await self.api_client.get_calendar_event(
                        event_key, fields=["all"]
                    )
                    event_data = full_event

                unique_events.append(event_data)

            # Generate combined iCalendar with all events
            ical_content = self._generate_combined_ical(unique_events)

            # Return as text/calendar
            return Response(
                content=ical_content,
                media_type="text/calendar",
                headers={
                    "Content-Disposition": f'inline; filename="calendar-{owner_key}.ics"'
                }
            )

        except Exception as e:
            # Log error and return 500
            if self.api_client.debug:
                import traceback
                traceback.print_exc()

            return Response(
                content=f"Error generating calendar feed: {str(e)}",
                status_code=500,
                media_type="text/plain"
            )

    def _generate_combined_ical(self, events: list[dict]) -> str:
        """Generate single VCALENDAR with multiple VEVENTs.

        Unlike CalDAV which returns one VCALENDAR per event, the ICS feed
        returns a single VCALENDAR containing all events.

        Args:
            events: List of INFORM event data dicts

        Returns:
            Combined iCalendar string
        """
        from icalendar import Calendar as iCalendar

        cal = iCalendar()
        cal.add("prodid", "-//INFORM ICS Feed//")
        cal.add("version", "2.0")
        cal.add("calscale", "GREGORIAN")
        cal.add("method", "PUBLISH")
        cal.add("x-wr-calname", "INFORM Calendar")

        # Add each event as a VEVENT component
        for event_data in events:
            # Convert to iCalendar (returns full VCALENDAR)
            event_ical_str = self.converter.inform_event_to_ical(event_data)

            # Parse and extract VEVENT component
            from icalendar import Calendar as iCal
            event_cal = iCal.from_ical(event_ical_str)

            for component in event_cal.walk():
                if component.name == "VEVENT":
                    cal.add_component(component)

        return cal.to_ical().decode("utf-8")
```

**Files to create:**
- **CREATE**: `py_webdav/ics_feed.py` (new ICS feed handler)

**Key differences from CalDAV:**
| Aspect | CalDAV | ICS Feed |
|--------|--------|----------|
| **Protocol** | WebDAV with PROPFIND/REPORT | Simple HTTP GET |
| **Output** | Multiple VCALENDAR (one per event) | Single VCALENDAR with all events |
| **Operations** | Read + Write (PUT/DELETE) | Read-only |
| **Authentication** | CalDAV client auth | Query parameter (owner_key) |
| **Usage** | Sync clients (Apple Calendar, etc.) | Subscribe-only clients |

---

### Phase 3: Integrate with Server

**Goal**: Add routing for `/feed.ics` endpoint in main HTTP handler.

#### 3.1 Update `py_webdav/server.py`

Add ICS feed routing to `Handler.handle()`:

```python
# py_webdav/server.py

from .ics_feed import ICSFeedHandler

class Handler:
    def __init__(
        self,
        filesystem: FileSystem,
        enable_principal_discovery: bool = True,
        principal_path: str = "/principals/current/",
        calendar_home_path: str | None = None,
        addressbook_home_path: str | None = None,
        caldav_backend=None,
        carddav_backend=None,
        ics_feed_handler: ICSFeedHandler | None = None,  # NEW
        debug: bool = False,
    ):
        # ... existing init code ...
        self.ics_feed_handler = ics_feed_handler  # NEW

    async def handle(self, request: Request) -> StarletteResponse:
        # ... existing debug logging ...

        # NEW: Handle ICS feed endpoint (before CalDAV checks)
        if request.url.path == "/feed.ics" and self.ics_feed_handler:
            if request.method == "GET":
                return await self.ics_feed_handler.handle_feed_request(request)
            else:
                return StarletteResponse(
                    content="Method not allowed",
                    status_code=405
                )

        # ... existing principal discovery ...
        # ... existing CalDAV routing ...
        # ... existing WebDAV handling ...
```

**Files to modify:**
- **MODIFY**: `py_webdav/server.py`
  - Import `ICSFeedHandler`
  - Add `ics_feed_handler` parameter to `Handler.__init__()`
  - Add routing for `/feed.ics` in `Handler.handle()`

#### 3.2 Update CLI server (`py_webdav/cmd/server.py`)

Add command-line flag to enable ICS feed:

```python
# py_webdav/cmd/server.py

def main():
    parser = argparse.ArgumentParser(description="Run py-webdav server")
    # ... existing arguments ...
    parser.add_argument("--ics-feed", action="store_true", help="Enable ICS feed endpoint")
    parser.add_argument("--ics-feed-weeks", type=int, default=2,
                       help="Weeks to sync for ICS feed (default: 2)")
    # ...

    args = parser.parse_args()

    # ... existing setup ...

    # NEW: Setup ICS feed handler if enabled
    ics_feed_handler = None
    if args.ics_feed:
        from ..ics_feed import ICSFeedHandler
        ics_feed_handler = ICSFeedHandler(
            config=inform_config,
            sync_weeks=args.ics_feed_weeks,
            debug=args.debug_inform
        )
        print(f"ICS feed enabled at: /feed.ics?calendar=OWNER_KEY")

    # Create handler with ICS feed
    handler = Handler(
        filesystem=filesystem,
        # ... existing parameters ...
        ics_feed_handler=ics_feed_handler,  # NEW
        debug=args.debug,
    )
```

**Files to modify:**
- **MODIFY**: `py_webdav/cmd/server.py`
  - Add `--ics-feed` and `--ics-feed-weeks` arguments
  - Create `ICSFeedHandler` if flag enabled
  - Pass handler to `Handler` constructor

---

## Testing Plan

### Unit Tests

#### Test `InformCalendarConverter`

**File**: `tests/unit/test_inform_calendar_utils.py`

```python
def test_format_datetime_for_inform():
    """Test datetime formatting for INFORM API."""

def test_occurrence_time_to_utc():
    """Test timezone conversion from server TZ to UTC."""

def test_inform_series_schema_to_rrule_daily():
    """Test RRULE generation for daily events."""

def test_inform_series_schema_to_rrule_weekly():
    """Test RRULE generation for weekly events."""

def test_calculate_first_occurrence():
    """Test first occurrence calculation with weekday constraints."""

def test_inform_event_to_ical_single():
    """Test conversion of single event."""

def test_inform_event_to_ical_recurring():
    """Test conversion of recurring event with RRULE."""
```

#### Test `ICSFeedHandler`

**File**: `tests/unit/test_ics_feed.py`

```python
async def test_handle_feed_request_success():
    """Test successful feed generation."""

async def test_handle_feed_request_missing_calendar():
    """Test 400 error for missing calendar parameter."""

async def test_generate_combined_ical():
    """Test combining multiple events into single VCALENDAR."""

async def test_deduplication():
    """Test deduplication of recurring event occurrences."""
```

### Integration Tests

#### Test ICS Feed Endpoint

**File**: `tests/integration/test_ics_feed_integration.py`

```python
async def test_ics_feed_endpoint():
    """Test GET /feed.ics?calendar=INFO endpoint."""
    # Setup test server
    # Make HTTP request
    # Verify response content-type
    # Parse iCalendar
    # Verify events

async def test_ics_feed_with_recurring_events():
    """Test feed with series events."""

async def test_ics_feed_timezone_handling():
    """Test correct timezone conversion in feed."""
```

### Manual Testing

1. **Start server with ICS feed enabled:**
   ```bash
   py-webdav-server --caldav --ics-feed --debug-inform
   ```

2. **Test feed endpoint:**
   ```bash
   curl "http://localhost:8000/feed.ics?calendar=INFO"
   ```

3. **Verify iCalendar format:**
   - Should start with `BEGIN:VCALENDAR`
   - Should contain multiple `BEGIN:VEVENT` blocks
   - Should include RRULE for recurring events
   - Should have proper DTSTART/DTEND in UTC

4. **Test in calendar client:**
   - Add subscription URL in Apple Calendar / Thunderbird
   - Verify events appear
   - Verify recurring events display correctly

---

## Implementation Checklist

### Phase 1: Extract Shared Code
- [ ] Create `py_webdav/inform_calendar_utils.py`
  - [ ] Extract timezone conversion methods
  - [ ] Extract RRULE generation methods
  - [ ] Extract main conversion method `inform_event_to_ical()`
  - [ ] Add comprehensive docstrings
  - [ ] Add type hints
- [ ] Update `py_webdav/caldav/inform_backend.py`
  - [ ] Import `InformCalendarConverter`
  - [ ] Replace internal methods with converter calls
  - [ ] Remove duplicated code
  - [ ] Run existing CalDAV tests to verify no regressions
- [ ] Create unit tests for `InformCalendarConverter`

### Phase 2: Create ICS Feed Endpoint
- [ ] Create `py_webdav/ics_feed.py`
  - [ ] Implement `ICSFeedHandler` class
  - [ ] Implement `handle_feed_request()` method
  - [ ] Implement `_generate_combined_ical()` method
  - [ ] Add error handling
  - [ ] Add logging
- [ ] Create unit tests for `ICSFeedHandler`
- [ ] Create integration tests for ICS feed

### Phase 3: Integrate with Server
- [ ] Update `py_webdav/server.py`
  - [ ] Add `ics_feed_handler` parameter
  - [ ] Add `/feed.ics` routing
  - [ ] Add method validation (GET only)
- [ ] Update `py_webdav/cmd/server.py`
  - [ ] Add `--ics-feed` argument
  - [ ] Add `--ics-feed-weeks` argument
  - [ ] Create handler if enabled
  - [ ] Pass to `Handler` constructor
- [ ] Manual testing
- [ ] Update documentation

### Phase 4: Documentation
- [ ] Add ICS_FEED.md documentation
  - [ ] Usage examples
  - [ ] URL format
  - [ ] Calendar client setup instructions
- [ ] Update README.md
  - [ ] Add ICS feed feature
  - [ ] Add command-line flags
- [ ] Add code comments

---

## File Summary

### Files to Create (3 new files)
1. `py_webdav/inform_calendar_utils.py` - Shared conversion library (~400 lines)
2. `py_webdav/ics_feed.py` - ICS feed handler (~200 lines)
3. `tests/unit/test_inform_calendar_utils.py` - Unit tests (~300 lines)
4. `tests/unit/test_ics_feed.py` - Unit tests (~200 lines)
5. `tests/integration/test_ics_feed_integration.py` - Integration tests (~150 lines)
6. `ICS_FEED.md` - Documentation (~100 lines)

### Files to Modify (3 existing files)
1. `py_webdav/caldav/inform_backend.py` - Use shared converter (~400 lines removed)
2. `py_webdav/server.py` - Add ICS feed routing (~20 lines added)
3. `py_webdav/cmd/server.py` - Add CLI flags (~15 lines added)
4. `README.md` - Add ICS feed documentation (~30 lines added)

**Total new code**: ~1,250 lines
**Total removed code**: ~400 lines (refactored)
**Net addition**: ~850 lines

---

## Benefits

### Code Quality
- ✅ **DRY principle**: Single source of truth for event conversion
- ✅ **Separation of concerns**: CalDAV protocol vs. event conversion
- ✅ **Testability**: Conversion logic can be tested independently
- ✅ **Maintainability**: Bug fixes benefit both CalDAV and ICS feed

### Features
- ✅ **Simple subscription**: Users can subscribe with just a URL
- ✅ **Read-only access**: No accidental modifications
- ✅ **Standard format**: Works with any iCalendar client
- ✅ **Reuses existing logic**: All INFORM quirks handled correctly

### Architecture
- ✅ **Modular design**: Feed handler is independent
- ✅ **Optional feature**: Can be enabled/disabled via CLI flag
- ✅ **Consistent behavior**: Same event conversion as CalDAV

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Breaking CalDAV | Low | High | Comprehensive test suite before refactoring |
| Performance issues | Low | Medium | Feed caches same as CalDAV (2 weeks) |
| INFORM API limits | Medium | Medium | Use same sync window as CalDAV |
| Timezone bugs | Low | High | Reuse tested conversion logic |

---

## Timeline Estimate

| Phase | Estimated Time |
|-------|----------------|
| Phase 1: Extract shared code | Focus on implementation |
| Phase 2: Create ICS feed | Focus on implementation |
| Phase 3: Integrate with server | Focus on implementation |
| Phase 4: Testing & docs | Focus on implementation |

**Note**: Focus on quality implementation rather than speed. Proper testing and documentation are critical.

---

## Questions for Review

1. **Sync window**: Is 2 weeks (default) appropriate for ICS feed? Should it be configurable per-request?
A: 2 weeks is OK for now.
2. **Authentication**: Should we add authentication for ICS feed, or is query parameter sufficient?
A: Not for now, but add it to the list for the future.
3. **Caching**: Should we add HTTP caching headers (ETag, Last-Modified)?
A: No, fetch the data from IN-FORM on each request for now. But add it to the list for the future.
4. **Rate limiting**: Should we implement rate limiting per owner_key?
A: No
5. **Error handling**: What information should we expose in error messages?
A: Nothing for now, just return an appropriate server error. Implement logging of ics and IN-FORM requests like in the existing client implementation. 
---

## Next Steps

1. **Review this plan** with stakeholders
2. **Get approval** for architecture decisions
3. **Start Phase 1**: Extract shared code
4. **Run existing tests** to ensure no regressions
5. **Proceed to Phase 2**: Implement ICS feed endpoint
