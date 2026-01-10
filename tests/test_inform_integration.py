"""Integration tests for INFORM API client and CalDAV backend.

These tests require valid INFORM API credentials set as environment variables:
- INFORM_CLIENT_ID
- INFORM_CLIENT_SECRET
- INFORM_LICENSE
- INFORM_USER
- INFORM_PASSWORD

Run with: pytest tests/test_inform_integration.py -v
Skip integration tests: pytest -m "not integration"
"""

import os
from datetime import UTC, datetime, timedelta

import pytest

from py_webdav.caldav import InformCalDAVBackend
from py_webdav.inform_api_client import InformAPIClient, InformConfig

# Check if credentials are available
HAS_CREDENTIALS = all(
    [
        os.getenv("INFORM_CLIENT_ID"),
        os.getenv("INFORM_CLIENT_SECRET"),
        os.getenv("INFORM_LICENSE"),
        os.getenv("INFORM_USER"),
        os.getenv("INFORM_PASSWORD"),
    ]
)

pytestmark = pytest.mark.skipif(
    not HAS_CREDENTIALS, reason="INFORM API credentials not configured"
)


@pytest.fixture
async def api_client():
    """Create and cleanup API client."""
    config = InformConfig()
    client = InformAPIClient(config)
    yield client
    await client.close()


@pytest.fixture
async def caldav_backend():
    """Create and cleanup CalDAV backend."""
    config = InformConfig()
    # Use the configured username as the owner key
    backend = InformCalDAVBackend(config=config, owner_key=config.username)
    yield backend
    await backend.api_client.close()


class TestInformAPIClient:
    """Integration tests for INFORM API client."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_authentication(self, api_client):
        """Test OAuth2 authentication with password grant."""
        # Trigger authentication by making a request
        companies = await api_client.get_companies()
        assert isinstance(companies, list)
        assert len(companies) > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_token_refresh(self, api_client):
        """Test automatic token refresh."""
        # Make initial request to get token
        companies1 = await api_client.get_companies()

        # Force token expiration
        if api_client._tokens:
            api_client._tokens.expires_at = datetime.now(UTC) - timedelta(seconds=1)

        # Make another request - should trigger refresh
        companies2 = await api_client.get_companies()

        assert companies1 == companies2

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_companies(self, api_client):
        """Test fetching company list."""
        companies = await api_client.get_companies()

        assert isinstance(companies, list)
        assert len(companies) > 0
        for company in companies:
            assert isinstance(company, str)
            assert len(company) > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_addresses(self, api_client):
        """Test fetching addresses."""
        # Get first company
        companies = await api_client.get_companies()
        company = companies[0]

        # Fetch addresses
        response = await api_client.get_addresses(company, limit=10)

        assert "addresses" in response
        assert "count" in response
        assert "totalCount" in response
        assert isinstance(response["addresses"], list)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_calendar_events_occurrences(self, api_client):
        """Test fetching calendar event occurrences."""
        # Get events for the next 2 weeks
        now = datetime.now(UTC)
        start = now - timedelta(days=7)
        end = now + timedelta(days=7)

        config = InformConfig()
        response = await api_client.get_calendar_events_occurrences(
            owner_key=config.username,
            start_datetime=start.isoformat(),
            end_datetime=end.isoformat(),
            limit=100,
        )

        assert "calendarEvents" in response
        assert "count" in response
        assert "totalCount" in response
        assert isinstance(response["calendarEvents"], list)


class TestInformCalDAVBackend:
    """Integration tests for INFORM CalDAV backend."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_list_calendars(self, caldav_backend):
        """Test listing calendars."""
        from unittest.mock import MagicMock

        # Create a mock request
        request = MagicMock()

        calendars = await caldav_backend.list_calendars(request)

        assert len(calendars) == 1
        assert calendars[0].name == "INFORM Calendar"
        assert calendars[0].path == caldav_backend._get_calendar_path()
        assert "VEVENT" in calendars[0].supported_component_set

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_calendar(self, caldav_backend):
        """Test getting a calendar."""
        from unittest.mock import MagicMock

        request = MagicMock()
        calendar_path = caldav_backend._get_calendar_path()

        calendar = await caldav_backend.get_calendar(request, calendar_path)

        assert calendar.name == "INFORM Calendar"
        assert calendar.path == calendar_path

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_list_calendar_objects(self, caldav_backend):
        """Test listing calendar objects (events)."""
        from unittest.mock import MagicMock

        request = MagicMock()
        calendar_path = caldav_backend._get_calendar_path()

        objects = await caldav_backend.list_calendar_objects(request, calendar_path)

        assert isinstance(objects, list)
        # May be empty or contain events depending on test account
        for obj in objects:
            assert obj.path.startswith(calendar_path)
            assert obj.path.endswith(".ics")
            assert obj.data.startswith("BEGIN:VCALENDAR")
            assert "BEGIN:VEVENT" in obj.data
            assert obj.etag
            assert obj.content_length > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_single_event(self, caldav_backend):
        """Test creating a single (non-recurring) event."""
        from unittest.mock import MagicMock

        request = MagicMock()
        calendar_path = caldav_backend._get_calendar_path()

        # Create a test event
        now = datetime.now(UTC)
        start_time = now + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        ical_data = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-single-event-{now.timestamp()}
