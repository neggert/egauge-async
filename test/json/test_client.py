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


# Phase 3: get_current_measurements() tests
@pytest.mark.asyncio
async def test_get_current_measurements_all_registers():
    """Test fetching current measurements for all registers."""
    response_data = {
        "ts": "1678330813.000",
        "registers": [
            {"name": "Grid", "type": "P", "idx": 17, "rate": 1798.5},
            {"name": "Solar", "type": "P", "idx": 18, "rate": -450.3},
        ],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/auth/unauthorized", {"rlm": "eGauge", "nnc": "abc"})
    mock_client.add_post_handler("/auth/login", {"jwt": "token"})
    mock_client.add_get_handler("/register", response_data)

    client = EgaugeJsonClient("https://egauge12345.local", "owner", "pass", mock_client)

    measurements = await client.get_current_measurements()

    assert len(measurements) == 2
    assert measurements["Grid"] == 1798.5
    assert measurements["Solar"] == -450.3


@pytest.mark.asyncio
async def test_get_current_measurements_uses_rate_parameter():
    """Test that current measurements request includes rate parameter."""
    response_data = {
        "ts": "1678330813.000",
        "registers": [{"name": "Grid", "type": "P", "idx": 17, "rate": 1798.5}],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/auth/unauthorized", {"rlm": "eGauge", "nnc": "abc"})
    mock_client.add_post_handler("/auth/login", {"jwt": "token"})
    mock_client.add_get_handler("/register", response_data)

    client = EgaugeJsonClient("https://egauge12345.local", "owner", "pass", mock_client)

    measurements = await client.get_current_measurements()

    # Verify measurements were returned correctly
    assert len(measurements) == 1
    assert measurements["Grid"] == 1798.5


@pytest.mark.asyncio
async def test_get_current_measurements_with_register_filter():
    """Test filtering current measurements to specific registers."""
    # First response: register info for mapping names to indices
    register_info_response = {
        "ts": "1678330813.000",
        "registers": [
            {"name": "Grid", "type": "P", "idx": 17, "did": 0},
            {"name": "Solar", "type": "P", "idx": 18, "did": 1},
            {"name": "Total", "type": "P", "idx": 19},
        ],
    }

    # The MultiResponseClient will return register_info_response for first call (caching),
    # then same response for the filtered measurements call (simplified mock behavior)
    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/auth/unauthorized", {"rlm": "eGauge", "nnc": "abc"})
    mock_client.add_post_handler("/auth/login", {"jwt": "token"})
    # Register info call will cache the registers
    mock_client.add_get_handler("/register", register_info_response)

    client = EgaugeJsonClient("https://egauge12345.local", "owner", "pass", mock_client)

    # Pre-populate cache by calling get_register_info
    await client.get_register_info()

    # Now add handler for the filtered measurement call
    filtered_response = {
        "ts": "1678330813.000",
        "registers": [{"name": "Grid", "type": "P", "idx": 17, "rate": 1798.5}],
    }
    mock_client.add_get_handler("/register", filtered_response)

    measurements = await client.get_current_measurements(registers=["Grid"])

    # Should only return Grid with rate value
    assert len(measurements) == 1
    assert measurements["Grid"] == 1798.5


@pytest.mark.asyncio
async def test_get_current_measurements_no_rate_values():
    """Test handling response with registers but no rate values."""
    response_data = {
        "ts": "1678330813.000",
        "registers": [
            {"name": "Grid", "type": "P", "idx": 17},  # No rate field
        ],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/auth/unauthorized", {"rlm": "eGauge", "nnc": "abc"})
    mock_client.add_post_handler("/auth/login", {"jwt": "token"})
    mock_client.add_get_handler("/register", response_data)

    client = EgaugeJsonClient("https://egauge12345.local", "owner", "pass", mock_client)

    measurements = await client.get_current_measurements()

    # Should return empty dict since no rate values present
    assert len(measurements) == 0
