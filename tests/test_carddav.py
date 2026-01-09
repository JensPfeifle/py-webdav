"""Tests for CardDAV functionality."""
import pytest

from py_webdav.carddav import validate_address_object


def test_validate_address_object_valid():
    """Test validating a valid vCard."""
    vcard_data = """BEGIN:VCARD
VERSION:3.0
FN:John Doe
N:Doe;John;;;
UID:test-contact-123
EMAIL:john@example.com
TEL:+1-555-1234
END:VCARD"""

    uid = validate_address_object(vcard_data)

    assert uid == "test-contact-123", f"Expected test-contact-123, got {uid}"


def test_validate_address_object_version_4():
    """Test validating a vCard version 4.0."""
    vcard_data = """BEGIN:VCARD
VERSION:4.0
FN:Jane Smith
N:Smith;Jane;;;
UID:test-contact-456
EMAIL:jane@example.com
END:VCARD"""

    uid = validate_address_object(vcard_data)

    assert uid == "test-contact-456", f"Expected test-contact-456, got {uid}"


def test_validate_address_object_missing_uid():
    """Test that vCard without UID is rejected."""
    vcard_data = """BEGIN:VCARD
VERSION:3.0
FN:No UID Contact
N:Contact;NoUID;;;
EMAIL:nouid@example.com
END:VCARD"""

    with pytest.raises(ValueError, match="UID"):
        validate_address_object(vcard_data)


def test_validate_address_object_invalid_format():
    """Test that invalid vCard format is rejected."""
    vcard_data = """This is not a valid vCard"""

    with pytest.raises(Exception):  # vobject will raise an exception
        validate_address_object(vcard_data)
