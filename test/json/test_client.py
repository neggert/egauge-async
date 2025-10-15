"""Tests for EgaugeJsonClient."""

from egauge_async.json.client import EgaugeJsonClient
from mocks import MockAsyncClient


# Phase 1: Initialization tests
def test_init_stores_parameters():
    """Test that __init__ stores all parameters correctly."""
    mock_client = MockAsyncClient("https://example.com", {})

    client = EgaugeJsonClient(
        base_url="https://egauge12345.local",
        username="owner",
        password="testpass",
        client=mock_client,
    )

    assert client.base_url == "https://egauge12345.local"
    assert client.username == "owner"
    assert client.password == "testpass"
    assert client.client is mock_client


def test_init_creates_auth_manager():
    """Test that __init__ creates a JwtAuthManager instance."""
    mock_client = MockAsyncClient("https://example.com", {})

    client = EgaugeJsonClient(
        base_url="https://egauge12345.local",
        username="owner",
        password="testpass",
        client=mock_client,
    )

    assert hasattr(client, "auth")
    assert client.auth is not None


def test_init_initializes_register_cache():
    """Test that __init__ initializes _register_cache to None."""
    mock_client = MockAsyncClient("https://example.com", {})

    client = EgaugeJsonClient(
        base_url="https://egauge12345.local",
        username="owner",
        password="testpass",
        client=mock_client,
    )

    assert client._register_cache is None
