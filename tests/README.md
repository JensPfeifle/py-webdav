# Integration Tests

## Overview

The `test_inform_integration.py` file contains integration tests for the INFORM API client and CalDAV backend. These tests make real API calls to the INFORM API.

## Prerequisites

You need valid INFORM API credentials set as environment variables:

```bash
export INFORM_CLIENT_ID="your_client_id"
export INFORM_CLIENT_SECRET="your_client_secret"
export INFORM_LICENSE="W000000"
export INFORM_USER="your_username"
export INFORM_PASSWORD="your_password"
```

## Running Tests

### Run all tests (including integration tests)

```bash
pytest tests/test_inform_integration.py -v
```

### Run only integration tests

```bash
pytest -m integration -v
```

### Skip integration tests

```bash
pytest -m "not integration" -v
```

### Run all tests with coverage

```bash
pytest --cov=py_webdav --cov-report=html
```

## Test Coverage

The integration test suite covers:

### INFORM API Client (`TestInformAPIClient`)
- ✅ OAuth2 authentication with password grant
- ✅ Automatic token refresh
- ✅ Fetching company list
- ✅ Fetching addresses
- ✅ Fetching calendar event occurrences

### INFORM CalDAV Backend (`TestInformCalDAVBackend`)
- ✅ Listing calendars
- ✅ Getting calendar details
- ✅ Listing calendar objects (events)
- ✅ Creating single (non-recurring) events
- ✅ Creating recurring (serial) events
- ✅ Updating existing events
- ✅ Deleting events
- ✅ Getting specific calendar objects
- ✅ Events with alarms/reminders
- ✅ RRULE conversion (daily, weekly, monthly, yearly)

## Notes

- Integration tests are automatically skipped if credentials are not configured
- Tests create and delete calendar events in your INFORM account
- Test events are prefixed with "Integration Test" or "test-" for easy identification
- All test events are cleaned up after execution (best effort)
- Tests use a 2-week window for event sync (configurable in CalDAV backend)

## Troubleshooting

### Tests are skipped

If you see "INFORM API credentials not configured", ensure all required environment variables are set:

```bash
env | grep INFORM
```

### Authentication errors

- Verify your credentials are correct
- Check that your INFORM license is active
- Ensure your user has calendar access permissions

### Network errors

- Check your internet connection
- Verify you can reach `https://testapi.in-software.com/v1`
- Check firewall settings

### API errors

- Check INFORM API version compatibility (requires 2024.00+)
- Verify your account has CalDAV enabled
- Review INFORM API documentation for any breaking changes
