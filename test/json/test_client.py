"""Tests for EgaugeJsonClient."""

import pytest
from datetime import datetime, timedelta, timezone

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


# Phase 4: get_historical_counters() tests
@pytest.mark.asyncio
async def test_get_historical_counters_basic():
    """Test fetching historical counter data with quantum conversion."""
    response_data = {
        "registers": [
            {"name": "Grid", "type": "P", "idx": 17},
            {"name": "Voltage", "type": "V", "idx": 18},
        ],
        "ranges": [
            {
                "ts": "1678298313.000",
                "delta": 60,
                "rows": [
                    [
                        "7494425049",
                        "120000000",
                    ],  # Grid=7494425049 W·s, Voltage=120000.0 V·s
                    [
                        "7494425954",
                        "120000500",
                    ],  # Grid=7494425954 W·s, Voltage=120000.5 V·s
                ],
            }
        ],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/auth/unauthorized", {"rlm": "eGauge", "nnc": "abc"})
    mock_client.add_post_handler("/auth/login", {"jwt": "token"})
    mock_client.add_get_handler("/register", response_data)

    client = EgaugeJsonClient("https://egauge12345.local", "owner", "pass", mock_client)

    start = datetime(2023, 3, 8, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2023, 3, 8, 13, 0, 0, tzinfo=timezone.utc)
    step = timedelta(seconds=60)

    result = await client.get_historical_counters(start, end, step)

    assert len(result) == 2

    # First row
    assert result[0]["ts"] == datetime.fromtimestamp(1678298313.0, tz=timezone.utc)
    assert result[0]["Grid"] == 7494425049.0  # quantum=1.0 for Power
    assert result[0]["Voltage"] == 120000.0  # 120000000 * 0.001 for Voltage

    # Second row (60 seconds later)
    assert result[1]["ts"] == datetime.fromtimestamp(1678298313.0 + 60, tz=timezone.utc)
    assert result[1]["Grid"] == 7494425954.0
    assert result[1]["Voltage"] == 120000.5  # 120000500 * 0.001


@pytest.mark.asyncio
async def test_get_historical_counters_multiple_ranges():
    """Test handling response with multiple ranges (different delta values)."""
    response_data = {
        "registers": [{"name": "Grid", "type": "P", "idx": 17}],
        "ranges": [
            {
                "ts": "1678298313.000",
                "delta": 60,
                "rows": [["100"], ["200"]],
            },
            {
                "ts": "1678298500.000",
                "delta": 3600,  # Different delta (1 hour)
                "rows": [["300"], ["400"]],
            },
        ],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/auth/unauthorized", {"rlm": "eGauge", "nnc": "abc"})
    mock_client.add_post_handler("/auth/login", {"jwt": "token"})
    mock_client.add_get_handler("/register", response_data)

    client = EgaugeJsonClient("https://egauge12345.local", "owner", "pass", mock_client)

    start = datetime(2023, 3, 8, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2023, 3, 8, 13, 0, 0, tzinfo=timezone.utc)
    step = timedelta(seconds=60)

    result = await client.get_historical_counters(start, end, step)

    # Should have 4 total rows (2 from each range)
    assert len(result) == 4

    # First range rows
    assert result[0]["ts"] == datetime.fromtimestamp(1678298313.0, tz=timezone.utc)
    assert result[0]["Grid"] == 100.0
    assert result[1]["ts"] == datetime.fromtimestamp(1678298313.0 + 60, tz=timezone.utc)
    assert result[1]["Grid"] == 200.0

    # Second range rows with different delta
    assert result[2]["ts"] == datetime.fromtimestamp(1678298500.0, tz=timezone.utc)
    assert result[2]["Grid"] == 300.0
    assert result[3]["ts"] == datetime.fromtimestamp(
        1678298500.0 + 3600, tz=timezone.utc
    )
    assert result[3]["Grid"] == 400.0


@pytest.mark.asyncio
async def test_get_historical_counters_with_register_filter():
    """Test filtering historical data to specific registers."""
    register_info_response = {
        "ts": "1678330813.000",
        "registers": [
            {"name": "Grid", "type": "P", "idx": 17, "did": 0},
            {"name": "Solar", "type": "P", "idx": 18, "did": 1},
        ],
    }

    historical_response = {
        "registers": [{"name": "Grid", "type": "P", "idx": 17}],
        "ranges": [{"ts": "1678298313.000", "delta": 60, "rows": [["7494425049"]]}],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/auth/unauthorized", {"rlm": "eGauge", "nnc": "abc"})
    mock_client.add_post_handler("/auth/login", {"jwt": "token"})
    mock_client.add_get_handler("/register", register_info_response)

    client = EgaugeJsonClient("https://egauge12345.local", "owner", "pass", mock_client)

    # Pre-populate cache
    await client.get_register_info()

    # Add handler for historical call
    mock_client.add_get_handler("/register", historical_response)

    start = datetime(2023, 3, 8, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2023, 3, 8, 13, 0, 0, tzinfo=timezone.utc)
    step = timedelta(seconds=60)

    result = await client.get_historical_counters(start, end, step, registers=["Grid"])

    assert len(result) == 1
    assert "Grid" in result[0]
    assert "Solar" not in result[0]  # Filtered out


@pytest.mark.asyncio
async def test_get_historical_counters_with_max_rows():
    """Test limiting historical data with max_rows parameter."""
    response_data = {
        "registers": [{"name": "Grid", "type": "P", "idx": 17}],
        "ranges": [
            {
                "ts": "1678298313.000",
                "delta": 60,
                "rows": [["100"], ["200"]],  # Only 2 rows despite more available
            }
        ],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/auth/unauthorized", {"rlm": "eGauge", "nnc": "abc"})
    mock_client.add_post_handler("/auth/login", {"jwt": "token"})
    mock_client.add_get_handler("/register", response_data)

    client = EgaugeJsonClient("https://egauge12345.local", "owner", "pass", mock_client)

    start = datetime(2023, 3, 8, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2023, 3, 8, 13, 0, 0, tzinfo=timezone.utc)
    step = timedelta(seconds=60)

    result = await client.get_historical_counters(start, end, step, max_rows=2)

    # Should only return 2 rows as limited by max_rows
    assert len(result) == 2
