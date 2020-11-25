"""Miscellaneous utitity functions"""

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
        elif isinstance(p, str):
            query_string += p
        else:
            raise ValueError(f"Unsupported query parameter {p}")
    return query_string
