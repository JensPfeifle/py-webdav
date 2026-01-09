"""CardDAV types and vCard support.

CardDAV is defined in RFC 6352.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# CardDAV capability
CAPABILITY_ADDRESSBOOK = "addressbook"


@dataclass
class AddressBook:
    """CardDAV address book collection."""

    path: str
    name: str = ""
    description: str = ""
    max_resource_size: int = 0


@dataclass
class AddressObject:
    """CardDAV address object (vCard data)."""

    path: str
    data: str  # vCard data as string
    mod_time: datetime | None = None
    content_length: int = 0
    etag: str = ""


@dataclass
class TextMatch:
    """Text matching filter."""

    text: str
    negate_condition: bool = False
    match_type: str = "contains"  # contains, equals, starts-with, ends-with


@dataclass
class ParamFilter:
    """Parameter filter for address book queries."""

    name: str
    is_not_defined: bool = False
    text_match: TextMatch | None = None


@dataclass
class PropFilter:
    """Property filter for address book queries."""

    name: str
    is_not_defined: bool = False
    text_match: TextMatch | None = None
    param_filters: list[ParamFilter] = field(default_factory=list)


@dataclass
class AddressBookQuery:
    """CardDAV addressbook-query REPORT request."""

    prop_filters: list[PropFilter] = field(default_factory=list)
    limit: int = 0  # <= 0 means unlimited


@dataclass
class AddressBookMultiGet:
    """CardDAV addressbook-multiget REPORT request."""

    paths: list[str]


@dataclass
class SyncQuery:
    """CardDAV sync-collection request."""

    sync_token: str
    limit: int = 0  # <= 0 means unlimited


@dataclass
class SyncResponse:
    """CardDAV sync-collection response."""

    sync_token: str
    updated: list[AddressObject] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)


def validate_address_object(vcard_data: str) -> str:
    """Validate a vCard object.

    Args:
        vcard_data: vCard data as string

    Returns:
        UID from the vCard

    Raises:
        ValueError: If validation fails
    """
    try:
        import vobject

        vcard = vobject.readOne(vcard_data)

        if vcard.name != "VCARD":
            raise ValueError(f"expected VCARD, got {vcard.name}")

        # Get UID
        if not hasattr(vcard, "uid"):
            raise ValueError("vCard must have a UID property")

        return str(vcard.uid.value)

    except Exception as e:
        raise ValueError(f"invalid vCard object: {e}") from e
