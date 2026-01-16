"""Shared utilities for converting INFORM events to iCalendar format.

This module provides conversion logic that can be used by both CalDAV backend
and ICS feed endpoint. All INFORM API quirks are handled here including:
- Timezone conversion from server local time to UTC
- RRULE generation from INFORM series schemas
- First occurrence calculation for day-of-week constraints
- Single vs recurring event handling
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr
from icalendar import Alarm
from icalendar import Calendar as iCalendar
from icalendar import Event as iEvent


class InformCalendarConverter:
    """Shared utilities for converting INFORM events to iCalendar format.

    This converter handles all the quirks of the INFORM API including:
    - Occurrence times in server's local timezone (not UTC)
    - Series start date vs first actual occurrence mismatch
    - Complex RRULE generation from INFORM series schemas

    Can be used by both CalDAV backend and ICS feed endpoint.
    """

    def __init__(self, server_timezone: str = "Europe/Berlin") -> None:
        """Initialize INFORM calendar converter.

        Args:
            server_timezone: INFORM server's local timezone for time conversion
                           (default: Europe/Berlin)
        """
        self.server_timezone = server_timezone

    def get_sync_date_range(self, weeks: int = 2) -> tuple[datetime, datetime]:
        """Get date range for syncing events (N weeks before/after current date).

        Args:
            weeks: Number of weeks before and after current date (default: 2)

        Returns:
            Tuple of (start_date, end_date) in UTC
        """
        now = datetime.now(UTC)
        start = now - timedelta(weeks=weeks)
        end = now + timedelta(weeks=weeks)
        return start, end

    def format_datetime_for_inform(self, dt: datetime) -> str:
        """Format datetime for INFORM API.

        INFORM API requires datetime in format: YYYY-MM-DDTHH:MM:SSZ
        - Must use 'Z' suffix (not +00:00)
        - Must NOT include microseconds

        Args:
            dt: Datetime object (should be UTC)

        Returns:
            Formatted datetime string (e.g., "2026-01-13T14:30:00Z")
        """
        # Ensure datetime is in UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        elif dt.tzinfo != UTC:
            dt = dt.astimezone(UTC)

        # Format without microseconds, with Z suffix
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def occurrence_time_to_utc(self, date_str: str, seconds_from_midnight: float) -> datetime:
        """Convert INFORM occurrence time to UTC datetime.

        INFORM API returns occurrenceStartTime/occurrenceEndTime as seconds from
        midnight in the server's LOCAL timezone (not UTC). This is a major quirk
        documented in INFORM_API_QUIRKS.md.

        Args:
            date_str: Date string in ISO format (YYYY-MM-DD)
            seconds_from_midnight: Seconds from midnight in server's local timezone

        Returns:
            UTC datetime object

        Example:
            >>> converter = InformCalendarConverter("Europe/Berlin")
            >>> # 14:00 in Berlin time on 2026-01-13
            >>> dt = converter.occurrence_time_to_utc("2026-01-13", 50400)
            >>> # Returns 2026-01-13 13:00:00 UTC (during CET, UTC+1)
        """
        # Parse the date
        date = datetime.fromisoformat(date_str).date()

        # Calculate hours, minutes, seconds
        hours = int(seconds_from_midnight // 3600)
        minutes = int((seconds_from_midnight % 3600) // 60)
        seconds = int(seconds_from_midnight % 60)

        # Create datetime in server's local timezone
        server_tz = ZoneInfo(self.server_timezone)
        local_dt = datetime.combine(date, datetime.min.time()).replace(
            hour=hours, minute=minutes, second=seconds, tzinfo=server_tz
        )

        # Convert to UTC
        utc_dt = local_dt.astimezone(UTC)

        return utc_dt

    def inform_series_schema_to_rrule(self, series_schema: dict[str, Any]) -> str | None:
        """Convert INFORM seriesSchema to iCalendar RRULE.

        Handles all INFORM recurrence patterns:
        - Daily: allBusinessDays, interval
        - Weekly: specific weekdays with interval
        - Monthly: specific date or specific day (e.g., first Monday)
        - Yearly: specific date or specific day in month
        - Arrhythmic: irregular pattern (not supported, returns None)

        Args:
            series_schema: INFORM series schema data containing schemaType and
                         type-specific data (dailySchemaData, weeklySchemaData, etc.)

        Returns:
            RRULE string (e.g., "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR") or None if
            not a recurring event or unsupported pattern

        Example:
            >>> schema = {
            ...     "schemaType": "weekly",
            ...     "weeklySchemaData": {
            ...         "weekdays": ["monday", "wednesday", "friday"],
            ...         "weeksInterval": 1
            ...     }
            ... }
            >>> converter.inform_series_schema_to_rrule(schema)
            'FREQ=WEEKLY;BYDAY=MO,WE,FR'
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
                # Specific day of month (e.g., 15th)
                day = monthly_data.get("dayOfMonth", 1)
                interval = monthly_data.get("monthsInterval", 1)
                if interval == 1:
                    return f"FREQ=MONTHLY;BYMONTHDAY={day}"
                else:
                    return f"FREQ=MONTHLY;INTERVAL={interval};BYMONTHDAY={day}"

            elif regularity == "specificDay":
                # Specific weekday (e.g., first Monday, third Friday)
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
                # Specific date (month + day, e.g., December 25th)
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

    def calculate_first_occurrence(self, series_start_dt: datetime, rrule_str: str) -> datetime:
        """Calculate the first occurrence matching the RRULE.

        INFORM's seriesStartDate may not match the first actual occurrence if the
        RRULE has constraints. For example, if seriesStartDate is Saturday but the
        RRULE specifies BYDAY=MO,TU,WE,TH,FR (business days only), the first actual
        occurrence should be the following Monday.

        This is a critical quirk documented in INFORM_API_QUIRKS.md and
        EVENT_KEY_HANDLING.md.

        Args:
            series_start_dt: Series start datetime from INFORM API
            rrule_str: RRULE string (e.g., "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR")

        Returns:
            First occurrence datetime that matches the RRULE constraints

        Example:
            >>> # Series starts on Saturday 2026-01-10
            >>> start = datetime(2026, 1, 10, 14, 0, tzinfo=UTC)
            >>> rrule = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
            >>> converter.calculate_first_occurrence(start, rrule)
            datetime(2026, 1, 12, 14, 0, tzinfo=UTC)  # Monday
        """
        try:
            # Build RRULE string for dateutil
            dtstart_str = series_start_dt.strftime("%Y%m%dT%H%M%SZ")
            rrule_full = f"DTSTART:{dtstart_str}\nRRULE:{rrule_str}"

            # Parse and get first occurrence
            rule = rrulestr(rrule_full)
            first_occ = rule[0] if rule else series_start_dt

            return first_occ
        except Exception:
            # If parsing fails, fall back to series start date
            return series_start_dt

    def inform_event_to_ical(self, event_data: dict[str, Any]) -> str:
        """Convert INFORM calendar event to iCalendar format.

        Handles both single and recurring (serial) events. For recurring events,
        generates proper RRULE strings and calculates the correct first occurrence
        when the series start date doesn't match RRULE constraints.

        Args:
            event_data: Event data from INFORM API containing:
                - key: Event unique identifier (used as UID)
                - subject: Event title
                - content: Event description
                - location: Event location
                - eventCategory: Event category
                - eventMode: "single" or "serial" (recurring)
                - occurrenceId: If present, treat as single event occurrence
                - startDateTime/endDateTime: For single events
                - seriesStartDate/seriesEndDate: For recurring events
                - seriesSchema: Recurrence pattern definition
                - occurrenceStartTime/occurrenceEndTime: Times in server timezone
                - wholeDayEvent: Boolean flag for all-day events
                - private: Privacy flag
                - reminderEnabled/remindBeforeStart: Alarm settings

        Returns:
            Complete iCalendar string (BEGIN:VCALENDAR...END:VCALENDAR)
            containing a single VEVENT component

        Example:
            >>> event = {
            ...     "key": "12345",
            ...     "subject": "Team Meeting",
            ...     "eventMode": "single",
            ...     "startDateTime": "2026-01-13T14:00:00Z",
            ...     "endDateTime": "2026-01-13T15:00:00Z"
            ... }
            >>> ical = converter.inform_event_to_ical(event)
            >>> "BEGIN:VCALENDAR" in ical
            True
        """
        cal = iCalendar()
        cal.add("prodid", "-//INFORM CalDAV Backend//")
        cal.add("version", "2.0")

        event = iEvent()

        # Required: UID
        # For occurrences, append occurrenceId to make UID unique
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
        # If event has occurrenceId, treat it as a single event with its occurrence times
        event_mode = event_data.get("eventMode", "single")
        is_occurrence = bool(event_data.get("occurrenceId"))

        if event_mode == "single" or is_occurrence:
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
            rrule_str = self.inform_series_schema_to_rrule(series_schema)

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
                        first_occ_dt = self.calculate_first_occurrence(series_start_dt, rrule_str)
                        event.add("dtstart", first_occ_dt.date())
                        event.add("dtend", first_occ_dt.date())
                    else:
                        event.add("dtstart", series_start_date.date())
                        event.add("dtend", series_start_date.date())
                else:
                    # Convert occurrence times from server local timezone to UTC
                    start_dt = self.occurrence_time_to_utc(series_start_date_str, occ_start_time)
                    end_dt = self.occurrence_time_to_utc(series_start_date_str, occ_end_time)

                    # Calculate first occurrence matching RRULE
                    if rrule_str:
                        first_occ_dt = self.calculate_first_occurrence(start_dt, rrule_str)
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

        # Add description from event content
        if content:
            event.add("description", content)

        # Last modified (use current time)
        event.add("dtstamp", datetime.now(UTC))

        cal.add_component(event)
        ical_str: str = cal.to_ical().decode("utf-8")
        return ical_str
