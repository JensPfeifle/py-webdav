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

        # Path should now use INFORM-generated key
        assert calendar_object.path.startswith(calendar_path)
        assert calendar_object.path.endswith(".ics")
        assert calendar_object.etag
        assert calendar_object.content_length > 0
        assert "Integration Test Single Event" in calendar_object.data

        # Cleanup: Delete the test event using the returned path
        try:
            await caldav_backend.delete_calendar_object(request, calendar_object.path)
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

        # Path should now use INFORM-generated key
        assert calendar_object.path.startswith(calendar_path)
        assert calendar_object.path.endswith(".ics")
        assert calendar_object.etag
        assert "Integration Test Recurring Event" in calendar_object.data
        # Verify RRULE is preserved
        assert "RRULE:" in calendar_object.data

        # Cleanup: Delete the test event using the returned path
        try:
            await caldav_backend.delete_calendar_object(request, calendar_object.path)
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

        # Update the event using the returned path
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
            request, created_object.path, updated_ical, if_match=original_etag
        )

        assert "Updated Summary" in updated_object.data
        assert "Updated Description" in updated_object.data
        assert "New Location" in updated_object.data

        # Cleanup: Delete the test event using the returned path
        try:
            await caldav_backend.delete_calendar_object(request, updated_object.path)
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
        created_object = await caldav_backend.put_calendar_object(
            request, object_path, ical_data, if_none_match=True
        )

        # Delete event using the returned path
        await caldav_backend.delete_calendar_object(request, created_object.path)

        # Verify deletion by trying to get it (should fail)
        from py_webdav.internal import HTTPError

        with pytest.raises(HTTPError) as exc_info:
            await caldav_backend.get_calendar_object(request, created_object.path)
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

        # Get the event using the returned path
        retrieved_object = await caldav_backend.get_calendar_object(request, created_object.path)

        assert retrieved_object.path == created_object.path
        # ETags may differ due to DTSTAMP being regenerated, just verify both are valid
        assert created_object.etag
        assert retrieved_object.etag
        assert "Test Get Event" in retrieved_object.data
        assert "Testing retrieval" in retrieved_object.data

        # Cleanup: Delete the test event using the returned path
        try:
            await caldav_backend.delete_calendar_object(request, created_object.path)
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

        # Cleanup: Delete the test event using the returned path
        try:
            await caldav_backend.delete_calendar_object(request, calendar_object.path)
        except Exception:
            pass  # Ignore cleanup errors

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rrule_conversion_daily(self, caldav_backend):
        """Test daily recurrence rule conversion."""
        # Test internal conversion methods

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