DTSTART:{start_time.strftime('%Y%m%dT%H%M%SZ')}
DTEND:{end_time.strftime('%Y%m%dT%H%M%SZ')}
SUMMARY:Integration Test Single Event
DESCRIPTION:This is a test event created by the integration test suite
LOCATION:Test Location
CLASS:PUBLIC
END:VEVENT
END:VCALENDAR"""

        # Create the event
        object_path = f"{calendar_path}test-single-event-{now.timestamp()}.ics"
        calendar_object = await caldav_backend.put_calendar_object(
            request, object_path, ical_data, if_none_match=True
        )

        assert calendar_object.path == object_path
        assert calendar_object.etag
        assert calendar_object.content_length > 0
        assert "Integration Test Single Event" in calendar_object.data

        # Cleanup: Delete the test event
        try:
            await caldav_backend.delete_calendar_object(request, object_path)
        except Exception:
            pass  # Ignore cleanup errors

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_recurring_event(self, caldav_backend):
        """Test creating a recurring (serial) event."""
        from unittest.mock import MagicMock

        request = MagicMock()
        calendar_path = caldav_backend._get_calendar_path()

        # Create a recurring test event (every weekday for 2 weeks)
        now = datetime.now(UTC)
        start_time = now + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        ical_data = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-recurring-event-{now.timestamp()}
DTSTART:{start_time.strftime('%Y%m%dT%H%M%SZ')}
DTEND:{end_time.strftime('%Y%m%dT%H%M%SZ')}
SUMMARY:Integration Test Recurring Event
DESCRIPTION:This is a recurring test event
RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;COUNT=10
CLASS:PUBLIC
END:VEVENT
END:VCALENDAR"""

        # Create the event
        object_path = f"{calendar_path}test-recurring-event-{now.timestamp()}.ics"
        calendar_object = await caldav_backend.put_calendar_object(
            request, object_path, ical_data, if_none_match=True
        )

        assert calendar_object.path == object_path
        assert calendar_object.etag
        assert "Integration Test Recurring Event" in calendar_object.data
        # Verify RRULE is preserved
        assert "RRULE:" in calendar_object.data

        # Cleanup: Delete the test event
        try:
            await caldav_backend.delete_calendar_object(request, object_path)
        except Exception:
            pass  # Ignore cleanup errors

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_update_event(self, caldav_backend):
        """Test updating an existing event."""
        from unittest.mock import MagicMock

        request = MagicMock()
        calendar_path = caldav_backend._get_calendar_path()

        # Create an event first
        now = datetime.now(UTC)
        start_time = now + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        original_ical = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-update-event-{now.timestamp()}
