"""INFORM API-based CardDAV backend implementation.

This backend retrieves addresses from the INFORM API and exposes them
via CardDAV protocol. It is read-only and ignores any write operations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import md5
from typing import Any

from starlette.requests import Request

from ..inform_api_client import InformAPIClient, InformConfig
from ..internal import HTTPError
from .carddav import AddressBook, AddressBookQuery, AddressObject

# Address book names for each INFORM address type
ADDRESS_BOOK_MAPPING = {
    "customer": {"name": "Customers", "description": "Customer addresses from INFORM"},
    "supplier": {"name": "Suppliers", "description": "Supplier addresses from INFORM"},
    "employee": {"name": "Employees", "description": "Employee addresses from INFORM"},
    "other": {"name": "Other", "description": "Other addresses from INFORM"},
}


class InformCardDAVBackend:
    """INFORM API-based CardDAV backend.

    This backend is read-only. Write operations (create, update, delete) will
    raise HTTP 403 Forbidden errors to prevent modifications.

    Address books are organized by INFORM address types:
    - customer
    - supplier
    - employee
    - other
    """

    def __init__(
        self,
        config: InformConfig | None = None,
        home_set_path: str = "/contacts/",
        principal_path: str = "/principals/current/",
    ) -> None:
        """Initialize INFORM CardDAV backend.

        Args:
            config: INFORM API configuration (uses default if None)
            home_set_path: Address book home set path
            principal_path: User principal path
        """
        self.api_client = InformAPIClient(config)
        self.home_set_path = home_set_path
        self.principal_path = principal_path
        self._company_name: str | None = None

    async def _get_company_name(self) -> str:
        """Get the first available company name from INFORM API.

        Returns:
            Company name

        Raises:
            HTTPError: If no companies are available
        """
        if self._company_name is None:
            companies = await self.api_client.get_companies()
            if not companies:
                raise HTTPError(503, Exception("No companies available in INFORM"))
            self._company_name = companies[0]

        return self._company_name

    async def addressbook_home_set_path(self, request: Request) -> str:
        """Get address book home set path."""
        return self.home_set_path

    async def current_user_principal(self, request: Request) -> str:
        """Get current user principal path."""
        return self.principal_path

    def _get_addressbook_path(self, address_type: str) -> str:
        """Get path for address book by type."""
        return f"{self.home_set_path}{address_type}/"

    def _parse_addressbook_path(self, path: str) -> str:
        """Parse address book path to extract address type.

        Args:
            path: Address book path (e.g., "/contacts/customer/")

        Returns:
            Address type (customer, supplier, employee, other)

        Raises:
            HTTPError: If path is invalid
        """
        parts = [p for p in path.split("/") if p and p != "contacts"]
        if not parts or parts[0] not in ADDRESS_BOOK_MAPPING:
            raise HTTPError(404, Exception(f"Invalid address book path: {path}"))
        return parts[0]

    def _parse_object_path(self, path: str) -> tuple[str, str]:
        """Parse object path to extract address book type and object ID.

        Args:
            path: Object path (e.g., "/contacts/customer/BACHE.vcf")

        Returns:
            Tuple of (address_type, address_key)

        Raises:
            HTTPError: If path is invalid
        """
        parts = [p for p in path.split("/") if p and p != "contacts"]
        if len(parts) < 2:
            raise HTTPError(404, Exception(f"Invalid object path: {path}"))

        address_type = parts[0]
        if address_type not in ADDRESS_BOOK_MAPPING:
            raise HTTPError(404, Exception(f"Invalid address book type: {address_type}"))

        # Remove .vcf extension if present
        address_key = parts[1]
        if address_key.endswith(".vcf"):
            address_key = address_key[:-4]

        return address_type, address_key

    async def list_addressbooks(self, request: Request) -> list[AddressBook]:
        """List all address books (one per address type)."""
        addressbooks = []

        for address_type, info in ADDRESS_BOOK_MAPPING.items():
            addressbook = AddressBook(
                path=self._get_addressbook_path(address_type),
                name=info["name"],
                description=info["description"],
            )
            addressbooks.append(addressbook)

        return addressbooks

    async def get_addressbook(self, request: Request, path: str) -> AddressBook:
        """Get address book by path."""
        address_type = self._parse_addressbook_path(path)
        info = ADDRESS_BOOK_MAPPING[address_type]

        return AddressBook(
            path=path,
            name=info["name"],
            description=info["description"],
        )

    async def create_addressbook(self, request: Request, addressbook: AddressBook) -> None:
        """Create address book (not supported - read-only backend)."""
        raise HTTPError(403, Exception("INFORM backend is read-only"))

    async def delete_addressbook(self, request: Request, path: str) -> None:
        """Delete address book (not supported - read-only backend)."""
        raise HTTPError(403, Exception("INFORM backend is read-only"))

    def _inform_address_to_vcard(self, address_data: dict[str, Any]) -> str:
        """Convert INFORM address data to vCard format.

        Args:
            address_data: Address data from INFORM API

        Returns:
            vCard data as string
        """
        import vobject

        vcard = vobject.vCard()

        # Required: UID (use INFORM key)
        address_key = address_data.get("key", "")
        vcard.add("uid")
        vcard.uid.value = address_key

        # Required: FN (formatted name)
        # Use first post address line1 or key as fallback
        fn = address_key
        post_addresses = address_data.get("postAddresses", [])
        if post_addresses and len(post_addresses) > 0:
            post_addr = post_addresses[0].get("postAddress", {})
            line1 = post_addr.get("line1", "")
            if line1:
                fn = line1

        vcard.add("fn")
        vcard.fn.value = fn

        # N (name) - try to parse from line1 or use key
        vcard.add("n")
        if fn != address_key:
            # Simple parsing: assume "Company Name" format
            vcard.n.value = vobject.vcard.Name(family=fn)
        else:
            vcard.n.value = vobject.vcard.Name(family=address_key)

        # ORG (organization)
        vcard.add("org")
        vcard.org.value = [fn]

        # Add address type as category
        address_type = address_data.get("addressType", "")
        if address_type:
            vcard.add("categories")
            vcard.categories.value = [address_type.upper()]

        # Add postal address from first postAddress
        if post_addresses and len(post_addresses) > 0:
            post_addr = post_addresses[0].get("postAddress", {})

            # Extract address components
            street = post_addr.get("street", "")
            zip_city = post_addr.get("zipCodeAndCity", "")
            line1 = post_addr.get("line1", "")

            # Try to parse zip code and city
            city = ""
            postal_code = ""
            if zip_city:
                # Simple parsing: assume "12345 City Name" format
                parts = zip_city.split(" ", 1)
                if len(parts) == 2:
                    postal_code = parts[0]
                    city = parts[1]
                else:
                    city = zip_city

            if street or city or postal_code:
                adr = vcard.add("adr")
                adr.type_param = "WORK"
                adr.value = vobject.vcard.Address(
                    street=street,
                    city=city,
                    code=postal_code,
                )

            # Add phone if available
            phone = post_addr.get("phone", "")
            if phone:
                tel = vcard.add("tel")
                tel.type_param = "WORK"
                tel.value = phone

            # Add mobile if available
            mobile = post_addr.get("mobile", "")
            if mobile:
                tel = vcard.add("tel")
                tel.type_param = "CELL"
                tel.value = mobile

            # Add fax if available
            fax = post_addr.get("fax", "")
            if fax:
                tel = vcard.add("tel")
                tel.type_param = "FAX"
                tel.value = fax

            # Add email if available
            email = post_addr.get("email", "")
            if email:
                email_obj = vcard.add("email")
                email_obj.type_param = "WORK"
                email_obj.value = email

            # Add website if available
            website = post_addr.get("website", "")
            if website:
                url = vcard.add("url")
                url.value = website

        # Add note if available
        note = address_data.get("note", "")
        if note:
            vcard.add("note")
            vcard.note.value = note

        # Add tax ID as custom field
        tax_id = address_data.get("taxId", "")
        if tax_id:
            x_taxid = vcard.add("x-taxid")
            x_taxid.value = tax_id

        # Add client number as custom field
        client_number = address_data.get("clientNumber", "")
        if client_number:
            x_client = vcard.add("x-clientnumber")
            x_client.value = client_number

        # Serialize to string
        vcard_str: str = vcard.serialize()
        return vcard_str

    async def get_address_object(self, request: Request, path: str) -> AddressObject:
        """Get an address object (vCard)."""
        address_type, address_key = self._parse_object_path(path)
        company = await self._get_company_name()

        # Fetch address from INFORM API
        try:
            address_data = await self.api_client.get_address(company, address_key)
        except Exception as e:
            raise HTTPError(404, Exception(f"Address not found: {address_key}")) from e

        # Verify address type matches
        if address_data.get("addressType") != address_type:
            raise HTTPError(404, Exception(f"Address type mismatch for: {address_key}"))

        # Convert to vCard
        vcard_data = self._inform_address_to_vcard(address_data)

        # Generate ETag from content
        etag = md5(vcard_data.encode()).hexdigest()

        return AddressObject(
            path=path,
            data=vcard_data,
            mod_time=datetime.now(UTC),
            content_length=len(vcard_data.encode()),
            etag=etag,
        )

    async def list_address_objects(
        self, request: Request, addressbook_path: str
    ) -> list[AddressObject]:
        """List all address objects in an address book."""
        address_type = self._parse_addressbook_path(addressbook_path)
        company = await self._get_company_name()

        # Fetch addresses from INFORM API (limit to 1000)
        response = await self.api_client.get_addresses(
            company=company,
            address_type=address_type,
            limit=1000,
        )

        addresses = response.get("addresses", [])
        objects = []

        for address_data in addresses:
            address_key = address_data.get("key", "")
            if not address_key:
                continue

            try:
                # Convert to vCard
                vcard_data = self._inform_address_to_vcard(address_data)

                # Generate ETag
                etag = md5(vcard_data.encode()).hexdigest()

                # Create object path
                object_path = f"{addressbook_path}{address_key}.vcf"

                obj = AddressObject(
                    path=object_path,
                    data=vcard_data,
                    mod_time=datetime.now(UTC),
                    content_length=len(vcard_data.encode()),
                    etag=etag,
                )
                objects.append(obj)
            except Exception:
                # Skip invalid addresses
                continue

        return objects

    async def query_address_objects(
        self, request: Request, addressbook_path: str, query: AddressBookQuery
    ) -> list[AddressObject]:
        """Query address objects with filters.

        Note: Query filters are not fully implemented. Returns all objects.
        """
        # TODO: Implement filtering based on query.prop_filters
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
        """Create or update address object (not supported - read-only backend)."""
        raise HTTPError(403, Exception("INFORM backend is read-only"))

    async def delete_address_object(self, request: Request, path: str) -> None:
        """Delete address object (not supported - read-only backend)."""
        raise HTTPError(403, Exception("INFORM backend is read-only"))
