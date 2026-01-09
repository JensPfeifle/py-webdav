"""CalDAV backend interface."""

from __future__ import annotations

from typing import Protocol

from starlette.requests import Request

from .caldav import Calendar, CalendarCompRequest, CalendarObject, CalendarQuery


class CalDAVBackend(Protocol):
    """CalDAV server backend interface.

    Implementations provide storage and retrieval of calendars and calendar objects.
    """

    async def calendar_home_set_path(self, request: Request) -> str:
        """Get the calendar home set path for the current user.

        Args:
            request: HTTP request

        Returns:
            Path to calendar home set (e.g., "/calendars/")
        """
        ...

    async def current_user_principal(self, request: Request) -> str:
        """Get the current user's principal path.

        Args:
            request: HTTP request

        Returns:
            Path to user principal (e.g., "/principals/current/")
        """
        ...

    async def list_calendars(self, request: Request) -> list[Calendar]:
        """List all calendars for the current user.

        Args:
            request: HTTP request

        Returns:
            List of Calendar objects
        """
        ...

    async def get_calendar(self, request: Request, path: str) -> Calendar:
        """Get calendar by path.

        Args:
            request: HTTP request
            path: Calendar path

        Returns:
            Calendar object

        Raises:
            HTTPError: If calendar not found (404)
        """
        ...

    async def create_calendar(self, request: Request, calendar: Calendar) -> None:
        """Create a new calendar.

        Args:
            request: HTTP request
            calendar: Calendar to create

        Raises:
            HTTPError: If calendar already exists (409) or creation fails
        """
        ...

    async def delete_calendar(self, request: Request, path: str) -> None:
        """Delete a calendar.

        Args:
            request: HTTP request
            path: Calendar path

        Raises:
            HTTPError: If calendar not found (404)
        """
        ...

    async def get_calendar_object(
        self, request: Request, path: str, comp_request: CalendarCompRequest | None = None
    ) -> CalendarObject:
        """Get a calendar object (event, todo, etc.).

        Args:
            request: HTTP request
            path: Calendar object path
            comp_request: Optional component request

        Returns:
            CalendarObject

        Raises:
            HTTPError: If object not found (404)
        """
        ...

    async def list_calendar_objects(
        self, request: Request, calendar_path: str, comp_request: CalendarCompRequest | None = None
    ) -> list[CalendarObject]:
        """List all calendar objects in a calendar.

        Args:
            request: HTTP request
            calendar_path: Calendar path
            comp_request: Optional component request

        Returns:
            List of CalendarObject

        Raises:
            HTTPError: If calendar not found (404)
        """
        ...

    async def query_calendar_objects(
        self, request: Request, calendar_path: str, query: CalendarQuery
    ) -> list[CalendarObject]:
        """Query calendar objects with filters.

        Args:
            request: HTTP request
            calendar_path: Calendar path
            query: CalDAV query with filters

        Returns:
            List of matching CalendarObject

        Raises:
            HTTPError: If calendar not found (404)
        """
        ...

    async def put_calendar_object(
        self,
        request: Request,
        path: str,
        ical_data: str,
        if_none_match: bool = False,
        if_match: str | None = None,
    ) -> CalendarObject:
        """Create or update a calendar object.

        Args:
            request: HTTP request
            path: Calendar object path
            ical_data: iCalendar data as string
            if_none_match: If True, fail if resource exists
            if_match: ETag that must match for update

        Returns:
            Created/updated CalendarObject

        Raises:
            HTTPError: If preconditions fail or validation fails
        """
        ...

    async def delete_calendar_object(self, request: Request, path: str) -> None:
        """Delete a calendar object.

        Args:
            request: HTTP request
            path: Calendar object path

        Raises:
            HTTPError: If object not found (404)
        """
        ...