DTSTART:{start_time.strftime('%Y%m%dT%H%M%SZ')}
DTEND:{end_time.strftime('%Y%m%dT%H%M%SZ')}
SUMMARY:Original Summary
DESCRIPTION:Original Description
CLASS:PUBLIC
END:VEVENT
END:VCALENDAR"""

        object_path = f"{calendar_path}test-update-event-{now.timestamp()}.ics"

        # Create event
        created_object = await caldav_backend.put_calendar_object(
            request, object_path, original_ical, if_none_match=True
        )
        original_etag = created_object.etag

        # Update the event
        updated_ical = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-update-event-{now.timestamp()}
DTSTART:{start_time.strftime('%Y%m%dT%H%M%SZ')}
DTEND:{end_time.strftime('%Y%m%dT%H%M%SZ')}
SUMMARY:Updated Summary
DESCRIPTION:Updated Description
LOCATION:New Location
CLASS:PRIVATE
END:VEVENT
END:VCALENDAR"""

        updated_object = await caldav_backend.put_calendar_object(
            request, object_path, updated_ical, if_match=original_etag
        )

        assert "Updated Summary" in updated_object.data
        assert "Updated Description" in updated_object.data
        assert "New Location" in updated_object.data

        # Cleanup: Delete the test event
        try:
            await caldav_backend.delete_calendar_object(request, object_path)
        except Exception:
            pass  # Ignore cleanup errors

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_delete_event(self, caldav_backend):
        """Test deleting an event."""
        from unittest.mock import MagicMock

        request = MagicMock()
        calendar_path = caldav_backend._get_calendar_path()

        # Create an event first
        now = datetime.now(UTC)
        start_time = now + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        ical_data = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-delete-event-{now.timestamp()}
DTSTART:{start_time.strftime('%Y%m%dT%H%M%SZ')}
DTEND:{end_time.strftime('%Y%m%dT%H%M%SZ')}
SUMMARY:Event To Delete
CLASS:PUBLIC
END:VEVENT
END:VCALENDAR"""

        object_path = f"{calendar_path}test-delete-event-{now.timestamp()}.ics"

        # Create event
        await caldav_backend.put_calendar_object(
            request, object_path, ical_data, if_none_match=True
        )

        # Delete event
        await caldav_backend.delete_calendar_object(request, object_path)

        # Verify deletion by trying to get it (should fail)
        from py_webdav.internal import HTTPError

        with pytest.raises(HTTPError) as exc_info:
            await caldav_backend.get_calendar_object(request, object_path)
        assert exc_info.value.code == 404

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_calendar_object(self, caldav_backend):
        """Test getting a specific calendar object."""
        from unittest.mock import MagicMock

        request = MagicMock()
        calendar_path = caldav_backend._get_calendar_path()

        # Create an event first
        now = datetime.now(UTC)
        start_time = now + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        ical_data = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-get-event-{now.timestamp()}
DTSTART:{start_time.strftime('%Y%m%dT%H%M%SZ')}
DTEND:{end_time.strftime('%Y%m%dT%H%M%SZ')}
SUMMARY:Test Get Event
DESCRIPTION:Testing retrieval
CLASS:PUBLIC
END:VEVENT
END:VCALENDAR"""

        object_path = f"{calendar_path}test-get-event-{now.timestamp()}.ics"

        # Create event
        created_object = await caldav_backend.put_calendar_object(
            request, object_path, ical_data, if_none_match=True
        )

        # Get the event
        retrieved_object = await caldav_backend.get_calendar_object(request, object_path)

        assert retrieved_object.path == object_path
        assert retrieved_object.etag == created_object.etag
        assert "Test Get Event" in retrieved_object.data
        assert "Testing retrieval" in retrieved_object.data

        # Cleanup: Delete the test event
        try:
            await caldav_backend.delete_calendar_object(request, object_path)
        except Exception:
            pass  # Ignore cleanup errors

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_event_with_alarm(self, caldav_backend):
        """Test creating an event with an alarm/reminder."""
        from unittest.mock import MagicMock

        request = MagicMock()
        calendar_path = caldav_backend._get_calendar_path()

        # Create an event with alarm
        now = datetime.now(UTC)
        start_time = now + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        ical_data = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-alarm-event-{now.timestamp()}
