# INFORM API Quirks and Behavior Documentation

This document describes unexpected or non-intuitive behaviors observed in the INFORM API.
Each entry follows the IST (actual)/SOLL (expected) format.

## Table of Contents

1. [Recurring All-Day Events Require Time Fields](#1-recurring-all-day-events-require-time-fields)
2. [DateTime Format Strictness](#2-datetime-format-strictness)
3. [Empty PATCH Requests](#3-empty-patch-requests)
4. [Series Event Occurrences Missing Schema](#4-series-event-occurrences-missing-schema)

---

## 1. Recurring All-Day Events Require Time Fields

### IST (Actual Behavior)

When creating a recurring (serial) all-day event, the API **requires** `occurrenceStartTime`, `occurrenceStartTimeEnabled`, `occurrenceEndTime`, and `occurrenceEndTimeEnabled` fields, even when `wholeDayEvent: true`.

**Request that FAILS:**
```json
{
  "eventMode": "serial",
  "subject": "All-Day Holiday",
  "ownerKey": "EMPLOYEE_KEY",
  "seriesStartDate": "2026-01-10",
  "wholeDayEvent": true,
  "seriesSchema": {
    "schemaType": "daily",
    "dailySchemaData": {
      "regularity": "interval",
      "daysInterval": 1
    }
  },
  "seriesEndDate": "2026-01-14"
}
```

**Error Response:**
```json
{
  "errorCode": "verifier_bad_body",
  "errorMessage": "Bad request. The request body contains incorrect data. [...] Reason:'Invalid schema: #\nInvalid keyword: anyOf\nInvalid document: #\n'"
}
```

**Request that SUCCEEDS:**
```json
{
  "eventMode": "serial",
  "subject": "All-Day Holiday",
  "ownerKey": "EMPLOYEE_KEY",
  "seriesStartDate": "2026-01-10",
  "occurrenceStartTime": 0,
  "occurrenceStartTimeEnabled": true,
  "occurrenceEndTime": 86340,
  "occurrenceEndTimeEnabled": true,
  "wholeDayEvent": true,
  "seriesSchema": {
    "schemaType": "daily",
    "dailySchemaData": {
      "regularity": "interval",
      "daysInterval": 1
    }
  },
  "seriesEndDate": "2026-01-14"
}
```

### SOLL (Expected Behavior)

For all-day events (`wholeDayEvent: true`), time fields should be optional or ignored, regardless of whether the event is single or recurring. The API should accept:

- **Single all-day events:** Without `startDateTime`/`endDateTime` or with date-only values
- **Recurring all-day events:** Without `occurrenceStartTime`/`occurrenceEndTime` fields

The `wholeDayEvent` flag should be sufficient to indicate that the event spans full days without specific times.

### Workaround

When creating recurring all-day events:
- Always include `occurrenceStartTime: 0` (midnight)
- Always include `occurrenceStartTimeEnabled: true`
- Always include `occurrenceEndTime: 86340` (23:59:00)
- Always include `occurrenceEndTimeEnabled: true`
- Set `wholeDayEvent: true`

### Impact

- CalDAV implementations must handle all-day recurring events specially
- Cannot directly map iCalendar `DTSTART;VALUE=DATE` to INFORM without adding time fields
- Inconsistent with single all-day events which work without explicit time fields

---

## 2. DateTime Format Strictness

### IST (Actual Behavior)

The INFORM API requires datetimes in the **exact** format `YYYY-MM-DDTHH:MM:SSZ`:
- ✅ **Accepted:** `2026-01-10T14:30:00Z` (with `Z` suffix)
- ❌ **Rejected:** `2026-01-10T14:30:00+00:00` (with timezone offset)
- ❌ **Rejected:** `2026-01-10T14:30:00.000000Z` (with microseconds)
- ❌ **Rejected:** `2026-01-10T14:30:00` (without timezone)

When sending an unsupported format like `+00:00`, the API **silently accepts** the request but **resets the time to midnight** (`00:00:00`).

**Example:**
```json
// Request
{
  "startDateTime": "2026-01-10T14:30:00+00:00"
}

// Response (time reset!)
{
  "startDateTime": "2026-01-10T00:00:00Z"
}
```

### SOLL (Expected Behavior)

The API should either:
1. **Accept ISO 8601 standard formats** including:
   - `YYYY-MM-DDTHH:MM:SSZ` (Z suffix)
   - `YYYY-MM-DDTHH:MM:SS+00:00` (timezone offset)
   - `YYYY-MM-DDTHH:MM:SS.ffffffZ` (with microseconds)
2. **Reject invalid formats with 400 error** instead of silently resetting times

**Ideal behavior:** Parse and normalize all valid ISO 8601 datetime formats to the internal representation.

### Workaround

Always format datetimes using `strftime("%Y-%m-%dT%H:%M:%SZ")`:
```python
# ✅ Correct
dt.strftime("%Y-%m-%dT%H:%M:%SZ")  # "2026-01-10T14:30:00Z"

# ❌ Incorrect (will reset to midnight)
dt.isoformat()  # "2026-01-10T14:30:00+00:00"
```

### Impact

- Python's `.isoformat()` produces `+00:00` format by default
- Other ISO 8601 libraries may use different formats
- Silent data corruption (time reset) makes debugging difficult
- Requires custom datetime formatting in all API clients

---

## 3. Empty PATCH Requests

### IST (Actual Behavior)

The INFORM API **rejects** PATCH requests with an empty body:

**Request:**
```http
PATCH /calendarEvents/74006900000001
Content-Type: application/json

{}
```

**Response:**
```json
{
  "errorCode": "verifier_bad_body",
  "errorMessage": "Bad request. [...] Reason:'Request body is empty'"
}
```

### SOLL (Expected Behavior)

Empty PATCH requests could be:
1. **Accepted as no-op** (HTTP 200/204 with no changes)
2. **Accepted to trigger validation** (useful for checking if resource exists)

However, requiring at least one field is a **reasonable design choice** for a PATCH endpoint.

### Workaround

Always include at least one field in PATCH requests. If no changes are needed, consider:
- Using GET instead to verify resource exists
- Including a redundant field (e.g., `eventMode: "single"` for single events)

### Impact

- CalDAV UPDATE operations must always include at least one field
- Cannot use empty PATCH to verify resource existence
- Minor inconvenience but acceptable API design

---

## 4. Series Event Occurrences Missing Schema

### IST (Actual Behavior)

When retrieving calendar events using the occurrences API endpoint (`GET /calendarEvents/occurrences`), the API returns occurrence data that **does not include** the series schema information for recurring events.

**Occurrences API Response** (for a recurring event):
```json
{
  "key": "74006900000092",
  "occurrenceId": "740071",
  "subject": "Weekly Team Meeting",
  "ownerKey": "KINCHI",
  "startDateTime": "2026-01-12T13:00:00Z",
  "endDateTime": "2026-01-12T14:00:00Z",
  "wholeDayEvent": false,
  "location": "Meeting Room A"
  // ❌ Missing: seriesStartDate, seriesEndDate, seriesSchema
}
```

To get the complete series information, you must make a **second request** to `GET /calendarEvents/{key}` with `fields=all`:

**Full Event Response** (with `fields=all`):
```json
{
  "key": "74006900000092",
  "eventMode": "serial",
  "subject": "Weekly Team Meeting",
  "seriesStartDate": "2026-01-10",
  "seriesEndDate": "2026-01-24",
  "occurrenceStartTime": 50400,
  "occurrenceEndTime": 54000,
  "seriesSchema": {
    "schemaType": "weekly",
    "weeklySchemaData": {
      "weekdays": ["monday", "wednesday", "friday"],
      "weeksInterval": 1
    }
  }
  // ✅ Complete series information
}
```

**Important:** Without `fields=all` parameter, even the direct GET request may not return the `seriesSchema`.

### SOLL (Expected Behavior)

The occurrences API should either:
1. **Include series metadata** in occurrence responses (at least `eventMode`, `seriesSchema`)
2. **Return complete event data** when occurrence belongs to a series
3. **Document** which fields are available in occurrences vs. full event responses

This would allow clients to:
- Understand that an occurrence is part of a series
- Reconstruct the recurrence rule without additional API calls
- Display series information in calendar views efficiently

### Workaround

When working with calendar event occurrences:

```python
# 1. Fetch occurrences
occurrences_response = await api.get_calendar_events_occurrences(
    owner_key=owner,
    start_datetime="2026-01-10T00:00:00Z",
    end_datetime="2026-01-24T23:59:59Z"
)

# 2. Check each occurrence
for event_data in occurrences_response["calendarEvents"]:
    event_key = event_data["key"]
    occurrence_id = event_data.get("occurrenceId")

    # 3. If it's an occurrence, fetch full event with ALL fields
    if occurrence_id:
        full_event = await api.get_calendar_event(
            event_key,
            fields=["all"]  # ← Required to get seriesSchema
        )
        # Now full_event has seriesStartDate, seriesEndDate, seriesSchema
        event_data = full_event
```

### Impact

- **CalDAV implementations** need to fetch full event data for each occurrence to generate RRULE
- **Performance penalty:** N+1 query problem (1 occurrences query + N individual event queries)
- **Bandwidth usage:** Fetching full event data multiple times for the same series
- **Complexity:** Requires caching and deduplication logic to avoid redundant API calls

For CalDAV sync with 100 occurrences of 10 different series events:
- Without optimization: 1 + 100 = **101 API calls**
- With deduplication: 1 + 10 = **11 API calls** (tracking unique event keys)

---

## Version Information

- **API Version Tested:** 2026.02 (INFORM API v1)
- **API Endpoint:** `https://testapi.in-software.com/v1`
- **Test Date:** 2026-01-10
- **Documentation:** https://api.in-software.com/v1/api/details/

## Contributing

If you discover additional quirks or behavioral inconsistencies in the INFORM API, please document them here following the IST/SOLL format:

1. **Clear title** describing the issue
2. **IST section** showing actual API behavior with examples
3. **SOLL section** describing expected/intuitive behavior
4. **Workaround** with code examples
5. **Impact** on implementation
