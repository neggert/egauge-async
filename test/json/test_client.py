"""Tests for EgaugeJsonClient."""

import pytest

from egauge_async.json.client import EgaugeJsonClient
from egauge_async.json.models import RegisterType
from mocks import MockAsyncClient, MultiResponseClient


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


# Phase 2: get_register_info() tests
@pytest.mark.asyncio
async def test_get_register_info_success():
    """Test successfully fetching register information."""
    response_data = {
        "ts": "1678330813.000129799",
        "registers": [
            {"name": "Grid", "type": "P", "idx": 17, "did": 0},
            {"name": "Solar", "type": "P", "idx": 18, "did": 1},
            {"name": "Total Usage", "type": "P", "idx": 19},  # Virtual (no did)
        ],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler(
        "/auth/unauthorized", {"rlm": "eGauge", "nnc": "abc123"}
    )
    mock_client.add_post_handler("/auth/login", {"jwt": "test_token"})
    mock_client.add_get_handler("/register", response_data)

    client = EgaugeJsonClient("https://egauge12345.local", "owner", "pass", mock_client)

    registers = await client.get_register_info()

    assert len(registers) == 3
    assert "Grid" in registers
    assert registers["Grid"].name == "Grid"
    assert registers["Grid"].type == RegisterType.POWER
    assert registers["Grid"].idx == 17
    assert registers["Grid"].did == 0

    assert "Total Usage" in registers
    assert registers["Total Usage"].did is None  # Virtual register


@pytest.mark.asyncio
async def test_get_register_info_caching():
    """Test that register info is cached after first fetch."""
    response_data = {
        "ts": "1678330813.000",
        "registers": [{"name": "Grid", "type": "P", "idx": 17, "did": 0}],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/auth/unauthorized", {"rlm": "eGauge", "nnc": "abc"})
    mock_client.add_post_handler("/auth/login", {"jwt": "token"})
    mock_client.add_get_handler("/register", response_data)

    client = EgaugeJsonClient("https://egauge12345.local", "owner", "pass", mock_client)

    # First call
    registers1 = await client.get_register_info()
    call_count_after_first = len(mock_client.calls)

    # Second call (should use cache)
    registers2 = await client.get_register_info()

    assert registers1 == registers2
    assert len(mock_client.calls) == call_count_after_first  # No additional calls


@pytest.mark.asyncio
async def test_get_register_info_uses_bearer_auth():
    """Test that get_register_info uses Bearer token authentication."""
    response_data = {
        "ts": "1678330813.000",
        "registers": [{"name": "Grid", "type": "P", "idx": 17, "did": 0}],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/auth/unauthorized", {"rlm": "eGauge", "nnc": "abc"})
    mock_client.add_post_handler("/auth/login", {"jwt": "test_jwt_token"})
    mock_client.add_get_handler("/register", response_data)

    client = EgaugeJsonClient("https://egauge12345.local", "owner", "pass", mock_client)

    await client.get_register_info()

    # Verify auth flow happened (get nonce + login)
    assert any("/auth/unauthorized" in call[1] for call in mock_client.calls)
    assert any("/auth/login" in call[1] for call in mock_client.calls)
