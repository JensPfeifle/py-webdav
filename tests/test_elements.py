"""Tests for internal elements."""

from lxml import etree

from py_webdav.internal.elements import MultiStatus
from py_webdav.internal.internal import HrefError, HTTPError

# https://tools.ietf.org/html/rfc4918#section-9.6.2
EXAMPLE_DELETE_MULTISTATUS_STR = """<?xml version="1.0" encoding="utf-8" ?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>http://www.example.com/container/resource3</d:href>
    <d:status>HTTP/1.1 423 Locked</d:status>
    <d:error><d:lock-token-submitted/></d:error>
  </d:response>
</d:multistatus>"""


def test_response_err_error():
    """Test that Response.err() returns proper HTTPError."""
    xml_elem = etree.fromstring(EXAMPLE_DELETE_MULTISTATUS_STR.encode("utf-8"))
    ms = MultiStatus.from_xml(xml_elem)

    assert len(ms.responses) == 1, f"expected 1 <response>, got {len(ms.responses)}"

    resp = ms.responses[0]
    err = resp.err()

    assert err is not None, "Response.err() returned None, expected non-nil"
    # Should be HrefError wrapping HTTPError
    assert isinstance(err, HrefError), f"Response.err() = {type(err)}, expected HrefError"
    assert isinstance(err.err, HTTPError), f"HrefError.err = {type(err.err)}, expected HTTPError"
    assert err.err.code == 423, f"HTTPError.code = {err.err.code}, expected 423"


def test_multistatus_round_trip():
    """Test that MultiStatus can be serialized and deserialized."""
    # Parse the example XML
    xml_elem = etree.fromstring(EXAMPLE_DELETE_MULTISTATUS_STR.encode("utf-8"))
    ms = MultiStatus.from_xml(xml_elem)

    # Serialize it back
    xml_out = ms.to_xml()
    xml_str = etree.tostring(xml_out, encoding="unicode")

    # Verify it has the expected elements
    assert "response" in xml_str
    assert "href" in xml_str
    assert "status" in xml_str
