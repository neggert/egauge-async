"""Miscellaneous utitity functions"""

import ipaddress
import re
from typing import Iterable, Tuple, Union

QueryParam = Union[str, Tuple[str, str]]


def create_query_string(params: Iterable[QueryParam]) -> str:
    """
    Create a query string to be appended to a URL. Unlike the
    functionality built-in to requests, this function supports
    value-less parameters, e.g. "?p"

    Args:
        params: Iterable of query parameters. Each item may be
            either a single string, for a value-less parameter
            or a tuple of two strings for a key-value pair.

    Returns:
        The query string, including the leading "?"
    """
    query_string = ""
    for p in params:
        sep = "?" if len(query_string) == 0 else "&"
        query_string += sep
        if isinstance(p, tuple) and len(p) == 2:
            query_string += f"{p[0]}={p[1]}"
        else:
            query_string += p
    return query_string


def is_valid_host(host: str) -> bool:
    """
    Validate that a host string is either a valid DNS hostname or IPv4 address.

    Args:
        host: The host string to validate

    Returns:
        True if the host is valid, False otherwise

    Notes:
        - Rejects protocol prefixes (http://, https://)
        - Rejects port numbers
        - Rejects path separators
        - Accepts valid DNS hostnames per RFC 1123
        - Accepts valid IPv4 addresses
    """
    # Reject if contains protocol, port, or path separators
    if any(x in host for x in ["://", ":", "/"]):
        return False

    # Check if it's a valid IPv4 address
    try:
        ipaddress.IPv4Address(host)
        return True
    except ipaddress.AddressValueError:
        pass

    # Check if it's a valid DNS hostname
    if len(host) > 253:
        return False

    hostname_pattern = (
        r"^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*"
        r"[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
    )
    return bool(re.match(hostname_pattern, host))
