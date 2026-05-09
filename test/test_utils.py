# pyright: reportDeprecated=false
import pytest

from egauge_async.utils import create_query_string, is_valid_host
from egauge_async.utils import QueryParam


@pytest.mark.parametrize(
    "input,expected",
    [
        (["p"], "?p"),
        ([("k", "v")], "?k=v"),
        (["p", ("k", "v")], "?p&k=v"),
    ],
)
def test_create_query_string(input: list[QueryParam], expected: str) -> None:
    qs = create_query_string(input)
    assert qs == expected


# Host validation tests
@pytest.mark.parametrize(
    "host,expected,reason",
    [
        # Valid hostnames
        ("egauge12345.local", True, "valid DNS hostname"),
        ("meter.example.com", True, "DNS hostname with subdomain"),
        ("localhost", True, "single-label hostname"),
        ("192.168.1.100", True, "IPv4 address (valid DNS hostname)"),
        ("egauge-123.local", True, "hostname with hyphen"),
        ("a.b.c.d.e.f", True, "hostname with many labels"),
        # Invalid - protocol prefixes
        ("http://egauge.local", False, "http:// prefix"),
        ("https://egauge.local", False, "https:// prefix"),
        # Invalid - port numbers
        ("egauge.local:8080", False, "port number"),
        # Invalid - path separators
        ("egauge.local/", False, "trailing slash"),
        ("egauge.local/api/register", False, "path included"),
        # Invalid - DNS format violations
        ("-invalid.local", False, "starts with hyphen"),
        ("invalid-.local", False, "ends with hyphen"),
        ("invalid..local", False, "double dot"),
        ("", False, "empty string"),
        ("a" * 254 + ".com", False, "hostname too long (>253 chars)"),
    ],
)
def test_is_valid_host(host: str, expected: bool, reason: str) -> None:
    """Test that is_valid_host correctly validates hostnames."""
    assert is_valid_host(host) is expected, f"Failed for {reason}: {host}"
