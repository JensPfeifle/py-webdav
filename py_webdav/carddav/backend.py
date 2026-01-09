"""CardDAV backend interface."""

from __future__ import annotations

from typing import Protocol

from starlette.requests import Request

from .carddav import AddressBook, AddressBookQuery, AddressObject


class CardDAVBackend(Protocol):
    """CardDAV server backend interface.

    Implementations provide storage and retrieval of address books and contacts.
    """

    async def addressbook_home_set_path(self, request: Request) -> str:
        """Get the addressbook home set path for the current user.

        Args:
            request: HTTP request

        Returns:
            Path to addressbook home set (e.g., "/contacts/")
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

    async def list_addressbooks(self, request: Request) -> list[AddressBook]:
        """List all address books for the current user.

        Args:
            request: HTTP request

        Returns:
            List of AddressBook objects
        """
        ...

    async def get_addressbook(self, request: Request, path: str) -> AddressBook:
        """Get address book by path.

        Args:
            request: HTTP request
            path: Address book path

        Returns:
            AddressBook object

        Raises:
            HTTPError: If address book not found (404)
        """
        ...

    async def create_addressbook(self, request: Request, addressbook: AddressBook) -> None:
        """Create a new address book.

        Args:
            request: HTTP request
            addressbook: AddressBook to create

        Raises:
            HTTPError: If address book already exists (409) or creation fails
        """
        ...

    async def delete_addressbook(self, request: Request, path: str) -> None:
        """Delete an address book.

        Args:
            request: HTTP request
            path: Address book path

        Raises:
            HTTPError: If address book not found (404)
        """
        ...

    async def get_address_object(
        self, request: Request, path: str
    ) -> AddressObject:
        """Get an address object (vCard).

        Args:
            request: HTTP request
            path: Address object path

        Returns:
            AddressObject

        Raises:
            HTTPError: If object not found (404)
        """
        ...

    async def list_address_objects(
        self, request: Request, addressbook_path: str
    ) -> list[AddressObject]:
        """List all address objects in an address book.

        Args:
            request: HTTP request
            addressbook_path: Address book path

        Returns:
            List of AddressObject

        Raises:
            HTTPError: If address book not found (404)
        """
        ...

    async def query_address_objects(
        self, request: Request, addressbook_path: str, query: AddressBookQuery
    ) -> list[AddressObject]:
        """Query address objects with filters.

        Args:
            request: HTTP request
            addressbook_path: Address book path
            query: CardDAV query with filters

        Returns:
            List of matching AddressObject

        Raises:
            HTTPError: If address book not found (404)
        """
        ...

    async def put_address_object(
        self,
        request: Request,
        path: str,
        vcard_data: str,
        if_none_match: bool = False,
        if_match: str | None = None,
    ) -> AddressObject:
        """Create or update an address object.

        Args:
            request: HTTP request
            path: Address object path
            vcard_data: vCard data as string
            if_none_match: If True, fail if resource exists
            if_match: ETag that must match for update

        Returns:
            Created/updated AddressObject

        Raises:
            HTTPError: If preconditions fail or validation fails
        """
        ...

    async def delete_address_object(self, request: Request, path: str) -> None:
        """Delete an address object.

        Args:
            request: HTTP request
            path: Address object path

        Raises:
            HTTPError: If object not found (404)
        """
        ...
