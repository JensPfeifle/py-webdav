"""CardDAV support for py-webdav."""

from .backend import CardDAVBackend
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
from .fs_backend import LocalCardDAVBackend
from .inform_backend import InformCardDAVBackend
from .server import handle_carddav_propfind

__all__ = [
    "CardDAVBackend",
    "LocalCardDAVBackend",
    "InformCardDAVBackend",
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