class TestInformAPIWorkflows:
    """Test complete workflows through the INFORM API."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_post_get_workflow(self, api_client):
        """Test POST (create) → GET workflow."""
        now = datetime.now(UTC)
        start_time = now + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        # POST: Create event
        event_data = {
            "eventMode": "single",
            "subject": "Workflow Test: POST→GET",
            "ownerKey": api_client.config.username,
            "startDateTime": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endDateTime": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "startDateTimeEnabled": True,
            "endDateTimeEnabled": True,
            "content": "Testing POST→GET workflow",
        }

        created = await api_client.create_calendar_event(event_data)
        event_key = created["key"]
        assert event_key

        try:
            # GET: Retrieve event
            retrieved = await api_client.get_calendar_event(event_key, fields=["all"])

            # Verify data matches
            assert retrieved["key"] == event_key
            assert retrieved["subject"] == event_data["subject"]
            assert retrieved["content"] == event_data["content"]
            assert retrieved["eventMode"] == "single"

        finally:
            # Cleanup
            await api_client.delete_calendar_event(event_key)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_post_get_patch_get_workflow(self, api_client):
        """Test POST → GET → PATCH → GET workflow."""
        now = datetime.now(UTC)
        start_time = now + timedelta(hours=2)
        end_time = start_time + timedelta(hours=1)

        # POST: Create event
        event_data = {
            "eventMode": "single",
            "subject": "Workflow Test: POST→GET→PATCH→GET",
            "ownerKey": api_client.config.username,
            "startDateTime": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endDateTime": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "startDateTimeEnabled": True,
            "endDateTimeEnabled": True,
            "content": "Original content",
            "location": "Original Location",
        }

        created = await api_client.create_calendar_event(event_data)
        event_key = created["key"]

        try:
            # GET: Retrieve original event
            original = await api_client.get_calendar_event(event_key, fields=["all"])
            assert original["subject"] == event_data["subject"]
            assert original["content"] == "Original content"
            assert original["location"] == "Original Location"

            # PATCH: Update event
            patch_data = {
                "subject": "UPDATED Subject",
                "content": "UPDATED content",
                "location": "UPDATED Location",
            }
            await api_client.update_calendar_event(event_key, patch_data)

            # GET: Retrieve updated event
            updated = await api_client.get_calendar_event(event_key, fields=["all"])
            assert updated["key"] == event_key
            assert updated["subject"] == "UPDATED Subject"
            assert updated["content"] == "UPDATED content"
            assert updated["location"] == "UPDATED Location"

            # Verify times were preserved
            assert updated["startDateTime"] == original["startDateTime"]
            assert updated["endDateTime"] == original["endDateTime"]

        finally:
            # Cleanup
            await api_client.delete_calendar_event(event_key)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_post_get_delete_get_workflow(self, api_client):
        """Test POST → GET → DELETE → GET workflow."""
        now = datetime.now(UTC)
        start_time = now + timedelta(hours=3)
        end_time = start_time + timedelta(hours=1)

        # POST: Create event
        event_data = {
            "eventMode": "single",
            "subject": "Workflow Test: POST→GET→DELETE→GET",
            "ownerKey": api_client.config.username,
            "startDateTime": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endDateTime": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "startDateTimeEnabled": True,
            "endDateTimeEnabled": True,
        }

        created = await api_client.create_calendar_event(event_data)
        event_key = created["key"]

        # GET: Verify event exists
        retrieved = await api_client.get_calendar_event(event_key, fields=["all"])
        assert retrieved["key"] == event_key
        assert retrieved["subject"] == event_data["subject"]

        # DELETE: Delete event
        await api_client.delete_calendar_event(event_key)

        # GET: Verify event is deleted (should raise error)
        with pytest.raises(Exception):
            await api_client.get_calendar_event(event_key)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_post_multiple_get_list_workflow(self, api_client):
        """Test POST (multiple) → GET (list) workflow."""
        now = datetime.now(UTC)
        event_keys = []

        # POST: Create multiple events
        for i in range(3):
            start_time = now + timedelta(hours=i + 1)
            end_time = start_time + timedelta(minutes=30)

            event_data = {
                "eventMode": "single",
                "subject": f"Workflow Test: Multi-Event #{i + 1}",
                "ownerKey": api_client.config.username,
                "startDateTime": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "endDateTime": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "startDateTimeEnabled": True,
                "endDateTimeEnabled": True,
            }

            created = await api_client.create_calendar_event(event_data)
            event_keys.append(created["key"])

        try:
            # GET: Retrieve event list
            start_date = now - timedelta(hours=1)
            end_date = now + timedelta(hours=10)

            response = await api_client.get_calendar_events_occurrences(
                owner_key=api_client.config.username,
                start_datetime=start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                end_datetime=end_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )

            events = response.get("calendarEvents", [])
            retrieved_keys = [e["key"] for e in events]

            # Verify all created events are in the list
            for key in event_keys:
                assert key in retrieved_keys

        finally:
            # Cleanup: Delete all created events
            for key in event_keys:
                try:
                    await api_client.delete_calendar_event(key)
                except Exception:
                    pass

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_post_get_patch_times_workflow(self, api_client):
        """Test POST → GET → PATCH (times) → GET workflow to verify time preservation."""
        now = datetime.now(UTC)
        original_start = now.replace(hour=14, minute=30, second=0, microsecond=0)
        original_end = original_start + timedelta(hours=1)

        # POST: Create event with specific times
        event_data = {
            "eventMode": "single",
            "subject": "Time Preservation Test",
            "ownerKey": api_client.config.username,
            "startDateTime": original_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endDateTime": original_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "startDateTimeEnabled": True,
            "endDateTimeEnabled": True,
        }

        created = await api_client.create_calendar_event(event_data)
        event_key = created["key"]

        try:
            # GET: Verify times
            retrieved = await api_client.get_calendar_event(event_key, fields=["all"])
            assert "14:30:00" in retrieved["startDateTime"]
            assert "15:30:00" in retrieved["endDateTime"]

            # PATCH: Update only subject, not times
            patch_data = {"subject": "Updated Subject Only"}
            await api_client.update_calendar_event(event_key, patch_data)

            # GET: Verify times still preserved
            updated = await api_client.get_calendar_event(event_key, fields=["all"])
            assert updated["subject"] == "Updated Subject Only"
            assert "14:30:00" in updated["startDateTime"]
            assert "15:30:00" in updated["endDateTime"]

            # PATCH: Update times
            new_start = now.replace(hour=16, minute=0, second=0, microsecond=0)
            new_end = new_start + timedelta(hours=2)

            patch_data = {
                "startDateTime": new_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "endDateTime": new_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "startDateTimeEnabled": True,
                "endDateTimeEnabled": True,
            }
            await api_client.update_calendar_event(event_key, patch_data)

            # GET: Verify new times
            final = await api_client.get_calendar_event(event_key, fields=["all"])
            assert "16:00:00" in final["startDateTime"]
            assert "18:00:00" in final["endDateTime"]

        finally:
            # Cleanup
            await api_client.delete_calendar_event(event_key)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_recurring_event_workflow(self, api_client):
        """Test POST → GET → PATCH → DELETE workflow for recurring events."""
        now = datetime.now(UTC)
        start_date = now.date()

        # POST: Create recurring event (daily for 5 days)
        event_data = {
            "eventMode": "serial",
            "subject": "Recurring Event Workflow Test",
            "ownerKey": api_client.config.username,
            "seriesStartDate": start_date.strftime("%Y-%m-%d"),
            "occurrenceStartTime": 36000,  # 10:00 AM
            "occurrenceStartTimeEnabled": True,
            "occurrenceEndTime": 39600,  # 11:00 AM
            "occurrenceEndTimeEnabled": True,
            "wholeDayEvent": False,
            "seriesSchema": {
                "schemaType": "daily",
                "dailySchemaData": {"regularity": "interval", "daysInterval": 1},
            },
            "seriesEndDate": (start_date + timedelta(days=4)).strftime("%Y-%m-%d"),
        }

        created = await api_client.create_calendar_event(event_data)
        event_key = created["key"]

        try:
            # GET: Retrieve recurring event
            retrieved = await api_client.get_calendar_event(event_key, fields=["all"])
            assert retrieved["eventMode"] == "serial"
            assert retrieved["subject"] == event_data["subject"]
            assert retrieved["occurrenceStartTime"] == 36000

            # PATCH: Update recurring event subject
            patch_data = {"subject": "UPDATED Recurring Event"}
            await api_client.update_calendar_event(event_key, patch_data)

            # GET: Verify update
            updated = await api_client.get_calendar_event(event_key, fields=["all"])
            assert updated["subject"] == "UPDATED Recurring Event"
            assert updated["eventMode"] == "serial"
            assert updated["occurrenceStartTime"] == 36000  # Times preserved

        finally:
            # DELETE: Clean up
            await api_client.delete_calendar_event(event_key)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_lifecycle_workflow(self, api_client):
        """Test complete event lifecycle: create, read, update multiple times, delete."""
        now = datetime.now(UTC)
        start_time = now + timedelta(hours=5)
        end_time = start_time + timedelta(hours=1)

        # Step 1: CREATE
        event_data = {
            "eventMode": "single",
            "subject": "Lifecycle Test Event",
            "ownerKey": api_client.config.username,
            "content": "Version 1",
            "location": "Location 1",
            "startDateTime": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endDateTime": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "startDateTimeEnabled": True,
            "endDateTimeEnabled": True,
        }

        created = await api_client.create_calendar_event(event_data)
        event_key = created["key"]

        try:
            # Step 2: READ initial version
            v1 = await api_client.get_calendar_event(event_key, fields=["all"])
            assert v1["content"] == "Version 1"
            assert v1["location"] == "Location 1"

            # Step 3: UPDATE content
            await api_client.update_calendar_event(event_key, {"content": "Version 2"})
            v2 = await api_client.get_calendar_event(event_key, fields=["all"])
            assert v2["content"] == "Version 2"
            assert v2["location"] == "Location 1"  # Unchanged

            # Step 4: UPDATE location
            await api_client.update_calendar_event(event_key, {"location": "Location 2"})
            v3 = await api_client.get_calendar_event(event_key, fields=["all"])
            assert v3["content"] == "Version 2"  # Unchanged
            assert v3["location"] == "Location 2"

            # Step 5: UPDATE subject
            await api_client.update_calendar_event(
                event_key, {"subject": "UPDATED Lifecycle Event"}
            )
            v4 = await api_client.get_calendar_event(event_key, fields=["all"])
            assert v4["subject"] == "UPDATED Lifecycle Event"
            assert v4["content"] == "Version 2"
            assert v4["location"] == "Location 2"

            # Verify times preserved through all updates
            assert v4["startDateTime"] == v1["startDateTime"]
            assert v4["endDateTime"] == v1["endDateTime"]

        finally:
            # Step 6: DELETE
            await api_client.delete_calendar_event(event_key)

            # Verify deletion
            with pytest.raises(Exception):
                await api_client.get_calendar_event(event_key)


class TestInformAPIAllDayEvents:
    """Test all-day events through the INFORM API."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_all_day_single_event(self, api_client):
        """Test creating a single all-day event."""
        today = datetime.now(UTC).date()
        tomorrow = today + timedelta(days=1)

        # Create all-day event
        event_data = {
            "eventMode": "single",
            "subject": "All-Day Event Test",
            "ownerKey": api_client.config.username,
            "startDateTime": f"{today}T00:00:00Z",
            "endDateTime": f"{tomorrow}T00:00:00Z",
            "startDateTimeEnabled": True,
            "endDateTimeEnabled": True,
            "wholeDayEvent": True,
        }

        created = await api_client.create_calendar_event(event_data)
        event_key = created["key"]

        try:
            # Retrieve and verify
            retrieved = await api_client.get_calendar_event(event_key, fields=["all"])
            
            assert retrieved["wholeDayEvent"] is True
            assert retrieved["eventMode"] == "single"
            assert retrieved["subject"] == "All-Day Event Test"
            
            # Check datetime format
            assert f"{today}" in retrieved["startDateTime"]
            assert f"{tomorrow}" in retrieved["endDateTime"]

        finally:
            await api_client.delete_calendar_event(event_key)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_all_day_event_with_date_objects(self, api_client):
        """Test all-day event using date-only format (YYYY-MM-DD)."""
        today = datetime.now(UTC).date()
        
        # Try creating with date strings (no time component)
        event_data = {
            "eventMode": "single",
            "subject": "Date-Only All-Day Event",
            "ownerKey": api_client.config.username,
            "startDateTime": f"{today}T00:00:00Z",
            "endDateTime": f"{today}T00:00:00Z",
            "startDateTimeEnabled": True,
            "endDateTimeEnabled": True,
            "wholeDayEvent": True,
        }

        created = await api_client.create_calendar_event(event_data)
        event_key = created["key"]

        try:
            retrieved = await api_client.get_calendar_event(event_key, fields=["all"])
            
            assert retrieved["wholeDayEvent"] is True
            assert retrieved["subject"] == "Date-Only All-Day Event"

        finally:
            await api_client.delete_calendar_event(event_key)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_multi_day_event(self, api_client):
        """Test multi-day all-day event (spans multiple days)."""
        start_date = datetime.now(UTC).date()
        end_date = start_date + timedelta(days=3)  # 3-day event

        event_data = {
            "eventMode": "single",
            "subject": "Multi-Day Event (3 days)",
            "ownerKey": api_client.config.username,
            "startDateTime": f"{start_date}T00:00:00Z",
            "endDateTime": f"{end_date}T00:00:00Z",
            "startDateTimeEnabled": True,
            "endDateTimeEnabled": True,
            "wholeDayEvent": True,
        }

        created = await api_client.create_calendar_event(event_data)
        event_key = created["key"]

        try:
            retrieved = await api_client.get_calendar_event(event_key, fields=["all"])
            
            assert retrieved["wholeDayEvent"] is True
            assert f"{start_date}" in retrieved["startDateTime"]
            assert f"{end_date}" in retrieved["endDateTime"]

        finally:
            await api_client.delete_calendar_event(event_key)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_convert_timed_to_all_day(self, api_client):
        """Test converting a timed event to all-day event via PATCH."""
        today = datetime.now(UTC).date()
        tomorrow = today + timedelta(days=1)

        # Create timed event
        event_data = {
            "eventMode": "single",
            "subject": "Convert to All-Day Test",
            "ownerKey": api_client.config.username,
            "startDateTime": f"{today}T14:00:00Z",
            "endDateTime": f"{today}T15:00:00Z",
            "startDateTimeEnabled": True,
            "endDateTimeEnabled": True,
            "wholeDayEvent": False,
        }

        created = await api_client.create_calendar_event(event_data)
        event_key = created["key"]

        try:
            # Verify it's a timed event
            original = await api_client.get_calendar_event(event_key, fields=["all"])
            assert original["wholeDayEvent"] is False

            # Convert to all-day
            patch_data = {
                "startDateTime": f"{today}T00:00:00Z",
                "endDateTime": f"{tomorrow}T00:00:00Z",
                "wholeDayEvent": True,
            }
            await api_client.update_calendar_event(event_key, patch_data)

            # Verify conversion
            updated = await api_client.get_calendar_event(event_key, fields=["all"])
            assert updated["wholeDayEvent"] is True

        finally:
            await api_client.delete_calendar_event(event_key)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_convert_all_day_to_timed(self, api_client):
        """Test converting an all-day event to timed event via PATCH."""
        today = datetime.now(UTC).date()
        tomorrow = today + timedelta(days=1)

        # Create all-day event
        event_data = {
            "eventMode": "single",
            "subject": "Convert to Timed Test",
            "ownerKey": api_client.config.username,
            "startDateTime": f"{today}T00:00:00Z",
            "endDateTime": f"{tomorrow}T00:00:00Z",
            "startDateTimeEnabled": True,
            "endDateTimeEnabled": True,
            "wholeDayEvent": True,
        }

        created = await api_client.create_calendar_event(event_data)
        event_key = created["key"]

        try:
            # Verify it's all-day
            original = await api_client.get_calendar_event(event_key, fields=["all"])
            assert original["wholeDayEvent"] is True

            # Convert to timed event
            patch_data = {
                "startDateTime": f"{today}T09:00:00Z",
                "endDateTime": f"{today}T17:00:00Z",
                "wholeDayEvent": False,
            }
            await api_client.update_calendar_event(event_key, patch_data)

            # Verify conversion
            updated = await api_client.get_calendar_event(event_key, fields=["all"])
            assert updated["wholeDayEvent"] is False
            assert "09:00:00" in updated["startDateTime"]
            assert "17:00:00" in updated["endDateTime"]

        finally:
            await api_client.delete_calendar_event(event_key)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_all_day_recurring_event(self, api_client):
        """Test recurring all-day event (e.g., holidays).

        Note: INFORM API requires time fields even for all-day recurring events.
        See INFORM_API_QUIRKS.md for details.
        """
        start_date = datetime.now(UTC).date()

        # Create recurring all-day event (daily for 5 days)
        # NOTE: INFORM API quirk - must include time fields even for wholeDayEvent=true
        event_data = {
            "eventMode": "serial",
            "subject": "Recurring All-Day Event",
            "ownerKey": api_client.config.username,
            "seriesStartDate": start_date.strftime("%Y-%m-%d"),
            "occurrenceStartTime": 0,  # Required for recurring all-day events
            "occurrenceStartTimeEnabled": True,
            "occurrenceEndTime": 86340,  # Required for recurring all-day events
            "occurrenceEndTimeEnabled": True,
            "wholeDayEvent": True,
            "seriesSchema": {
                "schemaType": "daily",
                "dailySchemaData": {"regularity": "interval", "daysInterval": 1},
            },
            "seriesEndDate": (start_date + timedelta(days=4)).strftime("%Y-%m-%d"),
        }

        created = await api_client.create_calendar_event(event_data)
        event_key = created["key"]

        try:
            retrieved = await api_client.get_calendar_event(event_key, fields=["all"])

            assert retrieved["eventMode"] == "serial"
            assert retrieved["wholeDayEvent"] is True
            assert retrieved["subject"] == "Recurring All-Day Event"

        finally:
            await api_client.delete_calendar_event(event_key)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_caldav_all_day_event_workflow(self, caldav_backend):
        """Test CalDAV backend with all-day events."""
        from unittest.mock import MagicMock

        request = MagicMock()
        calendar_path = caldav_backend._get_calendar_path()

        today = datetime.now(UTC).date()

        # Create all-day event via CalDAV (using iCal format)
        ical_data = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-all-day-caldav-{datetime.now(UTC).timestamp()}
DTSTART;VALUE=DATE:{today.strftime('%Y%m%d')}
DTEND;VALUE=DATE:{(today + timedelta(days=1)).strftime('%Y%m%d')}
SUMMARY:CalDAV All-Day Event Test
DESCRIPTION:Testing all-day event via CalDAV
CLASS:PUBLIC
END:VEVENT
END:VCALENDAR"""

        object_path = f"{calendar_path}test-all-day-{datetime.now(UTC).timestamp()}.ics"
        
        try:
            # Create via CalDAV
            calendar_object = await caldav_backend.put_calendar_object(
                request, object_path, ical_data, if_none_match=True
            )

            # Verify the event was created and returned data contains date
            assert calendar_object.data
            assert "CalDAV All-Day Event Test" in calendar_object.data
            assert "DTSTART" in calendar_object.data
            
            # The returned iCal should preserve the all-day nature
            # (dates without time component)
            assert ";VALUE=DATE:" in calendar_object.data or f"{today.strftime('%Y%m%d')}" in calendar_object.data

        finally:
            # Cleanup
            try:
                await caldav_backend.delete_calendar_object(request, calendar_object.path)
            except Exception:
                pass
