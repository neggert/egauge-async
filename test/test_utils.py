import pytest

from egauge_async.utils import create_query_string, is_valid_host


@pytest.mark.parametrize(
    "input,expected",
    [
        (["p"], "?p"),
        ([("k", "v")], "?k=v"),
        (["p", ("k", "v")], "?p&k=v"),
    ],
)
def test_create_query_string(input, expected):
    qs = create_query_string(input)
    assert qs == expected


# Host validation tests
def test_is_valid_host_rejects_http_prefix():
    """Test that is_valid_host rejects host with http:// prefix."""
    assert is_valid_host("http://egauge.local") is False


def test_is_valid_host_rejects_https_prefix():
    """Test that is_valid_host rejects host with https:// prefix."""
    assert is_valid_host("https://egauge.local") is False


def test_is_valid_host_rejects_port_number():
    """Test that is_valid_host rejects host with port number."""
    assert is_valid_host("egauge.local:8080") is False


def test_is_valid_host_rejects_path_separator():
    """Test that is_valid_host rejects host with path separator."""
    assert is_valid_host("egauge.local/") is False


def test_is_valid_host_rejects_path():
    """Test that is_valid_host rejects host with path."""
    assert is_valid_host("egauge.local/api/register") is False


def test_is_valid_host_accepts_ipv4_address():
    """Test that is_valid_host accepts valid IPv4 address (which is a valid DNS hostname)."""
    assert is_valid_host("192.168.1.100") is True


def test_is_valid_host_accepts_dns_hostname():
    """Test that is_valid_host accepts valid DNS hostname."""
    assert is_valid_host("egauge12345.local") is True


def test_is_valid_host_accepts_dns_hostname_with_subdomain():
    """Test that is_valid_host accepts DNS hostname with subdomain."""
    assert is_valid_host("meter.example.com") is True


def test_is_valid_host_rejects_invalid_dns_hostname():
    """Test that is_valid_host rejects invalid DNS hostname."""
    assert is_valid_host("-invalid.local") is False  # starts with hyphen
    assert is_valid_host("invalid-.local") is False  # ends with hyphen
    assert is_valid_host("invalid..local") is False  # double dot


def test_is_valid_host_rejects_hostname_too_long():
    """Test that is_valid_host rejects hostname longer than 253 chars."""
    long_hostname = "a" * 254 + ".com"
    assert is_valid_host(long_hostname) is False


def test_is_valid_host_accepts_single_label_hostname():
    """Test that is_valid_host accepts single-label hostname."""
    assert is_valid_host("localhost") is True


def test_is_valid_host_rejects_empty_string():
    """Test that is_valid_host rejects empty string."""
    assert is_valid_host("") is False
