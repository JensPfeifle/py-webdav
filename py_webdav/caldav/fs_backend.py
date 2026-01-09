"""Filesystem-based CalDAV backend implementation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import md5
from pathlib import Path
from typing import Any

from starlette.requests import Request

from ..internal import HTTPError
from .caldav import Calendar, CalendarCompRequest, CalendarObject, CalendarQuery, validate_calendar_object


class LocalCalDAVBackend:
    """Filesystem-based CalDAV backend.

    Calendars are stored as directories with metadata in .metadata.json.
    Calendar objects (.ics files) are stored within calendar directories.
    """

    def __init__(
        self,
        root_dir: Path,
        home_set_path: str = "/calendars/",
        principal_path: str = "/principals/current/",
    ) -> None:
        """Initialize backend.

        Args:
            root_dir: Root directory for all data
            home_set_path: Calendar home set path
            principal_path: User principal path
        """
        self.root_dir: Path = Path(root_dir)
        self.home_set_path: str = home_set_path
        self.principal_path: str = principal_path

        # Ensure calendars directory exists
        self.calendars_dir: Path = self.root_dir / "calendars"
        self.calendars_dir.mkdir(parents=True, exist_ok=True)

    async def calendar_home_set_path(self, request: Request) -> str:
        """Get calendar home set path."""
        return self.home_set_path

    async def current_user_principal(self, request: Request) -> str:
        """Get current user principal path."""
        return self.principal_path

    def _calendar_dir(self, calendar_path: str) -> Path:
        """Get filesystem directory for calendar path."""
        # Extract calendar name from path like "/calendars/work/"
        parts = [p for p in calendar_path.split("/") if p and p != "calendars"]
        if not parts:
            raise HTTPError(404, Exception("Invalid calendar path"))
        calendar_name = parts[0]
        return self.calendars_dir / calendar_name

    def _read_calendar_metadata(self, calendar_dir: Path) -> Calendar:
        """Read calendar metadata from directory."""
        metadata_file: Path = calendar_dir / ".metadata.json"

        if metadata_file.exists():
            with open(metadata_file) as f:
                data: dict[str, Any] = json.load(f)
            return Calendar(
                path=f"{self.home_set_path}{calendar_dir.name}/",
                name=str(data.get("name", calendar_dir.name)),
                description=str(data.get("description", "")),
                max_resource_size=int(data.get("max_resource_size", 0)),
                supported_component_set=list(data.get("supported_component_set", ["VEVENT", "VTODO"])),
            )
        else:
            # Default calendar metadata
            return Calendar(
                path=f"{self.home_set_path}{calendar_dir.name}/",
                name=calendar_dir.name,
                description="",
                supported_component_set=["VEVENT", "VTODO"],
            )

    def _write_calendar_metadata(self, calendar: Calendar) -> None:
        """Write calendar metadata to directory."""
        calendar_dir = self._calendar_dir(calendar.path)
        calendar_dir.mkdir(parents=True, exist_ok=True)

        metadata_file = calendar_dir / ".metadata.json"
        data = {
            "name": calendar.name,
            "description": calendar.description,
            "max_resource_size": calendar.max_resource_size,
            "supported_component_set": calendar.supported_component_set,
        }
        with open(metadata_file, "w") as f:
            json.dump(data, f, indent=2)

    async def list_calendars(self, request: Request) -> list[Calendar]:
        """List all calendars."""
        calendars = []

        if not self.calendars_dir.exists():
            return calendars

        for item in self.calendars_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                try:
                    calendar = self._read_calendar_metadata(item)
                    calendars.append(calendar)
                except Exception:
                    # Skip invalid calendars
                    continue

        return calendars

    async def get_calendar(self, request: Request, path: str) -> Calendar:
        """Get calendar by path."""
        calendar_dir = self._calendar_dir(path)

        if not calendar_dir.exists() or not calendar_dir.is_dir():
            raise HTTPError(404, Exception(f"Calendar not found: {path}"))

        return self._read_calendar_metadata(calendar_dir)

    async def create_calendar(self, request: Request, calendar: Calendar) -> None:
        """Create a new calendar."""
        calendar_dir = self._calendar_dir(calendar.path)

        if calendar_dir.exists():
            raise HTTPError(409, Exception(f"Calendar already exists: {calendar.path}"))

        self._write_calendar_metadata(calendar)

    async def delete_calendar(self, request: Request, path: str) -> None:
        """Delete a calendar."""
        import shutil

        calendar_dir = self._calendar_dir(path)

        if not calendar_dir.exists():
            raise HTTPError(404, Exception(f"Calendar not found: {path}"))

        shutil.rmtree(calendar_dir)

    def _object_file(self, path: str) -> Path:
        """Get filesystem path for calendar object."""
        # Extract calendar and object name from path like "/calendars/work/event.ics"
        parts = [p for p in path.split("/") if p and p != "calendars"]
        if len(parts) < 2:
            raise HTTPError(404, Exception("Invalid object path"))

        calendar_name = parts[0]
        object_name = parts[1]

        if not object_name.endswith(".ics"):
            object_name += ".ics"

        return self.calendars_dir / calendar_name / object_name

    async def get_calendar_object(
        self, request: Request, path: str, comp_request: CalendarCompRequest | None = None
    ) -> CalendarObject:
        """Get a calendar object."""
        file_path = self._object_file(path)

        if not file_path.exists() or not file_path.is_file():
            raise HTTPError(404, Exception(f"Calendar object not found: {path}"))

        # Read iCalendar data
        ical_data = file_path.read_text()

        # Get file stats
        stat = file_path.stat()
        mod_time = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        # Generate ETag from content
        etag = md5(ical_data.encode()).hexdigest()

        return CalendarObject(
            path=path,
            data=ical_data,
            mod_time=mod_time,
            content_length=stat.st_size,
            etag=etag,
        )

    async def list_calendar_objects(
        self, request: Request, calendar_path: str, comp_request: CalendarCompRequest | None = None
    ) -> list[CalendarObject]:
        """List all calendar objects in a calendar."""
        calendar_dir = self._calendar_dir(calendar_path)

        if not calendar_dir.exists():
            raise HTTPError(404, Exception(f"Calendar not found: {calendar_path}"))

        objects = []
        for file_path in calendar_dir.glob("*.ics"):
            try:
                object_path = f"{calendar_path}{file_path.name}"
                obj = await self.get_calendar_object(request, object_path, comp_request)
                objects.append(obj)
            except Exception:
                # Skip invalid objects
                continue

        return objects

    async def query_calendar_objects(
        self, request: Request, calendar_path: str, query: CalendarQuery
    ) -> list[CalendarObject]:
        """Query calendar objects with filters."""
        # TODO: Implement filtering logic
        # For now, just return all objects
        return await self.list_calendar_objects(request, calendar_path, None)

    async def put_calendar_object(
        self,
        request: Request,
        path: str,
        ical_data: str,
        if_none_match: bool = False,
        if_match: str | None = None,
    ) -> CalendarObject:
        """Create or update a calendar object."""
        file_path = self._object_file(path)

        # Check preconditions
        if if_none_match and file_path.exists():
            raise HTTPError(412, Exception("Precondition failed: resource already exists"))

        if if_match is not None:
            if not file_path.exists():
                raise HTTPError(412, Exception("Precondition failed: resource does not exist"))

            # Check ETag
            existing = await self.get_calendar_object(request, path)
            if existing.etag != if_match:
                raise HTTPError(412, Exception("Precondition failed: ETag mismatch"))

        # Validate calendar data
        try:
            validate_calendar_object(ical_data)
        except Exception as e:
            raise HTTPError(400, Exception(f"Invalid calendar data: {e}")) from e

        # Ensure calendar directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        file_path.write_text(ical_data)

        # Return the created/updated object
        return await self.get_calendar_object(request, path)

    async def delete_calendar_object(self, request: Request, path: str) -> None:
        """Delete a calendar object."""
        file_path = self._object_file(path)

        if not file_path.exists():
            raise HTTPError(404, Exception(f"Calendar object not found: {path}"))

        file_path.unlink()
