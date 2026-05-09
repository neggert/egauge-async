"""Miscellaneous utitity functions"""

import re
from typing import Iterable, Tuple, Union
from warnings import deprecated

QueryParam = Union[str, Tuple[str, str]]


@deprecated(
    "create_query_string is deprecated and will be removed in egauge-async v0.6.0."
)
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
    Validate that a host string is a valid DNS hostname.

    Args:
        host: The host string to validate

    Returns:
        True if the host is valid, False otherwise

    Notes:
        - Rejects protocol prefixes (http://, https://)
        - Rejects port numbers
        - Rejects path separators
        - Accepts valid DNS hostnames per RFC 1123 (including IP addresses,
          which are valid hostnames)
    """
    # Reject if contains protocol, port, or path separators
    if any(x in host for x in ["://", ":", "/"]):
        return False

    # Check if it's a valid DNS hostname (RFC 1123)
    # Total length up to 253 chars
    if len(host) > 253:
        return False

    # Hostname regex: labels separated by dots
    # Each label: starts with alphanumeric, contains alphanumeric or hyphens, ends with alphanumeric
    # Labels can be 1-63 characters
    hostname_pattern = (
        r"^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*"
        r"[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
    )
    return bool(re.match(hostname_pattern, host))
