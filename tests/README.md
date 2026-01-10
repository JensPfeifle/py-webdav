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

### API Workflow Tests (`TestInformAPIWorkflows`)

These tests verify complete end-to-end workflows through the INFORM API:

- ✅ **POST → GET**: Basic create and retrieve workflow
- ✅ **POST → GET → PATCH → GET**: Create, read, update, read workflow
  - Verifies updates work correctly
  - Ensures event times are preserved after updates
- ✅ **POST → GET → DELETE → GET**: Complete lifecycle with deletion
  - Confirms deleted events cannot be retrieved
- ✅ **POST (multiple) → GET (list)**: Batch operations and filtering
  - Creates multiple events and verifies list retrieval
  - Tests date range queries
- ✅ **POST → GET → PATCH (times) → GET**: Time preservation testing
  - Updates subject only, verifies times preserved
  - Updates times, verifies time changes work
- ✅ **Recurring Event Workflow**: Serial event lifecycle
  - Create recurring event → Read → Update → Delete
  - Verifies recurrence patterns are preserved
- ✅ **Full Lifecycle**: Complete event lifecycle with multiple modifications
  - Create → Multiple updates to different fields → Delete
  - Ensures cumulative updates don't corrupt data

These workflow tests complement unit tests by catching integration issues that
might not appear in isolated tests. They verify that the API behaves correctly
across multiple sequential operations.

## Test Statistics

Current integration test coverage:
- **Total Integration Tests**: 25
  - API Client Tests: 5
  - CalDAV Backend Tests: 13
  - Workflow Tests: 7
- **Test Execution Time**: ~40-45 seconds (all tests)
- **API Calls per Test Run**: ~100+ (varies based on test selection)

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

## Best Practices

When adding new integration tests:

1. **Use descriptive test names**: Follow the pattern `test_<workflow>_<operation>`
2. **Clean up resources**: Always delete created events in `finally` blocks
3. **Use unique identifiers**: Include timestamps in test event subjects/UIDs
4. **Test both success and failure**: Verify both expected behavior and error handling
5. **Document workflows**: Add clear comments explaining the test sequence
6. **Keep tests focused**: Each test should verify one specific workflow
7. **Use appropriate timeouts**: Set reasonable timeouts for async operations
8. **Verify data integrity**: Check that operations preserve unrelated fields

## Development Workflow

When developing with these tests:

```bash
# Run tests while developing
pytest tests/test_inform_integration.py::TestInformAPIWorkflows -v

# Run specific test
pytest tests/test_inform_integration.py::TestInformAPIWorkflows::test_post_get_workflow -v

# Run with debug output
pytest tests/test_inform_integration.py -v -s

# Run with coverage
pytest tests/test_inform_integration.py --cov=py_webdav.inform_api_client --cov-report=term-missing
```
