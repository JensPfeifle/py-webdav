# Event Key vs Occurrence ID Handling

## Summary

The implementation correctly handles INFORM's distinction between event `key` (shared by all occurrences) and `occurrenceId` (unique per occurrence) to ensure proper CalDAV behavior for recurring events.

## INFORM API Behavior

When querying the INFORM API for calendar event occurrences (`/calendarEventsOccurrences`):

1. **Single Events**: Returned once with a `key` but no `occurrenceId`
2. **Series/Recurring Events**: Each occurrence is returned separately with:
   - **`key`**: Same for all occurrences (the "master" event ID)
   - **`occurrenceId`**: Unique for each occurrence instance

### Example

```
Event: "Weekly Meeting" (every weekday for 21 days)

API returns 21 entries:
- Entry 1: key="74006900000003", occurrenceId="740071" (Monday Jan 13)
- Entry 2: key="74006900000003", occurrenceId="740072" (Tuesday Jan 14)
- Entry 3: key="74006900000003", occurrenceId="740073" (Wednesday Jan 15)
...
- Entry 21: key="74006900000003", occurrenceId="740091" (Friday Jan 31)
```

## CalDAV Requirements

For CalDAV to work correctly with recurring events:

1. **UID**: Must be the SAME for all occurrences (use `key`)
2. **CalDAV Path**: Must be the SAME for all occurrences (use `key`)
3. **Single Object**: Client should see ONE event with RRULE, not 21 separate events
4. **RRULE**: Must be generated from the event's `seriesSchema`

## Implementation

### 1. Deduplication (`list_calendar_objects` and `query_calendar_objects`)

```python
seen_keys = set()

for event_data in events:
    event_key = event_data.get("key", "")
    if not event_key or event_key in seen_keys:
        continue  # Skip duplicates

    seen_keys.add(event_key)
    # ... process event once
```

**Location**: `py_webdav/caldav/inform_backend.py:786-794, 868-876`

### 2. Full Event Fetch for Occurrences

When an occurrence is detected, fetch the full event to get `seriesSchema`:

```python
occurrence_id = event_data.get("occurrenceId")
if occurrence_id:
    # This is an occurrence - fetch full event with all fields
    full_event_data = await self.api_client.get_calendar_event(
        event_key, fields=["all"]
    )
    event_data = full_event_data
```

**Location**: `py_webdav/caldav/inform_backend.py:797-808, 878-888`

**Why?** The `/calendarEventsOccurrences` endpoint doesn't include:
- `eventMode` (needed to identify "serial" vs "single")
- `seriesSchema` (needed to generate RRULE)

### 3. CalDAV Path Generation

```python
object_path = f"{calendar_path}{event_key}.ics"
```

**Location**: `py_webdav/caldav/inform_backend.py:818, 893`

Uses `event_key` (not `occurrenceId`) so all occurrences share the same path.

### 4. iCalendar UID

```python
event_key = event_data.get("key", "")
event.add("uid", event_key)
```

**Location**: `py_webdav/caldav/inform_backend.py:289-290`

Uses `event_key` for the UID so all occurrences have the same UID.

### 5. RRULE Generation

```python
if event_mode == "serial":
    series_schema = event_data.get("seriesSchema", {})
    rrule_str = self._inform_series_schema_to_rrule(series_schema)
    if rrule_str:
        event.add("rrule", rrule_str)
```

**Location**: `py_webdav/caldav/inform_backend.py:333-362`

Generates RRULE from the event's `seriesSchema`.

## Verification Results

### Test 1: Event Key Distribution

```
Total occurrences returned: 42
Unique event keys: 2

Event 1: key="74006900000003" - 21 occurrences
Event 2: key="7400690000000B" - 21 occurrences

✓ Each series event appears multiple times with same key
✓ Each occurrence has unique occurrenceId
```

### Test 2: Field Availability

**Occurrences endpoint** (`/calendarEventsOccurrences`):
- ✓ key: Present
- ✓ occurrenceId: Present
- ✗ eventMode: MISSING
- ✗ seriesSchema: MISSING

**Full event endpoint** (`/calendarEvents/{key}?fields=all`):
- ✓ key: Present
- ✓ eventMode: Present ("serial")
- ✓ seriesSchema: Present (complete schema)
- ✓ seriesStartDate: Present
- ✓ occurrenceStartTime: Present
- ✓ occurrenceEndTime: Present

**Conclusion**: Must fetch full event for occurrences to get RRULE data.

### Test 3: CalDAV Behavior

```
For event with key="74006900000003":
  CalDAV path:   /calendars/user/calendar/74006900000003.ics
  iCalendar UID: 74006900000003
  RRULE:         FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR

✓ Client sees ONE event (not 21)
✓ Event has RRULE for recurrence pattern
✓ All occurrences share same UID
✓ Correct CalDAV behavior
```

## Edge Cases Handled

1. **Multiple occurrences in query range**: Deduplication ensures event appears once
2. **Missing seriesSchema**: No RRULE generated, falls back to single event
3. **All-day recurring events**: Properly handled with date-only DTSTART
4. **Timezone conversion**: Occurrence times converted from server local time to UTC

## Related Documentation

- **INFORM_API_QUIRKS.md**: Documents API quirks including timezone handling
- **py_webdav/caldav/inform_backend.py**: Main implementation
- **diagnose_event_keys.py**: Diagnostic script to verify key/occurrence behavior
- **verify_full_event_fetch.py**: Verification script for field availability