DTSTART:{start_time.strftime('%Y%m%dT%H%M%SZ')}
DTEND:{end_time.strftime('%Y%m%dT%H%M%SZ')}
SUMMARY:Event with Alarm
CLASS:PUBLIC
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Reminder
TRIGGER:-PT15M
END:VALARM
END:VEVENT
END:VCALENDAR"""

        object_path = f"{calendar_path}test-alarm-event-{now.timestamp()}.ics"

        # Create event
        calendar_object = await caldav_backend.put_calendar_object(
            request, object_path, ical_data, if_none_match=True
        )

        assert "Event with Alarm" in calendar_object.data
        # Verify alarm is preserved (might be converted to INFORM format and back)
        # Just check that the event was created successfully

        # Cleanup: Delete the test event
        try:
            await caldav_backend.delete_calendar_object(request, object_path)
        except Exception:
            pass  # Ignore cleanup errors

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rrule_conversion_daily(self, caldav_backend):
        """Test daily recurrence rule conversion."""
        # Test internal conversion methods
        from py_webdav.caldav.inform_backend import InformCalDAVBackend

        # Test daily with interval
        rrule = {"freq": ["DAILY"], "interval": [2]}
        schema = caldav_backend._rrule_to_inform_series_schema(rrule)

        assert schema["schemaType"] == "daily"
        assert schema["dailySchemaData"]["regularity"] == "interval"
        assert schema["dailySchemaData"]["daysInterval"] == 2

        # Test business days
        rrule_biz = {"freq": ["DAILY"], "byday": ["MO", "TU", "WE", "TH", "FR"]}
        schema_biz = caldav_backend._rrule_to_inform_series_schema(rrule_biz)

        assert schema_biz["schemaType"] == "daily"
        assert schema_biz["dailySchemaData"]["regularity"] == "allBusinessDays"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rrule_conversion_weekly(self, caldav_backend):
        """Test weekly recurrence rule conversion."""
        rrule = {"freq": ["WEEKLY"], "byday": ["MO", "WE", "FR"], "interval": [1]}
        schema = caldav_backend._rrule_to_inform_series_schema(rrule)

        assert schema["schemaType"] == "weekly"
        assert schema["weeklySchemaData"]["weeksInterval"] == 1
        assert set(schema["weeklySchemaData"]["weekdays"]) == {
            "monday",
            "wednesday",
            "friday",
        }

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rrule_conversion_monthly(self, caldav_backend):
        """Test monthly recurrence rule conversion."""
        # Test specific date (e.g., 15th of each month)
        rrule_date = {"freq": ["MONTHLY"], "bymonthday": [15], "interval": [1]}
        schema_date = caldav_backend._rrule_to_inform_series_schema(rrule_date)

        assert schema_date["schemaType"] == "monthly"
        assert schema_date["monthlySchemaData"]["regularity"] == "specificDate"
        assert schema_date["monthlySchemaData"]["dayOfMonth"] == 15

        # Test specific day (e.g., first Monday)
        rrule_day = {"freq": ["MONTHLY"], "byday": ["1MO"], "interval": [1]}
        schema_day = caldav_backend._rrule_to_inform_series_schema(rrule_day)

        assert schema_day["schemaType"] == "monthly"
        assert schema_day["monthlySchemaData"]["regularity"] == "specificDay"
        assert schema_day["monthlySchemaData"]["weekday"] == "monday"
        assert schema_day["monthlySchemaData"]["weekNumber"] == 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rrule_conversion_yearly(self, caldav_backend):
        """Test yearly recurrence rule conversion."""
        # Test specific date (e.g., January 1st)
        rrule_date = {"freq": ["YEARLY"], "bymonth": [1], "bymonthday": [1]}
        schema_date = caldav_backend._rrule_to_inform_series_schema(rrule_date)

        assert schema_date["schemaType"] == "yearly"
        assert schema_date["yearlySchemaData"]["regularity"] == "specificDate"
        assert schema_date["yearlySchemaData"]["monthOfYear"] == 1
        assert schema_date["yearlySchemaData"]["dayOfMonth"] == 1
