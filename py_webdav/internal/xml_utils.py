"""XML utilities for WebDAV."""

from __future__ import annotations

from typing import Any

from lxml import etree


class RawXMLValue:
    """Raw XML value that can be marshaled/unmarshaled."""

    def __init__(
        self, element: etree.Element | None = None, obj: Any | None = None
    ) -> None:
        """Initialize raw XML value.

        Args:
            element: XML element to wrap
            obj: Python object to encode (mutually exclusive with element)
        """
        self.element = element
        self.obj = obj

    def xml_name(self) -> str | None:
        """Get XML tag name if this is an element."""
        if self.element is not None:
            return self.element.tag
        return None

    def decode(self, obj_type: type) -> Any:
        """Decode the XML value into a Python object.

        Args:
            obj_type: Type to decode into

        Returns:
            Decoded object
        """
        if self.element is None:
            raise ValueError("Cannot decode: no element")

        # For simple types, just return the text
        if obj_type is str:
            return self.element.text or ""
        elif obj_type is int:
            return int(self.element.text or "0")
        elif obj_type is bool:
            return (self.element.text or "").lower() in ("true", "1", "yes")

        # For complex types, would need custom decoding logic
        return self.element

    def encode(self) -> etree.Element:
        """Encode the value to XML."""
        if self.element is not None:
            return self.element
        if self.obj is not None:
            # Would need custom encoding logic
            raise NotImplementedError("Object encoding not implemented")
        raise ValueError("No element or object to encode")


def new_raw_xml_element(
    tag: str, attrib: dict[str, str] | None = None, children: list[etree.Element] | None = None
) -> RawXMLValue:
    """Create a new raw XML element.

    Args:
        tag: XML tag name
        attrib: Element attributes
        children: Child elements

    Returns:
        RawXMLValue wrapping the element
    """
    elem = etree.Element(tag, attrib=attrib or {})
    if children:
        for child in children:
            elem.append(child)
    return RawXMLValue(element=elem)


def encode_raw_xml_element(obj: Any) -> RawXMLValue:
    """Encode a Python object to a raw XML element.

    Args:
        obj: Object to encode

    Returns:
        RawXMLValue that can be marshaled
    """
    # Store the object for later encoding
    return RawXMLValue(obj=obj)


def value_xml_name(obj: Any) -> str:
    """Get the XML name for a Python object.

    Args:
        obj: Object to inspect

    Returns:
        XML tag name for the object

    Raises:
        ValueError: If object doesn't have XML metadata
    """
    # For etree elements, return the tag
    if isinstance(obj, etree._Element):
        return obj.tag

    # For dataclasses or other objects with a to_xml method
    if hasattr(obj, "to_xml"):
        elem = obj.to_xml()
        return elem.tag

    raise ValueError(f"Cannot determine XML name for {type(obj)}")
