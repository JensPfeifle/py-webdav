"""INFORM API-based CalDAV backend implementation.

This backend retrieves calendar events from the INFORM API and exposes them
via CalDAV protocol. Supports full read-write access including create, update,
and delete operations.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import md5
from typing import Any

from icalendar import Calendar as iCalendar
from icalendar import Event as iEvent
from starlette.requests import Request

from ..inform_api_client import InformAPIClient, InformConfig
from ..internal import HTTPError
from .caldav import Calendar, CalendarCompRequest, CalendarObject, CalendarQuery


class InformCalDAVBackend:
    """INFORM API-based CalDAV backend.

    This backend supports full read-write access to calendar events.
    Events are synced within a 2-week window (before and after current date).
    """

    def __init__(
        self,
        config: InformConfig | None = None,
        home_set_path: str = "/calendars/",
        principal_path: str = "/principals/current/",
        owner_key: str | None = None,
    ) -> None:
        """Initialize INFORM CalDAV backend.

        Args:
            config: INFORM API configuration (uses default if None)
            home_set_path: Calendar home set path
            principal_path: User principal path
            owner_key: Employee key who owns the calendar (required)
        """
        self.api_client = InformAPIClient(config)
        self.home_set_path = home_set_path
        self.principal_path = principal_path
        self.owner_key = owner_key or (config.username if config else None)
        self._sync_weeks = 2  # Sync 2 weeks before/after current date

    async def calendar_home_set_path(self, request: Request) -> str:
        """Get calendar home set path."""
        return self.home_set_path

    async def current_user_principal(self, request: Request) -> str:
        """Get current user principal path."""
        return self.principal_path

    def _get_calendar_path(self) -> str:
        """Get path for the calendar."""
        return f"{self.home_set_path}default/"

    def _get_sync_date_range(self) -> tuple[datetime, datetime]:
        """Get date range for syncing events (2 weeks before/after current date).

        Returns:
            Tuple of (start_date, end_date)
        """
        now = datetime.now(UTC)
        start = now - timedelta(weeks=self._sync_weeks)
        end = now + timedelta(weeks=self._sync_weeks)
        return start, end

    def _parse_object_path(self, path: str) -> str:
        """Parse object path to extract event key.

        Args:
            path: Object path (e.g., "/calendars/default/event123.ics")

        Returns:
            Event key

        Raises:
            HTTPError: If path is invalid
        """
        parts = [p for p in path.split("/") if p and p not in ["calendars", "default"]]
        if not parts:
            raise HTTPError(404, Exception(f"Invalid object path: {path}"))

        # Remove .ics extension if present
        event_key = parts[0]
        if event_key.endswith(".ics"):
            event_key = event_key[:-4]

        return event_key

    def _inform_series_schema_to_rrule(
        self, series_schema: dict[str, Any]
    ) -> str | None:
        """Convert INFORM seriesSchema to iCalendar RRULE.

        Args:
            series_schema: INFORM series schema data

        Returns:
            RRULE string or None if not a recurring event
        """
        schema_type = series_schema.get("schemaType")

        if schema_type == "daily":
            daily_data = series_schema.get("dailySchemaData", {})
            regularity = daily_data.get("regularity")

            if regularity == "allBusinessDays":
                # Every business day (Mon-Fri)
                return "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
            elif regularity == "interval":
                # Every N days
                interval = daily_data.get("daysInterval", 1)
                return f"FREQ=DAILY;INTERVAL={interval}"

        elif schema_type == "weekly":
            weekly_data = series_schema.get("weeklySchemaData", {})
            weekdays = weekly_data.get("weekdays", [])
            interval = weekly_data.get("weeksInterval", 1)

            # Convert weekday names to iCal format
            day_map = {
                "monday": "MO",
                "tuesday": "TU",
                "wednesday": "WE",
                "thursday": "TH",
                "friday": "FR",
                "saturday": "SA",
                "sunday": "SU",
            }
            byday = ",".join(day_map.get(d, d.upper()[:2]) for d in weekdays)

            if interval == 1:
                return f"FREQ=WEEKLY;BYDAY={byday}"
            else:
                return f"FREQ=WEEKLY;INTERVAL={interval};BYDAY={byday}"

        elif schema_type == "monthly":
            monthly_data = series_schema.get("monthlySchemaData", {})
            regularity = monthly_data.get("regularity")

            if regularity == "specificDate":
                # Specific day of month
                day = monthly_data.get("dayOfMonth", 1)
                interval = monthly_data.get("monthsInterval", 1)
                if interval == 1:
                    return f"FREQ=MONTHLY;BYMONTHDAY={day}"
                else:
                    return f"FREQ=MONTHLY;INTERVAL={interval};BYMONTHDAY={day}"

            elif regularity == "specificDay":
                # Specific weekday (e.g., first Monday)
                weekday = monthly_data.get("weekday", "monday")
                week_number = monthly_data.get("weekNumber", 1)
                interval = monthly_data.get("monthsInterval", 1)

                day_map = {
                    "monday": "MO",
                    "tuesday": "TU",
                    "wednesday": "WE",
                    "thursday": "TH",
                    "friday": "FR",
                    "saturday": "SA",
                    "sunday": "SU",
                }
                byday = f"{week_number}{day_map.get(weekday, 'MO')}"

                if interval == 1:
                    return f"FREQ=MONTHLY;BYDAY={byday}"
                else:
                    return f"FREQ=MONTHLY;INTERVAL={interval};BYDAY={byday}"

        elif schema_type == "yearly":
            yearly_data = series_schema.get("yearlySchemaData", {})
            regularity = yearly_data.get("regularity")

            if regularity == "specificDate":
                # Specific date (month + day)
                month = yearly_data.get("monthOfYear", 1)
                day = yearly_data.get("dayOfMonth", 1)
                return f"FREQ=YEARLY;BYMONTH={month};BYMONTHDAY={day}"

            elif regularity == "specificDay":
                # Specific weekday in month (e.g., first Monday of June)
                month = yearly_data.get("monthOfYear", 1)
                weekday = yearly_data.get("weekday", "monday")
                week_number = yearly_data.get("weekNumber", 1)

                day_map = {
                    "monday": "MO",
                    "tuesday": "TU",
                    "wednesday": "WE",
                    "thursday": "TH",
                    "friday": "FR",
                    "saturday": "SA",
                    "sunday": "SU",
                }
                byday = f"{week_number}{day_map.get(weekday, 'MO')}"
                return f"FREQ=YEARLY;BYMONTH={month};BYDAY={byday}"

        elif schema_type == "arrhythmic":
            # Arrhythmic events don't have a regular recurrence pattern
            # They're defined by explicit occurrence dates
            # Not supported by RRULE, so return None
            return None

        return None

    def _inform_event_to_ical(self, event_data: dict[str, Any]) -> str:
        """Convert INFORM calendar event to iCalendar format.

        Args:
            event_data: Event data from INFORM API

        Returns:
            iCalendar data as string
        """
        cal = iCalendar()
        cal.add("prodid", "-//INFORM CalDAV Backend//")
        cal.add("version", "2.0")

        event = iEvent()

        # Required: UID
        event_key = event_data.get("key", "")
        event.add("uid", event_key)

        # Summary (subject)
        subject = event_data.get("subject", "")
        if subject:
            event.add("summary", subject)

        # Description (content)
        content = event_data.get("content", "")
        if content:
            event.add("description", content)

        # Location
        location = event_data.get("location", "")
        if location:
            event.add("location", location)

        # Categories
        category = event_data.get("eventCategory", "")
        if category:
            event.add("categories", [category])

        # Event mode determines if single or recurring
        event_mode = event_data.get("eventMode", "single")

        if event_mode == "single":
            # Single event
            start_dt_str = event_data.get("startDateTime")
            end_dt_str = event_data.get("endDateTime")
            whole_day = event_data.get("wholeDayEvent", False)

            if start_dt_str:
                start_dt = datetime.fromisoformat(start_dt_str.replace("Z", "+00:00"))
                if whole_day:
                    event.add("dtstart", start_dt.date())
                else:
                    event.add("dtstart", start_dt)

            if end_dt_str:
                end_dt = datetime.fromisoformat(end_dt_str.replace("Z", "+00:00"))
                if whole_day:
                    event.add("dtend", end_dt.date())
                else:
                    event.add("dtend", end_dt)

        elif event_mode == "serial":
            # Recurring event
            series_start_date_str = event_data.get("seriesStartDate")
            series_end_date_str = event_data.get("seriesEndDate")
            occ_start_time = event_data.get("occurrenceStartTime", 0)
            occ_end_time = event_data.get("occurrenceEndTime", 0)
            whole_day = event_data.get("wholeDayEvent", False)

            # Convert series start date + occurrence time to datetime
            if series_start_date_str:
                series_start_date = datetime.fromisoformat(series_start_date_str)
                hours = int(occ_start_time // 3600)
                minutes = int((occ_start_time % 3600) // 60)

                if whole_day:
                    event.add("dtstart", series_start_date.date())
                else:
                    start_dt = series_start_date.replace(
                        hour=hours, minute=minutes, tzinfo=UTC
                    )
                    event.add("dtstart", start_dt)

                # Calculate end time for recurring events
                # Duration for reference (currently unused)
                _duration_secs = occ_end_time - occ_start_time
                if not whole_day:
                    end_hours = int(occ_end_time // 3600)
                    end_minutes = int((occ_end_time % 3600) // 60)
                    end_dt = series_start_date.replace(
                        hour=end_hours, minute=end_minutes, tzinfo=UTC
                    )
                    event.add("dtend", end_dt)
                else:
                    # For all-day events, use date
                    event.add("dtend", series_start_date.date())

            # Add recurrence rule
            series_schema = event_data.get("seriesSchema", {})
            rrule_str = self._inform_series_schema_to_rrule(series_schema)
            if rrule_str:
                event.add("rrule", rrule_str)

            # Add UNTIL if series has end date
            if series_end_date_str and rrule_str:
                series_end_date = datetime.fromisoformat(series_end_date_str)
                # Update RRULE to include UNTIL
                until_str = series_end_date.strftime("%Y%m%dT235959Z")
                if ";UNTIL=" not in rrule_str:
                    rrule_str = f"{rrule_str};UNTIL={until_str}"
                    event["rrule"] = rrule_str

        # Reminder/alarm
        reminder_enabled = event_data.get("reminderEnabled", False)
        remind_before = event_data.get("remindBeforeStart", 0)
        if reminder_enabled and remind_before > 0:
            from icalendar import Alarm

            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", subject or "Reminder")
            # Convert seconds to negative duration
            alarm.add("trigger", timedelta(seconds=-remind_before))
            event.add_component(alarm)

        # Privacy
        is_private = event_data.get("private", False)
        if is_private:
            event.add("class", "PRIVATE")
        else:
            event.add("class", "PUBLIC")

        # Last modified (use current time)
        event.add("dtstamp", datetime.now(UTC))

        cal.add_component(event)
        ical_str: str = cal.to_ical().decode("utf-8")
        return ical_str

    def _ical_to_inform_event(self, ical_data: str) -> dict[str, Any]:
        """Convert iCalendar data to INFORM calendar event format.

        Args:
            ical_data: iCalendar data as string

        Returns:
            INFORM event data dictionary
        """
        cal = iCalendar.from_ical(ical_data)

        # Find the VEVENT component
        event = None
        for component in cal.walk():
            if component.name == "VEVENT":
                event = component
                break

        if not event:
            raise ValueError("No VEVENT found in iCalendar data")

        event_data: dict[str, Any] = {}

        # Subject (summary)
        if "summary" in event:
            event_data["subject"] = str(event["summary"])

        # Content (description)
        if "description" in event:
            event_data["content"] = str(event["description"])

        # Location
        if "location" in event:
            event_data["location"] = str(event["location"])

        # Category
        if "categories" in event:
            categories = event["categories"]
            if isinstance(categories, list) and categories:
                event_data["eventCategory"] = str(categories[0])

        # Privacy
        if "class" in event:
            event_class = str(event["class"]).upper()
            event_data["private"] = event_class == "PRIVATE"

        # Check if recurring event
        has_rrule = "rrule" in event

        if has_rrule:
            # Serial/recurring event
            event_data["eventMode"] = "serial"

            # Parse DTSTART
            dtstart = event.get("dtstart").dt
            if isinstance(dtstart, datetime):
                event_data["seriesStartDate"] = dtstart.strftime("%Y-%m-%d")
                # Extract time in seconds from midnight
                seconds = dtstart.hour * 3600 + dtstart.minute * 60
                event_data["occurrenceStartTime"] = seconds
                event_data["occurrenceStartTimeEnabled"] = True
                event_data["wholeDayEvent"] = False
            else:
                # Date only (all-day event)
                event_data["seriesStartDate"] = dtstart.isoformat()
                event_data["occurrenceStartTime"] = 0
                event_data["occurrenceStartTimeEnabled"] = True
                event_data["wholeDayEvent"] = True

            # Parse DTEND or duration
            if "dtend" in event:
                dtend = event.get("dtend").dt
                if isinstance(dtend, datetime):
                    seconds = dtend.hour * 3600 + dtend.minute * 60
                    event_data["occurrenceEndTime"] = seconds
                    event_data["occurrenceEndTimeEnabled"] = True
                else:
                    event_data["occurrenceEndTime"] = 86340  # End of day
                    event_data["occurrenceEndTimeEnabled"] = True

            # Parse RRULE
            rrule = event.get("rrule")
            series_schema = self._rrule_to_inform_series_schema(rrule)
            event_data["seriesSchema"] = series_schema

            # Parse UNTIL for series end date
            if "until" in rrule:
                until = rrule["until"][0]
                if isinstance(until, datetime):
                    event_data["seriesEndDate"] = until.strftime("%Y-%m-%d")
                else:
                    event_data["seriesEndDate"] = until.isoformat()

        else:
            # Single event
            event_data["eventMode"] = "single"

            # Parse DTSTART
            dtstart = event.get("dtstart").dt
            if isinstance(dtstart, datetime):
                event_data["startDateTime"] = dtstart.isoformat()
                event_data["wholeDayEvent"] = False
                event_data["startDateTimeEnabled"] = True
            else:
                # Convert date to datetime
                dt = datetime.combine(dtstart, datetime.min.time()).replace(tzinfo=UTC)
                event_data["startDateTime"] = dt.isoformat()
                event_data["wholeDayEvent"] = True
                event_data["startDateTimeEnabled"] = True

            # Parse DTEND
            if "dtend" in event:
                dtend = event.get("dtend").dt
                if isinstance(dtend, datetime):
                    event_data["endDateTime"] = dtend.isoformat()
                    event_data["endDateTimeEnabled"] = True
                else:
                    dt = datetime.combine(dtend, datetime.min.time()).replace(
                        tzinfo=UTC
                    )
                    event_data["endDateTime"] = dt.isoformat()
                    event_data["endDateTimeEnabled"] = True

        # Parse alarms for reminders
        for component in event.walk():
            if component.name == "VALARM":
                trigger = component.get("trigger")
                if trigger:
                    # Convert trigger to seconds
                    if isinstance(trigger.dt, timedelta):
                        remind_before = abs(int(trigger.dt.total_seconds()))
                        event_data["reminderEnabled"] = True
                        event_data["remindBeforeStart"] = remind_before
                    break

        return event_data

    def _rrule_to_inform_series_schema(self, rrule: dict[str, Any]) -> dict[str, Any]:
        """Convert iCalendar RRULE to INFORM seriesSchema.

        Args:
            rrule: RRULE dictionary from icalendar

        Returns:
            INFORM series schema dictionary
        """
        freq = str(rrule.get("freq", ["DAILY"])[0]).upper()
        interval = int(rrule.get("interval", [1])[0])

        if freq == "DAILY":
            byday = rrule.get("byday")
            if byday and set(byday) == {"MO", "TU", "WE", "TH", "FR"}:
                # Business days
                return {
                    "schemaType": "daily",
                    "dailySchemaData": {"regularity": "allBusinessDays"},
                }
            else:
                # Every N days
                return {
                    "schemaType": "daily",
                    "dailySchemaData": {
                        "regularity": "interval",
                        "daysInterval": interval,
                    },
                }

        elif freq == "WEEKLY":
            byday = rrule.get("byday", [])
            # Convert to INFORM weekday names
            day_map = {
                "MO": "monday",
                "TU": "tuesday",
                "WE": "wednesday",
                "TH": "thursday",
                "FR": "friday",
                "SA": "saturday",
                "SU": "sunday",
            }
            weekdays = [day_map.get(str(d), "monday") for d in byday]

            return {
                "schemaType": "weekly",
                "weeklySchemaData": {
                    "weekdays": weekdays,
                    "weeksInterval": interval,
                },
            }

        elif freq == "MONTHLY":
            bymonthday = rrule.get("bymonthday")
            byday = rrule.get("byday")

            if bymonthday:
                # Specific day of month
                day = int(bymonthday[0])
                return {
                    "schemaType": "monthly",
                    "monthlySchemaData": {
                        "regularity": "specificDate",
                        "dayOfMonth": day,
                        "monthsInterval": interval,
                    },
                }
            elif byday:
                # Specific weekday (e.g., "1MO" = first Monday)
                byday_str = str(byday[0])
                week_number = int(byday_str[0]) if byday_str[0].isdigit() else 1
                weekday_code = byday_str[-2:]

                day_map = {
                    "MO": "monday",
                    "TU": "tuesday",
                    "WE": "wednesday",
                    "TH": "thursday",
                    "FR": "friday",
                    "SA": "saturday",
                    "SU": "sunday",
                }
                weekday = day_map.get(weekday_code, "monday")

                return {
                    "schemaType": "monthly",
                    "monthlySchemaData": {
                        "regularity": "specificDay",
                        "weekday": weekday,
                        "weekNumber": week_number,
                        "monthsInterval": interval,
                    },
                }

        elif freq == "YEARLY":
            bymonth = rrule.get("bymonth")
            bymonthday = rrule.get("bymonthday")
            byday = rrule.get("byday")

            month = int(bymonth[0]) if bymonth else 1

            if bymonthday:
                # Specific date
                day = int(bymonthday[0])
                return {
                    "schemaType": "yearly",
                    "yearlySchemaData": {
                        "regularity": "specificDate",
                        "monthOfYear": month,
                        "dayOfMonth": day,
                    },
                }
            elif byday:
                # Specific weekday
                byday_str = str(byday[0])
                week_number = int(byday_str[0]) if byday_str[0].isdigit() else 1
                weekday_code = byday_str[-2:]

                day_map = {
                    "MO": "monday",
                    "TU": "tuesday",
                    "WE": "wednesday",
                    "TH": "thursday",
                    "FR": "friday",
                    "SA": "saturday",
                    "SU": "sunday",
                }
                weekday = day_map.get(weekday_code, "monday")

                return {
                    "schemaType": "yearly",
                    "yearlySchemaData": {
                        "regularity": "specificDay",
                        "monthOfYear": month,
                        "weekday": weekday,
                        "weekNumber": week_number,
                    },
                }

        # Default to daily
        return {
            "schemaType": "daily",
            "dailySchemaData": {"regularity": "interval", "daysInterval": 1},
        }

    async def list_calendars(self, request: Request) -> list[Calendar]:
        """List all calendars (single default calendar)."""
        calendar = Calendar(
            path=self._get_calendar_path(),
            name="INFORM Calendar",
            description="Calendar synced from INFORM",
            supported_component_set=["VEVENT"],
        )
        return [calendar]

    async def get_calendar(self, request: Request, path: str) -> Calendar:
        """Get calendar by path."""
        if path != self._get_calendar_path():
            raise HTTPError(404, Exception(f"Calendar not found: {path}"))

        return Calendar(
            path=path,
            name="INFORM Calendar",
            description="Calendar synced from INFORM",
            supported_component_set=["VEVENT"],
        )

    async def create_calendar(self, request: Request, calendar: Calendar) -> None:
        """Create calendar (not supported - single calendar only)."""
        raise HTTPError(403, Exception("Creating calendars is not supported"))

    async def delete_calendar(self, request: Request, path: str) -> None:
        """Delete calendar (not supported)."""
        raise HTTPError(403, Exception("Deleting calendars is not supported"))

    async def get_calendar_object(
        self, request: Request, path: str, comp_request: CalendarCompRequest | None = None
    ) -> CalendarObject:
        """Get a calendar object (event)."""
        event_key = self._parse_object_path(path)

        # Fetch event from INFORM API
        try:
            event_data = await self.api_client.get_calendar_event(event_key, fields=["all"])
        except Exception as e:
            raise HTTPError(404, Exception(f"Event not found: {event_key}")) from e

        # Convert to iCalendar
        ical_data = self._inform_event_to_ical(event_data)

        # Generate ETag from content
        etag = md5(ical_data.encode()).hexdigest()

        return CalendarObject(
            path=path,
            data=ical_data,
            mod_time=datetime.now(UTC),
            content_length=len(ical_data.encode()),
            etag=etag,
        )

    async def list_calendar_objects(
        self,
        request: Request,
        calendar_path: str,
        comp_request: CalendarCompRequest | None = None,
    ) -> list[CalendarObject]:
        """List all calendar objects in the calendar."""
        # Get sync date range
        start_date, end_date = self._get_sync_date_range()

        # Fetch events from INFORM API
        response = await self.api_client.get_calendar_events_occurrences(
            owner_key=self.owner_key,
            start_datetime=start_date.isoformat(),
            end_datetime=end_date.isoformat(),
            limit=1000,
        )

        events = response.get("calendarEvents", [])
        objects = []

        for event_data in events:
            event_key = event_data.get("key", "")
            if not event_key:
                continue

            # For occurrences of serial events, we need to fetch the full event
            occurrence_id = event_data.get("occurrenceId")
            if occurrence_id:
                # This is an occurrence of a serial event
                # Fetch the full serial event definition
                try:
                    full_event_data = await self.api_client.get_calendar_event(
                        event_key
                    )
                    event_data = full_event_data
                except Exception:
                    continue

            try:
                # Convert to iCalendar
                ical_data = self._inform_event_to_ical(event_data)

                # Generate ETag
                etag = md5(ical_data.encode()).hexdigest()

                # Create object path
                object_path = f"{calendar_path}{event_key}.ics"

                obj = CalendarObject(
                    path=object_path,
                    data=ical_data,
                    mod_time=datetime.now(UTC),
                    content_length=len(ical_data.encode()),
                    etag=etag,
                )
                objects.append(obj)
            except Exception:
                # Skip invalid events
                continue

        return objects

    async def query_calendar_objects(
        self, request: Request, calendar_path: str, query: CalendarQuery
    ) -> list[CalendarObject]:
        """Query calendar objects with filters.

        Note: Query filters are partially implemented.
        """
        # For now, use the time range filter if available
        # TODO: Implement full filter support

        # Check if query has time range in comp_filter
        start_date = None
        end_date = None

        if query.comp_filter.start:
            start_date = query.comp_filter.start
        if query.comp_filter.end:
            end_date = query.comp_filter.end

        # Use provided time range or default sync range
        if not start_date or not end_date:
            start_date, end_date = self._get_sync_date_range()

        # Fetch events from INFORM API
        response = await self.api_client.get_calendar_events_occurrences(
            owner_key=self.owner_key,
            start_datetime=start_date.isoformat(),
            end_datetime=end_date.isoformat(),
            limit=1000,
        )

        events = response.get("calendarEvents", [])
        objects = []

        # Track unique event keys (avoid duplicates from occurrences)
        seen_keys = set()

        for event_data in events:
            event_key = event_data.get("key", "")
            if not event_key or event_key in seen_keys:
                continue

            seen_keys.add(event_key)

            # For occurrences, fetch full event
            occurrence_id = event_data.get("occurrenceId")
            if occurrence_id:
                try:
                    full_event_data = await self.api_client.get_calendar_event(
                        event_key
                    )
                    event_data = full_event_data
                except Exception:
                    continue

            try:
                ical_data = self._inform_event_to_ical(event_data)
                etag = md5(ical_data.encode()).hexdigest()
                object_path = f"{calendar_path}{event_key}.ics"

                obj = CalendarObject(
                    path=object_path,
                    data=ical_data,
                    mod_time=datetime.now(UTC),
                    content_length=len(ical_data.encode()),
                    etag=etag,
                )
                objects.append(obj)
            except Exception:
                continue

        return objects

    async def put_calendar_object(
        self,
        request: Request,
        path: str,
        ical_data: str,
        if_none_match: bool = False,
        if_match: str | None = None,
    ) -> CalendarObject:
        """Create or update a calendar object."""
        event_key = self._parse_object_path(path)

        # Convert iCalendar to INFORM format
        try:
            event_data = self._ical_to_inform_event(ical_data)
        except Exception as e:
            raise HTTPError(400, Exception(f"Invalid iCalendar data: {e}")) from e

        # Set owner
        event_data["ownerKey"] = self.owner_key

        # Check if event exists
        try:
            _existing_event = await self.api_client.get_calendar_event(event_key)
            event_exists = True
        except Exception:
            event_exists = False

        # Handle preconditions
        if if_none_match and event_exists:
            raise HTTPError(412, Exception("Event already exists"))

        if if_match and not event_exists:
            raise HTTPError(412, Exception("Event does not exist"))

        # Create or update
        try:
            if event_exists:
                # Update existing event
                _updated_event = await self.api_client.update_calendar_event(
                    event_key, event_data
                )
            else:
                # Create new event
                # Note: INFORM API auto-generates keys, so we can't use the path key
                # We'll create the event and let INFORM assign the key
                created_event = await self.api_client.create_calendar_event(event_data)
                event_key = created_event.get("key", event_key)

            # Fetch the created/updated event to get complete data
            final_event = await self.api_client.get_calendar_event(event_key, fields=["all"])

            # Convert back to iCalendar
            result_ical = self._inform_event_to_ical(final_event)
            etag = md5(result_ical.encode()).hexdigest()

            # Update path to use INFORM key as UID (if event was newly created)
            if not event_exists:
                calendar_path = self._get_calendar_path()
                path = f"{calendar_path}{event_key}.ics"

            return CalendarObject(
                path=path,
                data=result_ical,
                mod_time=datetime.now(UTC),
                content_length=len(result_ical.encode()),
                etag=etag,
            )

        except Exception as e:
            raise HTTPError(500, Exception(f"Failed to save event: {e}")) from e

    async def delete_calendar_object(self, request: Request, path: str) -> None:
        """Delete a calendar object."""
        event_key = self._parse_object_path(path)

        try:
            await self.api_client.delete_calendar_event(event_key)
        except Exception as e:
            raise HTTPError(404, Exception(f"Event not found: {event_key}")) from e
