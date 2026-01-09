"""Filesystem-based CardDAV backend implementation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import md5
from pathlib import Path
from typing import Any

from starlette.requests import Request

from ..internal import HTTPError
from .carddav import AddressBook, AddressBookQuery, AddressObject, validate_address_object


class LocalCardDAVBackend:
    """Filesystem-based CardDAV backend.

    Address books are stored as directories with metadata in .metadata.json.
    Address objects (.vcf files) are stored within address book directories.
    """

    def __init__(
        self,
        root_dir: Path,
        home_set_path: str = "/contacts/",
        principal_path: str = "/principals/current/",
    ) -> None:
        """Initialize backend.

        Args:
            root_dir: Root directory for all data
            home_set_path: Address book home set path
            principal_path: User principal path
        """
        self.root_dir: Path = Path(root_dir)
        self.home_set_path: str = home_set_path
        self.principal_path: str = principal_path

        # Ensure contacts directory exists
        self.addressbooks_dir: Path = self.root_dir / "contacts"
        self.addressbooks_dir.mkdir(parents=True, exist_ok=True)

    async def addressbook_home_set_path(self, request: Request) -> str:
        """Get address book home set path."""
        return self.home_set_path

    async def current_user_principal(self, request: Request) -> str:
        """Get current user principal path."""
        return self.principal_path

    def _addressbook_dir(self, addressbook_path: str) -> Path:
        """Get filesystem directory for address book path."""
        # Extract address book name from path like "/contacts/personal/"
        parts = [p for p in addressbook_path.split("/") if p and p != "contacts"]
        if not parts:
            raise HTTPError(404, Exception("Invalid address book path"))
        addressbook_name = parts[0]
        return self.addressbooks_dir / addressbook_name

    def _read_addressbook_metadata(self, addressbook_dir: Path) -> AddressBook:
        """Read address book metadata from directory."""
        metadata_file: Path = addressbook_dir / ".metadata.json"

        if metadata_file.exists():
            with open(metadata_file) as f:
                data: dict[str, Any] = json.load(f)
            return AddressBook(
                path=f"{self.home_set_path}{addressbook_dir.name}/",
                name=str(data.get("name", addressbook_dir.name)),
                description=str(data.get("description", "")),
                max_resource_size=int(data.get("max_resource_size", 0)),
            )
        else:
            # Default address book metadata
            return AddressBook(
                path=f"{self.home_set_path}{addressbook_dir.name}/",
                name=addressbook_dir.name,
                description="",
            )

    def _write_addressbook_metadata(self, addressbook: AddressBook) -> None:
        """Write address book metadata to directory."""
        addressbook_dir = self._addressbook_dir(addressbook.path)
        addressbook_dir.mkdir(parents=True, exist_ok=True)

        metadata_file = addressbook_dir / ".metadata.json"
        data = {
            "name": addressbook.name,
            "description": addressbook.description,
            "max_resource_size": addressbook.max_resource_size,
        }
        with open(metadata_file, "w") as f:
            json.dump(data, f, indent=2)

    async def list_addressbooks(self, request: Request) -> list[AddressBook]:
        """List all address books."""
        addressbooks = []

        if not self.addressbooks_dir.exists():
            return addressbooks

        for item in self.addressbooks_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                try:
                    addressbook = self._read_addressbook_metadata(item)
                    addressbooks.append(addressbook)
                except Exception:
                    # Skip invalid address books
                    continue

        return addressbooks

    async def get_addressbook(self, request: Request, path: str) -> AddressBook:
        """Get address book by path."""
        addressbook_dir = self._addressbook_dir(path)

        if not addressbook_dir.exists() or not addressbook_dir.is_dir():
            raise HTTPError(404, Exception(f"Address book not found: {path}"))

        return self._read_addressbook_metadata(addressbook_dir)

    async def create_addressbook(self, request: Request, addressbook: AddressBook) -> None:
        """Create a new address book."""
        addressbook_dir = self._addressbook_dir(addressbook.path)

        if addressbook_dir.exists():
            raise HTTPError(409, Exception(f"Address book already exists: {addressbook.path}"))

        self._write_addressbook_metadata(addressbook)

    async def delete_addressbook(self, request: Request, path: str) -> None:
        """Delete an address book."""
        import shutil

        addressbook_dir = self._addressbook_dir(path)

        if not addressbook_dir.exists():
            raise HTTPError(404, Exception(f"Address book not found: {path}"))

        shutil.rmtree(addressbook_dir)

    def _object_file(self, path: str) -> Path:
        """Get filesystem path for address object."""
        # Extract address book and object name from path like "/contacts/personal/contact.vcf"
        parts = [p for p in path.split("/") if p and p != "contacts"]
        if len(parts) < 2:
            raise HTTPError(404, Exception("Invalid object path"))

        addressbook_name = parts[0]
        object_name = parts[1]

        if not object_name.endswith(".vcf"):
            object_name += ".vcf"

        return self.addressbooks_dir / addressbook_name / object_name

    async def get_address_object(self, request: Request, path: str) -> AddressObject:
        """Get an address object."""
        file_path = self._object_file(path)

        if not file_path.exists() or not file_path.is_file():
            raise HTTPError(404, Exception(f"Address object not found: {path}"))

        # Read vCard data
        vcard_data = file_path.read_text()

        # Get file stats
        stat = file_path.stat()
        mod_time = datetime.fromtimestamp(stat.st_mtime, tz=UTC)

        # Generate ETag from content
        etag = md5(vcard_data.encode()).hexdigest()

        return AddressObject(
            path=path,
            data=vcard_data,
            mod_time=mod_time,
            content_length=stat.st_size,
            etag=etag,
        )

    async def list_address_objects(
        self, request: Request, addressbook_path: str
    ) -> list[AddressObject]:
        """List all address objects in an address book."""
        addressbook_dir = self._addressbook_dir(addressbook_path)

        if not addressbook_dir.exists():
            raise HTTPError(404, Exception(f"Address book not found: {addressbook_path}"))

        objects = []
        for file_path in addressbook_dir.glob("*.vcf"):
            try:
                object_path = f"{addressbook_path}{file_path.name}"
                obj = await self.get_address_object(request, object_path)
                objects.append(obj)
            except Exception:
                # Skip invalid objects
                continue

        return objects

    async def query_address_objects(
        self, request: Request, addressbook_path: str, query: AddressBookQuery
    ) -> list[AddressObject]:
        """Query address objects with filters."""
        # TODO: Implement filtering logic
        # For now, just return all objects
        return await self.list_address_objects(request, addressbook_path)

    async def put_address_object(
        self,
        request: Request,
        path: str,
        vcard_data: str,
        if_none_match: bool = False,
        if_match: str | None = None,
    ) -> AddressObject:
        """Create or update an address object."""
        file_path = self._object_file(path)

        # Check preconditions
        if if_none_match and file_path.exists():
            raise HTTPError(412, Exception("Precondition failed: resource already exists"))

        if if_match is not None:
            if not file_path.exists():
                raise HTTPError(412, Exception("Precondition failed: resource does not exist"))

            # Check ETag
            existing = await self.get_address_object(request, path)
            if existing.etag != if_match:
                raise HTTPError(412, Exception("Precondition failed: ETag mismatch"))

        # Validate vCard data
        try:
            validate_address_object(vcard_data)
        except Exception as e:
            raise HTTPError(400, Exception(f"Invalid vCard data: {e}")) from e

        # Ensure address book directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        file_path.write_text(vcard_data)

        # Return the created/updated object
        return await self.get_address_object(request, path)

    async def delete_address_object(self, request: Request, path: str) -> None:
        """Delete an address object."""
        file_path = self._object_file(path)

        if not file_path.exists():
            raise HTTPError(404, Exception(f"Address object not found: {path}"))

        file_path.unlink()
