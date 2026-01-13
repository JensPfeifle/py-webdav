"""ICS feed endpoint for calendar subscriptions.

Provides read-only HTTP access to calendar events via .ics URL:
    GET /feed.ics?calendar=OWNER_KEY

Where OWNER_KEY is the employee key (e.g., INFO).

This module provides a simple subscription feed that returns all events
in a single iCalendar file, suitable for calendar clients that don't
support full CalDAV synchronization.
"""

from __future__ import annotations

from typing import Any

from icalendar import Calendar as iCalendar
from starlette.requests import Request
from starlette.responses import Response

from .inform_api_client import InformAPIClient, InformConfig
from .inform_calendar_utils import InformCalendarConverter


class ICSFeedHandler:
    """Handler for ICS feed endpoint.

    Generates a single .ics file containing all events for a calendar owner.
    Events are fetched from the INFORM API and converted to iCalendar format
    using the shared InformCalendarConverter.
    """

    def __init__(
        self,
        config: InformConfig | None = None,
        sync_weeks: int = 2,
        debug: bool = False,
    ) -> None:
        """Initialize ICS feed handler.

        Args:
            config: INFORM API configuration (uses default if None)
            sync_weeks: Number of weeks before/after current date to sync (default: 2)
            debug: Enable debug logging of INFORM API requests/responses
        """
        self.api_client = InformAPIClient(config, debug=debug)
        self.converter = InformCalendarConverter(
            server_timezone=self.api_client.config.server_timezone
        )
        self.sync_weeks = sync_weeks
        self.debug = debug

    async def handle_feed_request(self, request: Request) -> Response:
        """Handle GET /feed.ics?calendar=OWNER_KEY request.

        Process:
        1. Extract calendar parameter (OWNER_KEY) from query string
        2. Fetch events from INFORM API for configured date range
        3. Deduplicate recurring event occurrences (same as CalDAV)
        4. Convert each event to iCalendar format
        5. Combine into single VCALENDAR with multiple VEVENTs
        6. Return as text/calendar response with inline content disposition

        Args:
            request: HTTP request containing calendar query parameter

        Returns:
            Response with Content-Type: text/calendar containing the
            combined iCalendar feed, or error response (400/500)

        Examples:
            GET /feed.ics?calendar=INFO
            Returns: text/calendar with all events for owner "INFO"
        """
        # Extract calendar parameter (OWNER_KEY)
        owner_key = request.query_params.get("calendar")
        if not owner_key:
            return Response(
                content="Missing required 'calendar' parameter. Usage: /feed.ics?calendar=OWNER_KEY",
                status_code=400,
                media_type="text/plain",
            )

        try:
            # Calculate date range for event sync
            start_dt, end_dt = self.converter.get_sync_date_range(weeks=self.sync_weeks)

            # Format datetimes for INFORM API
            start_str = self.converter.format_datetime_for_inform(start_dt)
            end_str = self.converter.format_datetime_for_inform(end_dt)

            if self.debug:
                print(f"[ICS Feed] Fetching events for {owner_key}")
                print(f"[ICS Feed] Date range: {start_str} to {end_str}")

            # Fetch events from INFORM API
            events_response = await self.api_client.get_calendar_events_occurrences(
                owner_key=owner_key,
                start_datetime=start_str,
                end_datetime=end_str,
                limit=1000,
            )

            events = events_response.get("calendarEvents", [])

            if self.debug:
                print(f"[ICS Feed] Received {len(events)} event occurrences")

            # Deduplicate recurring events
            # The occurrences endpoint returns multiple records for series events,
            # but we want one event with RRULE (same as CalDAV)
            seen_keys: set[str] = set()
            unique_events: list[dict[str, Any]] = []

            for event_data in events:
                event_key = event_data.get("key", "")
                if event_key in seen_keys:
                    continue

                seen_keys.add(event_key)

                # Fetch full event if this is an occurrence record
                # Quirk: occurrences endpoint doesn't include seriesSchema
                if event_data.get("occurrenceId"):
                    if self.debug:
                        print(f"[ICS Feed] Fetching full event for key: {event_key}")

                    full_event = await self.api_client.get_calendar_event(event_key, fields=["all"])
                    event_data = full_event

                unique_events.append(event_data)

            if self.debug:
                print(f"[ICS Feed] Deduplicated to {len(unique_events)} unique events")

            # Generate combined iCalendar feed
            ical_content = self._generate_combined_ical(unique_events, owner_key)

            if self.debug:
                print(f"[ICS Feed] Generated {len(ical_content)} bytes of iCalendar data")

            # Return as text/calendar response
            return Response(
                content=ical_content,
                media_type="text/calendar; charset=utf-8",
                headers={
                    "Content-Disposition": f'inline; filename="calendar-{owner_key}.ics"',
                    "Cache-Control": "private, max-age=300",  # Cache for 5 minutes
                },
            )

        except Exception as e:
            # Log error and return 500
            if self.debug:
                import traceback

                print(f"[ICS Feed] Error generating feed: {str(e)}")
                traceback.print_exc()

            return Response(
                content=f"Error generating calendar feed: {str(e)}",
                status_code=500,
                media_type="text/plain",
            )

    def _generate_combined_ical(self, events: list[dict[str, Any]], owner_key: str) -> str:
        """Generate single VCALENDAR with multiple VEVENTs.

        Unlike CalDAV which returns one VCALENDAR per event, the ICS feed
        returns a single VCALENDAR containing all events. This is the standard
        format for calendar subscription feeds.

        Args:
            events: List of INFORM event data dictionaries
            owner_key: Owner key for calendar name

        Returns:
            Combined iCalendar string (BEGIN:VCALENDAR...END:VCALENDAR)
            containing all events as VEVENT components

        Example:
            >>> events = [{"key": "123", "subject": "Meeting", ...}]
            >>> ical = handler._generate_combined_ical(events, "INFO")
            >>> "BEGIN:VCALENDAR" in ical
            True
            >>> "BEGIN:VEVENT" in ical
            True
        """
        # Create main calendar container
        cal = iCalendar()
        cal.add("prodid", "-//INFORM ICS Feed//")
        cal.add("version", "2.0")
        cal.add("calscale", "GREGORIAN")
        cal.add("method", "PUBLISH")
        cal.add("x-wr-calname", f"INFORM Calendar - {owner_key}")
        cal.add("x-wr-caldesc", f"Calendar feed for {owner_key}")

        # Add each event as a VEVENT component
        for event_data in events:
            try:
                # Convert INFORM event to iCalendar (returns full VCALENDAR)
                event_ical_str = self.converter.inform_event_to_ical(event_data)

                # Parse the iCalendar and extract VEVENT component
                event_cal = iCalendar.from_ical(event_ical_str)

                # Find and add the VEVENT component to our combined calendar
                for component in event_cal.walk():
                    if component.name == "VEVENT":
                        cal.add_component(component)
                        break

            except Exception as e:
                # Log error but continue processing other events
                if self.debug:
                    event_key = event_data.get("key", "unknown")
                    print(f"[ICS Feed] Error converting event {event_key}: {str(e)}")
                continue

        return cal.to_ical().decode("utf-8")
