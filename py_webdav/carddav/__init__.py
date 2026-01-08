"""CardDAV support for py-webdav."""

from .carddav import (
    CAPABILITY_ADDRESSBOOK,
    AddressBook,
    AddressBookMultiGet,
    AddressBookQuery,
    AddressObject,
    ParamFilter,
    PropFilter,
    SyncQuery,
    SyncResponse,
    TextMatch,
    validate_address_object,
)
from .server import handle_carddav_propfind

__all__ = [
    "CAPABILITY_ADDRESSBOOK",
    "AddressBook",
    "AddressBookMultiGet",
    "AddressBookQuery",
    "AddressObject",
    "ParamFilter",
    "PropFilter",
    "SyncQuery",
    "SyncResponse",
    "TextMatch",
    "validate_address_object",
    "handle_carddav_propfind",
]
