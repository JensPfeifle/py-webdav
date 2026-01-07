"""CardDAV types and vCard support.

CardDAV is defined in RFC 6352.

TODO: Full implementation pending - this is a minimal stub to allow imports.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AddressBook:
    """CardDAV address book."""

    path: str
    name: str = ""
    description: str = ""
    max_resource_size: int = 0


@dataclass
class AddressObject:
    """CardDAV address object (vCard)."""

    path: str
    data: str  # vCard data
    etag: str = ""
    content_type: str = "text/vcard"


# Capability constant
CAPABILITY_ADDRESSBOOK = "addressbook"
