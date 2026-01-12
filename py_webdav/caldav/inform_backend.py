"""INFORM API-based CalDAV backend implementation.

This backend retrieves calendar events from the INFORM API and exposes them
via CalDAV protocol. Supports full read-write access including create, update,
and delete operations.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import md5
from typing import Any
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr
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
        debug: bool = False,
    ) -> None:
        """Initialize INFORM CalDAV backend.

        Args:
            config: INFORM API configuration (uses default if None)
            home_set_path: Calendar home set path
            principal_path: User principal path
            owner_key: Employee key who owns the calendar (required)
            debug: Enable debug logging of INFORM API requests/responses
        """
        self.api_client = InformAPIClient(config, debug=debug)
        self.home_set_path = home_set_path
        self.principal_path = principal_path
        self.owner_key = owner_key or (config.username if config else "")
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

    def _format_datetime_for_inform(self, dt: datetime) -> str:
        """Format datetime for INFORM API.

        INFORM API requires datetime in format: YYYY-MM-DDTHH:MM:SSZ
        - Must use 'Z' suffix (not +00:00)
        - Must NOT include microseconds

        Args:
            dt: Datetime object (should be UTC)

        Returns:
            Formatted datetime string
        """
        # Ensure datetime is in UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        elif dt.tzinfo != UTC:
            dt = dt.astimezone(UTC)

        # Format without microseconds, with Z suffix
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _occurrence_time_to_utc(
        self, date_str: str, seconds_from_midnight: float
    ) -> datetime:
        """Convert INFORM occurrence time to UTC datetime.

        INFORM API returns occurrenceStartTime/occurrenceEndTime as seconds from
        midnight in the server's LOCAL timezone (not UTC). This method converts
        those times to proper UTC datetimes.

        Args:
            date_str: Date string in ISO format (YYYY-MM-DD)
            seconds_from_midnight: Seconds from midnight in server's local timezone

        Returns:
            UTC datetime object
        """
        # Parse the date
        date = datetime.fromisoformat(date_str).date()

        # Calculate hours and minutes
        hours = int(seconds_from_midnight // 3600)
        minutes = int((seconds_from_midnight % 3600) // 60)
        seconds = int(seconds_from_midnight % 60)

        # Create datetime in server's local timezone
        server_tz = ZoneInfo(self.api_client.config.server_timezone)
        local_dt = datetime.combine(date, datetime.min.time()).replace(
            hour=hours, minute=minutes, second=seconds, tzinfo=server_tz
        )

        # Convert to UTC
        utc_dt = local_dt.astimezone(UTC)

        return utc_dt

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

    def _inform_series_schema_to_rrule(self, series_schema: dict[str, Any]) -> str | None:
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
            byday = ",".join(day_map.get(d, d.upper()[:2]) for d in weekdays)  # type: ignore

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

    def _calculate_first_occurrence(
        self, series_start_dt: datetime, rrule_str: str
    ) -> datetime:
        """Calculate the first occurrence matching the RRULE.

        INFORM's seriesStartDate may not match the first actual occurrence if the
        RRULE has constraints (e.g., BYDAY=MO,TU,WE,TH,FR excludes weekends).
        This method finds the first occurrence that matches the RRULE.

        Args:
            series_start_dt: Series start datetime
            rrule_str: RRULE string (e.g., "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR")

        Returns:
            First occurrence datetime that matches the RRULE
        """
        try:
            # Build RRULE string for dateutil
            dtstart_str = series_start_dt.strftime('%Y%m%dT%H%M%SZ')
            rrule_full = f"DTSTART:{dtstart_str}\nRRULE:{rrule_str}"

            # Parse and get first occurrence
            rule = rrulestr(rrule_full)
            first_occ = rule[0] if rule else series_start_dt

            return first_occ
        except Exception:
            # If parsing fails, fall back to series start date
            return series_start_dt

    def _inform_occurrence_to_ical(self, event_data: dict[str, Any]) -> str:
        """Convert INFORM event occurrence to iCalendar single event.

        Each occurrence is treated as a separate single event (no RRULE).
        Uses the occurrence's startDateTime and endDateTime fields directly.

        Args:
            event_data: Event occurrence data from INFORM API

        Returns:
            iCalendar data as string for a single event
        """
        cal = iCalendar()
        cal.add("prodid", "-//INFORM CalDAV Backend//")
        cal.add("version", "2.0")

        event = iEvent()

        # UID: For occurrences, use key-occurrenceId to make each unique
        event_key = event_data.get("key", "")
        occurrence_id = event_data.get("occurrenceId")
        if occurrence_id:
            uid = f"{event_key}-{occurrence_id}"
        else:
            uid = event_key
        event.add("uid", uid)

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

        # Start and End times
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

        # Reminder/alarm
        reminder_enabled = event_data.get("reminderEnabled", False)
        remind_before = event_data.get("remindBeforeStart", 0)
        if reminder_enabled and remind_before > 0:
            from icalendar import Alarm

            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", subject or "Reminder")
            alarm.add("trigger", timedelta(seconds=-remind_before))
            event.add_component(alarm)

        # Privacy
        is_private = event_data.get("private", False)
        if is_private:
            event.add("class", "PRIVATE")
        else:
            event.add("class", "PUBLIC")

        # DTSTAMP (required)
        event.add("dtstamp", datetime.now(UTC))

        cal.add_component(event)
        return cal.to_ical().decode("utf-8")

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

        # Description (content) - will add debug info later
        content = event_data.get("content", "")

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

            # Generate RRULE first (needed to calculate correct first occurrence)
            series_schema = event_data.get("seriesSchema", {})
            rrule_str = self._inform_series_schema_to_rrule(series_schema)

            # Convert series start date + occurrence time to datetime
            if series_start_date_str:
                if whole_day:
                    series_start_date = datetime.fromisoformat(series_start_date_str)
                    # For whole-day events, calculate first occurrence matching RRULE
                    if rrule_str:
                        # Convert to datetime for RRULE calculation
                        series_start_dt = datetime.combine(
                            series_start_date.date(), datetime.min.time()
                        ).replace(tzinfo=UTC)
                        first_occ_dt = self._calculate_first_occurrence(
                            series_start_dt, rrule_str
                        )
                        event.add("dtstart", first_occ_dt.date())
                        event.add("dtend", first_occ_dt.date())
                    else:
                        event.add("dtstart", series_start_date.date())
                        event.add("dtend", series_start_date.date())
                else:
                    # Convert occurrence times from server local timezone to UTC
                    start_dt = self._occurrence_time_to_utc(
                        series_start_date_str, occ_start_time
                    )
                    end_dt = self._occurrence_time_to_utc(
                        series_start_date_str, occ_end_time
                    )

                    # Calculate first occurrence matching RRULE
                    if rrule_str:
                        first_occ_dt = self._calculate_first_occurrence(start_dt, rrule_str)
                        # Calculate duration to apply to first occurrence
                        duration = end_dt - start_dt
                        first_occ_end = first_occ_dt + duration

                        event.add("dtstart", first_occ_dt)
                        event.add("dtend", first_occ_end)
                    else:
                        event.add("dtstart", start_dt)
                        event.add("dtend", end_dt)

            # Add recurrence rule
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

        # Add description with debug information
        event_key = event_data.get("key", "")
        event_mode = event_data.get("eventMode", "single")
        series_schema = event_data.get("seriesSchema", {})

        debug_lines = []
        debug_lines.append(f"[DEBUG] Event ID: {event_key}")
        debug_lines.append(f"[DEBUG] Event Mode: {event_mode}")

        if event_mode == "serial" and series_schema:
            import json

            debug_lines.append(f"[DEBUG] Series Schema: {json.dumps(series_schema)}")
            debug_lines.append(f"[DEBUG] Series Start: {event_data.get('seriesStartDate', 'N/A')}")
            debug_lines.append(f"[DEBUG] Series End: {event_data.get('seriesEndDate', 'N/A')}")

            # Add the generated RRULE string (convert vRecur object to string if present)
            if "rrule" in event:
                rrule_value = event.get("rrule")
                # Convert vRecur to clean string format
                if hasattr(rrule_value, 'to_ical'):
                    rrule_str_debug = rrule_value.to_ical().decode('utf-8')
                else:
                    rrule_str_debug = str(rrule_value)
                debug_lines.append(f"[DEBUG] Generated RRULE: {rrule_str_debug}")

        # Combine original content with debug info
        if content:
            full_description = content + "\n\n" + "\n".join(debug_lines)
        else:
            full_description = "\n".join(debug_lines)

        event.add("description", full_description)

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
                event_data["startDateTime"] = self._format_datetime_for_inform(dtstart)
                event_data["wholeDayEvent"] = False
                event_data["startDateTimeEnabled"] = True
            else:
                # Convert date to datetime
                dt = datetime.combine(dtstart, datetime.min.time()).replace(tzinfo=UTC)
                event_data["startDateTime"] = self._format_datetime_for_inform(dt)
                event_data["wholeDayEvent"] = True
                event_data["startDateTimeEnabled"] = True

            # Parse DTEND
            if "dtend" in event:
                dtend = event.get("dtend").dt
                if isinstance(dtend, datetime):
                    event_data["endDateTime"] = self._format_datetime_for_inform(dtend)
                    event_data["endDateTimeEnabled"] = True
                else:
                    dt = datetime.combine(dtend, datetime.min.time()).replace(tzinfo=UTC)
                    event_data["endDateTime"] = self._format_datetime_for_inform(dt)
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
        """Get a calendar object (event).

        Handles both single events and occurrences of series events.
        Path format: key.ics or key-occurrenceId.ics
        """
        path_str = self._parse_object_path(path)

        # Check if this is an occurrence (contains hyphen before .ics)
        if "-" in path_str:
            parts = path_str.rsplit("-", 1)
            event_key = parts[0]
            occurrence_id = parts[1] if len(parts) > 1 else None
        else:
            event_key = path_str
            occurrence_id = None

        if occurrence_id:
            # Fetch the specific occurrence
            # We need to query occurrences to get the occurrence data
            # Use a date range that should include this occurrence
            start_date = datetime.now(UTC) - timedelta(days=365)
            end_date = datetime.now(UTC) + timedelta(days=365)

            response = await self.api_client.get_calendar_events_occurrences(
                owner_key=self.owner_key,
                start_datetime=self._format_datetime_for_inform(start_date),
                end_datetime=self._format_datetime_for_inform(end_date),
                limit=1000,
            )

            events = response.get("calendarEvents", [])
            event_data = None

            # Find the specific occurrence
            for evt in events:
                if evt.get("key") == event_key and evt.get("occurrenceId") == occurrence_id:
                    event_data = evt
                    break

            if not event_data:
                raise HTTPError(404, Exception(f"Occurrence not found: {event_key}-{occurrence_id}"))

            # Convert occurrence to iCalendar
            ical_data = self._inform_occurrence_to_ical(event_data)
        else:
            # Fetch single event
            try:
                event_data = await self.api_client.get_calendar_event(event_key, fields=["all"])
            except Exception as e:
                raise HTTPError(404, Exception(f"Event not found: {event_key}")) from e

            # Convert to iCalendar (treat as single occurrence)
            ical_data = self._inform_occurrence_to_ical(event_data)

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
        """List all calendar objects in the calendar.

        Each occurrence is returned as a separate CalDAV object.
        """
        # Get sync date range
        start_date, end_date = self._get_sync_date_range()

        # Fetch events from INFORM API
        response = await self.api_client.get_calendar_events_occurrences(
            owner_key=self.owner_key,
            start_datetime=self._format_datetime_for_inform(start_date),
            end_datetime=self._format_datetime_for_inform(end_date),
            limit=1000,
        )

        events = response.get("calendarEvents", [])
        objects = []

        for event_data in events:
            event_key = event_data.get("key", "")
            if not event_key:
                continue

            occurrence_id = event_data.get("occurrenceId")

            try:
                # Convert occurrence to single event iCalendar
                ical_data = self._inform_occurrence_to_ical(event_data)

                # Generate ETag
                etag = md5(ical_data.encode()).hexdigest()

                # Create unique object path
                # For occurrences: key-occurrenceId.ics
                # For single events: key.ics
                if occurrence_id:
                    object_path = f"{calendar_path}{event_key}-{occurrence_id}.ics"
                else:
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

        Each occurrence is returned as a separate CalDAV object.
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
            start_datetime=self._format_datetime_for_inform(start_date),
            end_datetime=self._format_datetime_for_inform(end_date),
            limit=1000,
        )

        events = response.get("calendarEvents", [])
        objects = []

        for event_data in events:
            event_key = event_data.get("key", "")
            if not event_key:
                continue

            occurrence_id = event_data.get("occurrenceId")

            try:
                # Convert occurrence to single event iCalendar
                ical_data = self._inform_occurrence_to_ical(event_data)
                etag = md5(ical_data.encode()).hexdigest()

                # Create unique object path
                if occurrence_id:
                    object_path = f"{calendar_path}{event_key}-{occurrence_id}.ics"
                else:
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
        """Create or update a calendar object.

        Note: Updating individual occurrences is not supported.
        Only single events can be created or updated.
        """
        path_str = self._parse_object_path(path)

        # Check if this is an occurrence (contains hyphen)
        if "-" in path_str:
            # Updating individual occurrences not supported
            raise HTTPError(
                405,
                Exception(
                    "Modifying individual occurrences is not supported. "
                    "Create a new event or modify the entire series."
                ),
            )

        event_key = path_str

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
                _updated_event = await self.api_client.update_calendar_event(event_key, event_data)
            else:
                # Create new event
                # Note: INFORM API auto-generates keys, so we can't use the path key
                # We'll create the event and let INFORM assign the key
                created_event = await self.api_client.create_calendar_event(event_data)
                event_key = created_event.get("key", event_key)

            # Fetch the created/updated event to get complete data
            final_event = await self.api_client.get_calendar_event(event_key, fields=["all"])

            # Convert back to iCalendar (as single occurrence)
            result_ical = self._inform_occurrence_to_ical(final_event)
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
        """Delete a calendar object.

        Note: Deleting individual occurrences is not supported.
        Only single events can be deleted.
        """
        path_str = self._parse_object_path(path)

        # Check if this is an occurrence (contains hyphen)
        if "-" in path_str:
            # Deleting individual occurrences not supported
            raise HTTPError(
                405,
                Exception(
                    "Deleting individual occurrences is not supported. "
                    "Delete the entire series or modify it to exclude this occurrence."
                ),
            )

        event_key = path_str

        try:
            await self.api_client.delete_calendar_event(event_key)
        except Exception as e:
            raise HTTPError(404, Exception(f"Event not found: {event_key}")) from e
