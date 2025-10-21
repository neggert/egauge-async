"""Tests for EgaugeJsonClient."""

import pytest
from datetime import datetime, timedelta, timezone

from egauge_async.json.client import EgaugeJsonClient
from egauge_async.json.models import RegisterType
from egauge_async.exceptions import (
    EgaugeUnknownRegisterError,
    EgaugeParsingException,
    EgaugePermissionError,
    EgaugeAuthenticationError,
)
from mocks import MockAsyncClient, MultiResponseClient, MockAuthManager


# Phase 0: Exception tests
def test_permission_error_can_be_raised():
    """Test that EgaugePermissionError can be raised and caught."""
    with pytest.raises(EgaugePermissionError, match="Permission denied"):
        raise EgaugePermissionError("Permission denied")


def test_permission_error_inherits_from_egauge_exception():
    """Test that EgaugePermissionError is an EgaugeException."""
    from egauge_async.exceptions import EgaugeException

    try:
        raise EgaugePermissionError("test error")
    except EgaugeException:
        pass  # Should catch as EgaugeException
    except Exception:
        pytest.fail("EgaugePermissionError should inherit from EgaugeException")


# Phase 1: Initialization tests
def test_init_stores_parameters():
    """Test that __init__ stores all parameters correctly."""
    mock_client = MockAsyncClient("https://example.com", {})
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        base_url="https://egauge12345.local",
        username="owner",
        password="testpass",
        client=mock_client,
        auth=mock_auth,
    )

    assert client.base_url == "https://egauge12345.local"
    assert client.username == "owner"
    assert client.password == "testpass"
    assert client.client is mock_client


def test_init_creates_auth_manager():
    """Test that __init__ uses provided auth manager."""
    mock_client = MockAsyncClient("https://example.com", {})
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        base_url="https://egauge12345.local",
        username="owner",
        password="testpass",
        client=mock_client,
        auth=mock_auth,
    )

    assert hasattr(client, "auth")
    assert client.auth is mock_auth


def test_init_initializes_register_cache():
    """Test that __init__ initializes _register_cache to None."""
    mock_client = MockAsyncClient("https://example.com", {})
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        base_url="https://egauge12345.local",
        username="owner",
        password="testpass",
        client=mock_client,
        auth=mock_auth,
    )

    assert client._register_cache is None


def test_init_validates_empty_base_url():
    """Test that __init__ raises ValueError for empty base_url."""
    mock_client = MockAsyncClient("https://example.com", {})
    mock_auth = MockAuthManager()

    with pytest.raises(ValueError, match="base_url cannot be empty"):
        EgaugeJsonClient(
            base_url="",
            username="owner",
            password="testpass",
            client=mock_client,
            auth=mock_auth,
        )


def test_init_validates_base_url_scheme():
    """Test that __init__ raises ValueError for invalid URL scheme."""
    mock_client = MockAsyncClient("https://example.com", {})
    mock_auth = MockAuthManager()

    with pytest.raises(ValueError, match="must start with http:// or https://"):
        EgaugeJsonClient(
            base_url="ftp://egauge.local",
            username="owner",
            password="testpass",
            client=mock_client,
            auth=mock_auth,
        )


def test_init_validates_empty_username():
    """Test that __init__ raises ValueError for empty username."""
    mock_client = MockAsyncClient("https://example.com", {})
    mock_auth = MockAuthManager()

    with pytest.raises(ValueError, match="username cannot be empty"):
        EgaugeJsonClient(
            base_url="https://egauge.local",
            username="",
            password="testpass",
            client=mock_client,
            auth=mock_auth,
        )


def test_init_validates_empty_password():
    """Test that __init__ raises ValueError for empty password."""
    mock_client = MockAsyncClient("https://example.com", {})
    mock_auth = MockAuthManager()

    with pytest.raises(ValueError, match="password cannot be empty"):
        EgaugeJsonClient(
            base_url="https://egauge.local",
            username="owner",
            password="",
            client=mock_client,
            auth=mock_auth,
        )


@pytest.mark.asyncio
async def test_close_calls_auth_logout():
    """Test that close() method calls auth.logout()."""
    mock_client = MockAsyncClient("https://example.com", {})
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        base_url="https://egauge.local",
        username="owner",
        password="testpass",
        client=mock_client,
        auth=mock_auth,
    )

    assert mock_auth.logout_calls == 0
    await client.close()
    assert mock_auth.logout_calls == 1


@pytest.mark.asyncio
async def test_context_manager_calls_close():
    """Test that async context manager calls close() on exit."""
    mock_client = MockAsyncClient("https://example.com", {})
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        base_url="https://egauge.local",
        username="owner",
        password="testpass",
        client=mock_client,
        auth=mock_auth,
    )

    assert mock_auth.logout_calls == 0

    # Use context manager
    async with client as ctx_client:
        assert ctx_client is client
        assert mock_auth.logout_calls == 0  # Not called yet

    # After exiting context, verify logout was called
    assert mock_auth.logout_calls == 1


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
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

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
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

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
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    await client.get_register_info()

    # Verify auth manager was called
    assert mock_auth.get_token_calls == 1


@pytest.mark.asyncio
async def test_get_register_info_missing_name_field():
    """Test that missing name field raises EgaugeParsingException."""
    response_data = {
        "ts": "1678330813.000",
        "registers": [{"type": "P", "idx": 17, "did": 0}],  # No name field
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    # Should raise exception since name field is missing
    with pytest.raises(EgaugeParsingException, match="Register missing 'name' field"):
        await client.get_register_info()


@pytest.mark.asyncio
async def test_get_register_info_missing_type_field():
    """Test that missing type field raises EgaugeParsingException."""
    response_data = {
        "ts": "1678330813.000",
        "registers": [{"name": "Grid", "idx": 17, "did": 0}],  # No type field
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    # Should raise exception since type field is missing
    with pytest.raises(
        EgaugeParsingException, match="Register 'Grid' missing 'type' field"
    ):
        await client.get_register_info()


@pytest.mark.asyncio
async def test_get_register_info_missing_idx_field():
    """Test that missing idx field raises EgaugeParsingException."""
    response_data = {
        "ts": "1678330813.000",
        "registers": [{"name": "Grid", "type": "P", "did": 0}],  # No idx field
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    # Should raise exception since idx field is missing
    with pytest.raises(
        EgaugeParsingException, match="Register 'Grid' missing 'idx' field"
    ):
        await client.get_register_info()


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
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

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
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    measurements = await client.get_current_measurements()

    # Verify measurements were returned correctly
    assert len(measurements) == 1
    assert measurements["Grid"] == 1798.5

    # Verify the rate parameter was passed
    assert len(mock_client.calls) == 1
    method, url, params = mock_client.calls[0]
    assert method == "GET"
    assert params is not None
    assert "rate" in params
    assert params["rate"] == ""


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

    # The MultiResponseClient will return register_info_response for first call (caching)
    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", register_info_response)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    # Pre-populate cache by calling get_register_info
    await client.get_register_info()

    # Now add handler for the filtered measurement call
    filtered_response = {
        "ts": "1678330813.000",
        "registers": [{"name": "Grid", "type": "P", "idx": 17, "rate": 1798.5}],
    }
    mock_client.add_get_handler("/api/register", filtered_response)

    measurements = await client.get_current_measurements(registers=["Grid"])

    # Should only return Grid with rate value
    assert len(measurements) == 1
    assert measurements["Grid"] == 1798.5

    # Verify the reg parameter was passed (2 calls: one for register info, one for measurements)
    assert len(mock_client.calls) == 2
    method, url, params = mock_client.calls[
        1
    ]  # Second call is the filtered measurements
    assert method == "GET"
    assert params is not None
    assert "reg" in params
    assert "17" in params["reg"]  # Grid has idx=17 (format may be none+17 or 17)
    assert "rate" in params
    assert params["rate"] == ""


@pytest.mark.asyncio
async def test_get_current_measurements_no_rate_values():
    """Test that missing rate field raises EgaugeParsingException."""
    response_data = {
        "ts": "1678330813.000",
        "registers": [
            {"name": "Grid", "type": "P", "idx": 17},  # No rate field
        ],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    # Should raise exception since rate field is missing
    with pytest.raises(
        EgaugeParsingException, match="Register 'Grid' missing 'rate' field"
    ):
        await client.get_current_measurements()


@pytest.mark.asyncio
async def test_get_current_measurements_unknown_register():
    """Test that requesting an unknown register raises EgaugeUnknownRegisterError."""
    register_info_response = {
        "ts": "1678330813.000",
        "registers": [
            {"name": "Grid", "type": "P", "idx": 17, "did": 0},
            {"name": "Solar", "type": "P", "idx": 18, "did": 1},
        ],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", register_info_response)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    # Pre-populate cache
    await client.get_register_info()

    # Try to get measurements for an unknown register
    with pytest.raises(
        EgaugeUnknownRegisterError, match="Unknown register Nonexistent"
    ):
        await client.get_current_measurements(registers=["Nonexistent"])


@pytest.mark.asyncio
async def test_get_current_measurements_missing_name_field():
    """Test that missing name field raises EgaugeParsingException."""
    response_data = {
        "ts": "1678330813.000",
        "registers": [
            {"type": "P", "idx": 17, "rate": 1798.5}  # No name field
        ],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    # Should raise exception since name field is missing
    with pytest.raises(EgaugeParsingException, match="Register missing 'name' field"):
        await client.get_current_measurements()


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
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    start = datetime(2023, 3, 8, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2023, 3, 8, 13, 0, 0, tzinfo=timezone.utc)
    step = timedelta(seconds=60)

    result = await client.get_historical_counters(start, end, step)

    assert len(result) == 2

    # First row
    assert result[0]["ts"] == datetime.fromtimestamp(1678298313.0, tz=timezone.utc)
    assert result[0]["Grid"] == 7494425049.0  # quantum=1.0 for Power
    assert result[0]["Voltage"] == 120000.0  # 120000000 * 0.001 for Voltage

    # Second row (60 seconds earlier)
    assert result[1]["ts"] == datetime.fromtimestamp(1678298313.0 - 60, tz=timezone.utc)
    assert result[1]["Grid"] == 7494425954.0
    assert result[1]["Voltage"] == 120000.5  # 120000500 * 0.001

    # Verify the time parameter was passed in start:step:end format
    assert len(mock_client.calls) == 1
    method, url, params = mock_client.calls[0]
    assert method == "GET"
    assert params is not None
    assert "time" in params
    # Format: start_timestamp:step_seconds:end_timestamp
    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())
    step_sec = int(step.total_seconds())
    expected_time = f"{start_ts}:{step_sec}:{end_ts}"
    assert params["time"] == expected_time


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
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    start = datetime(2023, 3, 8, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2023, 3, 8, 13, 0, 0, tzinfo=timezone.utc)
    step = timedelta(seconds=60)

    result = await client.get_historical_counters(start, end, step)

    # Should have 4 total rows (2 from each range)
    assert len(result) == 4

    # First range rows
    assert result[0]["ts"] == datetime.fromtimestamp(1678298313.0, tz=timezone.utc)
    assert result[0]["Grid"] == 100.0
    assert result[1]["ts"] == datetime.fromtimestamp(1678298313.0 - 60, tz=timezone.utc)
    assert result[1]["Grid"] == 200.0

    # Second range rows with different delta
    assert result[2]["ts"] == datetime.fromtimestamp(1678298500.0, tz=timezone.utc)
    assert result[2]["Grid"] == 300.0
    assert result[3]["ts"] == datetime.fromtimestamp(
        1678298500.0 - 3600, tz=timezone.utc
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
    mock_client.add_get_handler("/api/register", register_info_response)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    # Pre-populate cache
    await client.get_register_info()

    # Add handler for historical call
    mock_client.add_get_handler("/api/register", historical_response)

    start = datetime(2023, 3, 8, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2023, 3, 8, 13, 0, 0, tzinfo=timezone.utc)
    step = timedelta(seconds=60)

    result = await client.get_historical_counters(start, end, step, registers=["Grid"])

    assert len(result) == 1
    assert "Grid" in result[0]
    assert "Solar" not in result[0]  # Filtered out

    # Verify the reg parameter was passed (2 calls: one for register info, one for historical)
    assert len(mock_client.calls) == 2
    method, url, params = mock_client.calls[1]  # Second call is the filtered historical
    assert method == "GET"
    assert params is not None
    assert "reg" in params
    assert "17" in params["reg"]  # Grid has idx=17 (format may be none+17 or 17)
    assert "time" in params
    # Format: start_timestamp:step_seconds:end_timestamp
    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())
    step_sec = int(step.total_seconds())
    expected_time = f"{start_ts}:{step_sec}:{end_ts}"
    assert params["time"] == expected_time


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
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    start = datetime(2023, 3, 8, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2023, 3, 8, 13, 0, 0, tzinfo=timezone.utc)
    step = timedelta(seconds=60)

    result = await client.get_historical_counters(start, end, step, max_rows=2)

    # Should only return 2 rows as limited by max_rows
    assert len(result) == 2

    # Verify the max-rows parameter was passed
    assert len(mock_client.calls) == 1
    method, url, params = mock_client.calls[0]
    assert method == "GET"
    assert params is not None
    assert "max-rows" in params
    assert params["max-rows"] == "2"
    assert "time" in params
    # Format: start_timestamp:step_seconds:end_timestamp
    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())
    step_sec = int(step.total_seconds())
    expected_time = f"{start_ts}:{step_sec}:{end_ts}"
    assert params["time"] == expected_time


@pytest.mark.asyncio
async def test_get_historical_counters_unknown_register():
    """Test that requesting an unknown register raises EgaugeUnknownRegisterError."""
    register_info_response = {
        "ts": "1678330813.000",
        "registers": [
            {"name": "Grid", "type": "P", "idx": 17, "did": 0},
            {"name": "Solar", "type": "P", "idx": 18, "did": 1},
        ],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", register_info_response)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    # Pre-populate cache
    await client.get_register_info()

    start = datetime(2023, 3, 8, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2023, 3, 8, 13, 0, 0, tzinfo=timezone.utc)
    step = timedelta(seconds=60)

    # Try to get historical data for an unknown register
    with pytest.raises(
        EgaugeUnknownRegisterError, match="Unknown register Nonexistent"
    ):
        await client.get_historical_counters(
            start, end, step, registers=["Nonexistent"]
        )


@pytest.mark.asyncio
async def test_get_historical_counters_missing_name_field():
    """Test that missing name field raises EgaugeParsingException."""
    response_data = {
        "registers": [{"type": "P", "idx": 17}],  # No name field
        "ranges": [{"ts": "1678298313.000", "delta": 60, "rows": [["100"]]}],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    start = datetime(2023, 3, 8, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2023, 3, 8, 13, 0, 0, tzinfo=timezone.utc)
    step = timedelta(seconds=60)

    # Should raise exception since name field is missing
    with pytest.raises(EgaugeParsingException, match="Register missing 'name' field"):
        await client.get_historical_counters(start, end, step)


@pytest.mark.asyncio
async def test_get_historical_counters_missing_type_field():
    """Test that missing type field raises EgaugeParsingException."""
    response_data = {
        "registers": [{"name": "Grid", "idx": 17}],  # No type field
        "ranges": [{"ts": "1678298313.000", "delta": 60, "rows": [["100"]]}],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    start = datetime(2023, 3, 8, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2023, 3, 8, 13, 0, 0, tzinfo=timezone.utc)
    step = timedelta(seconds=60)

    # Should raise exception since type field is missing
    with pytest.raises(
        EgaugeParsingException, match="Register 'Grid' missing 'type' field"
    ):
        await client.get_historical_counters(start, end, step)


# Phase 5: get_current_counters() tests
@pytest.mark.asyncio
async def test_get_current_counters_all_registers():
    """Test fetching current counter values for all registers."""
    response_data = {
        "registers": [
            {"name": "Grid", "type": "P", "idx": 17},
            {"name": "Voltage", "type": "V", "idx": 18},
        ],
        "ranges": [
            {
                "ts": "1678298313.000",
                "delta": 1,
                "rows": [
                    [
                        "7494425049",
                        "120000000",
                    ]  # Grid=7494425049 W·s, Voltage=120000.0 V·s
                ],
            }
        ],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    counters = await client.get_current_counters()

    assert len(counters) == 2
    assert counters["Grid"] == 7494425049.0  # quantum=1.0 for Power
    assert counters["Voltage"] == 120000.0  # 120000000 * 0.001 for Voltage


@pytest.mark.asyncio
async def test_get_current_counters_uses_time_now_parameter():
    """Test that current counters request includes time=now parameter."""
    response_data = {
        "registers": [{"name": "Grid", "type": "P", "idx": 17}],
        "ranges": [{"ts": "1678298313.000", "delta": 1, "rows": [["100"]]}],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    counters = await client.get_current_counters()

    # Verify counters were returned correctly
    assert len(counters) == 1
    assert counters["Grid"] == 100.0

    # Verify the time parameter was passed with value "now"
    assert len(mock_client.calls) == 1
    method, url, params = mock_client.calls[0]
    assert method == "GET"
    assert params is not None
    assert "time" in params
    assert params["time"] == "now"


@pytest.mark.asyncio
async def test_get_current_counters_uses_bearer_auth():
    """Test that get_current_counters uses Bearer token authentication."""
    response_data = {
        "registers": [{"name": "Grid", "type": "P", "idx": 17}],
        "ranges": [{"ts": "1678298313.000", "delta": 1, "rows": [["100"]]}],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    await client.get_current_counters()

    # Verify auth manager was called
    assert mock_auth.get_token_calls == 1


@pytest.mark.asyncio
async def test_get_current_counters_with_register_filter():
    """Test filtering current counters to specific registers."""
    # First response: register info for mapping names to indices
    register_info_response = {
        "ts": "1678330813.000",
        "registers": [
            {"name": "Grid", "type": "P", "idx": 17, "did": 0},
            {"name": "Solar", "type": "P", "idx": 18, "did": 1},
            {"name": "Total", "type": "P", "idx": 19},
        ],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", register_info_response)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    # Pre-populate cache by calling get_register_info
    await client.get_register_info()

    # Now add handler for the filtered counter call
    filtered_response = {
        "registers": [{"name": "Grid", "type": "P", "idx": 17}],
        "ranges": [{"ts": "1678298313.000", "delta": 1, "rows": [["7494425049"]]}],
    }
    mock_client.add_get_handler("/api/register", filtered_response)

    counters = await client.get_current_counters(registers=["Grid"])

    # Should only return Grid with counter value
    assert len(counters) == 1
    assert counters["Grid"] == 7494425049.0

    # Verify the reg parameter was passed (2 calls: one for register info, one for counters)
    assert len(mock_client.calls) == 2
    method, url, params = mock_client.calls[1]  # Second call is the filtered counters
    assert method == "GET"
    assert params is not None
    assert "reg" in params
    assert "17" in params["reg"]  # Grid has idx=17 (format may be none+17 or 17)
    assert "time" in params
    assert params["time"] == "now"


@pytest.mark.asyncio
async def test_get_current_counters_unknown_register():
    """Test that requesting an unknown register raises EgaugeUnknownRegisterError."""
    register_info_response = {
        "ts": "1678330813.000",
        "registers": [
            {"name": "Grid", "type": "P", "idx": 17, "did": 0},
            {"name": "Solar", "type": "P", "idx": 18, "did": 1},
        ],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", register_info_response)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    # Pre-populate cache
    await client.get_register_info()

    # Try to get counters for an unknown register
    with pytest.raises(
        EgaugeUnknownRegisterError, match="Unknown register Nonexistent"
    ):
        await client.get_current_counters(registers=["Nonexistent"])


@pytest.mark.asyncio
async def test_get_current_counters_missing_name_field():
    """Test that missing name field raises EgaugeParsingException."""
    response_data = {
        "registers": [{"type": "P", "idx": 17}],  # No name field
        "ranges": [{"ts": "1678298313.000", "delta": 1, "rows": [["100"]]}],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    # Should raise exception since name field is missing
    with pytest.raises(EgaugeParsingException, match="Register missing 'name' field"):
        await client.get_current_counters()


@pytest.mark.asyncio
async def test_get_current_counters_missing_type_field():
    """Test that missing type field raises EgaugeParsingException."""
    response_data = {
        "registers": [{"name": "Grid", "idx": 17}],  # No type field
        "ranges": [{"ts": "1678298313.000", "delta": 1, "rows": [["100"]]}],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    # Should raise exception since type field is missing
    with pytest.raises(
        EgaugeParsingException, match="Register 'Grid' missing 'type' field"
    ):
        await client.get_current_counters()


@pytest.mark.asyncio
async def test_get_current_counters_quantum_conversion():
    """Test that quantum conversion is applied correctly for different register types."""
    response_data = {
        "registers": [
            {"name": "Grid", "type": "P", "idx": 17},  # Power: quantum=1.0
            {"name": "Voltage", "type": "V", "idx": 18},  # Voltage: quantum=0.001
        ],
        "ranges": [
            {
                "ts": "1678298313.000",
                "delta": 1,
                "rows": [["5000", "240000"]],  # Raw values
            }
        ],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    counters = await client.get_current_counters()

    # Grid (Power): 5000 * 1.0 = 5000.0
    assert counters["Grid"] == 5000.0
    # Voltage: 240000 * 0.001 = 240.0
    assert counters["Voltage"] == 240.0


@pytest.mark.asyncio
async def test_get_current_counters_missing_ranges():
    """Test that missing ranges array raises EgaugeParsingException."""
    response_data = {
        "registers": [{"name": "Grid", "type": "P", "idx": 17}],
        # No ranges field
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    with pytest.raises(
        EgaugeParsingException,
        match="Response missing 'ranges' array or array is empty",
    ):
        await client.get_current_counters()


@pytest.mark.asyncio
async def test_get_current_counters_empty_ranges():
    """Test that empty ranges array raises EgaugeParsingException."""
    response_data = {
        "registers": [{"name": "Grid", "type": "P", "idx": 17}],
        "ranges": [],  # Empty array
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    with pytest.raises(
        EgaugeParsingException,
        match="Response missing 'ranges' array or array is empty",
    ):
        await client.get_current_counters()


@pytest.mark.asyncio
async def test_get_current_counters_multiple_ranges():
    """Test that multiple ranges raises EgaugeParsingException."""
    response_data = {
        "registers": [{"name": "Grid", "type": "P", "idx": 17}],
        "ranges": [
            {"ts": "1678298313.000", "delta": 1, "rows": [["100"]]},
            {"ts": "1678298314.000", "delta": 1, "rows": [["200"]]},  # Unexpected
        ],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    with pytest.raises(
        EgaugeParsingException, match="Expected 1 range for time=now query, got 2"
    ):
        await client.get_current_counters()


@pytest.mark.asyncio
async def test_get_current_counters_missing_rows_field():
    """Test that missing rows field raises EgaugeParsingException."""
    response_data = {
        "registers": [{"name": "Grid", "type": "P", "idx": 17}],
        "ranges": [
            {"ts": "1678298313.000", "delta": 1}  # No rows field
        ],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    with pytest.raises(
        EgaugeParsingException, match="Range object missing 'rows' field"
    ):
        await client.get_current_counters()


@pytest.mark.asyncio
async def test_get_current_counters_empty_rows():
    """Test that empty rows array raises EgaugeParsingException."""
    response_data = {
        "registers": [{"name": "Grid", "type": "P", "idx": 17}],
        "ranges": [{"ts": "1678298313.000", "delta": 1, "rows": []}],  # Empty rows
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    with pytest.raises(EgaugeParsingException, match="Range 'rows' array is empty"):
        await client.get_current_counters()


@pytest.mark.asyncio
async def test_get_current_counters_multiple_rows():
    """Test that multiple rows raises EgaugeParsingException."""
    response_data = {
        "registers": [{"name": "Grid", "type": "P", "idx": 17}],
        "ranges": [
            {
                "ts": "1678298313.000",
                "delta": 1,
                "rows": [["100"], ["200"]],  # Multiple rows unexpected for time=now
            }
        ],
    }

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/register", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    with pytest.raises(
        EgaugeParsingException, match="Expected 1 row for time=now query, got 2"
    ):
        await client.get_current_counters()


# Phase 6: get_user_rights() tests
@pytest.mark.asyncio
async def test_get_user_rights_success():
    """Test successfully fetching user rights."""
    response_data = {"usr": "owner", "rights": ["save", "ctrl"]}

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/auth/rights", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    user_rights = await client.get_user_rights()

    assert user_rights.usr == "owner"
    assert user_rights.rights == ["save", "ctrl"]


@pytest.mark.asyncio
async def test_get_user_rights_empty_rights():
    """Test user with no special rights."""
    response_data = {"usr": "guest", "rights": []}

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/auth/rights", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    user_rights = await client.get_user_rights()

    assert user_rights.usr == "guest"
    assert user_rights.rights == []


@pytest.mark.asyncio
async def test_get_user_rights_uses_bearer_auth():
    """Test that get_user_rights uses Bearer token authentication."""
    response_data = {"usr": "owner", "rights": ["save"]}

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/auth/rights", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    await client.get_user_rights()

    # Verify auth manager was called
    assert mock_auth.get_token_calls == 1


@pytest.mark.asyncio
async def test_get_user_rights_missing_usr_field():
    """Test that missing usr field raises EgaugeParsingException."""
    response_data = {"rights": ["save", "ctrl"]}  # No usr field

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/auth/rights", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    # Should raise exception since usr field is missing
    with pytest.raises(
        EgaugeParsingException, match="User rights response missing 'usr' field"
    ):
        await client.get_user_rights()


@pytest.mark.asyncio
async def test_get_user_rights_missing_rights_field():
    """Test that missing rights field raises EgaugeParsingException."""
    response_data = {"usr": "owner"}  # No rights field

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/auth/rights", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    # Should raise exception since rights field is missing
    with pytest.raises(
        EgaugeParsingException, match="User rights response missing 'rights' field"
    ):
        await client.get_user_rights()


# Phase 6: get_device_serial_number() tests
@pytest.mark.asyncio
async def test_get_device_serial_number_success():
    """Test successfully fetching device serial number."""
    response_data = {"result": "G10400", "error": None}

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/sys/sn", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    serial_number = await client.get_device_serial_number()

    assert serial_number == "G10400"


@pytest.mark.asyncio
async def test_get_device_serial_number_alphanumeric():
    """Test serial number with letters and numbers."""
    response_data = {"result": "0Y0035", "error": None}

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/sys/sn", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    serial_number = await client.get_device_serial_number()

    assert serial_number == "0Y0035"


@pytest.mark.asyncio
async def test_get_device_serial_number_uses_bearer_auth():
    """Test that get_device_serial_number uses Bearer token authentication."""
    response_data = {"result": "G10400", "error": None}

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/sys/sn", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    await client.get_device_serial_number()

    # Verify auth manager was called
    assert mock_auth.get_token_calls == 1


@pytest.mark.asyncio
async def test_get_device_serial_number_missing_result_field():
    """Test that missing result field raises EgaugeParsingException."""
    response_data = {"error": None}  # No result field

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/sys/sn", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    # Should raise exception since result field is missing
    with pytest.raises(
        EgaugeParsingException, match="Serial number response missing 'result' field"
    ):
        await client.get_device_serial_number()


@pytest.mark.asyncio
async def test_get_device_serial_number_permission_denied():
    """Test that 401 with valid auth raises EgaugePermissionError.

    Scenario: User is authenticated but lacks permission to read device settings.
    - /api/sys/sn returns 401 (permission denied)
    - /api/auth/rights succeeds (user is authenticated)
    - Should raise EgaugePermissionError (not EgaugeAuthenticationError)
    """
    # Mock client that returns 401 for serial number but 200 for rights
    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/sys/sn", {}, status_code=401)
    mock_client.add_get_handler("/api/auth/rights", {"usr": "guest", "rights": []})
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "guest", "pass", mock_client, mock_auth
    )

    # Should raise permission error, not authentication error
    with pytest.raises(
        EgaugePermissionError,
        match="User 'guest' lacks permission to read device settings",
    ):
        await client.get_device_serial_number()


@pytest.mark.asyncio
async def test_get_device_serial_number_authentication_failed():
    """Test that 401 with invalid auth raises EgaugeAuthenticationError.

    Scenario: Invalid credentials - both endpoints return 401.
    - /api/sys/sn returns 401 (authentication failed)
    - /api/auth/rights also returns 401 (credentials truly invalid)
    - Should raise EgaugeAuthenticationError
    """
    # Mock client that returns 401 for both endpoints
    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/sys/sn", {}, status_code=401)
    mock_client.add_get_handler("/api/auth/rights", {}, status_code=401)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "baduser", "badpass", mock_client, mock_auth
    )

    # Should raise authentication error
    with pytest.raises(
        EgaugeAuthenticationError, match="Authentication failed after token refresh"
    ):
        await client.get_device_serial_number()


# Phase 7: get_hostname() tests
@pytest.mark.asyncio
async def test_get_hostname_success():
    """Test successfully fetching device hostname."""
    response_data = {"result": "eGauge42", "error": None}

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/config/net/hostname", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    hostname = await client.get_hostname()

    assert hostname == "eGauge42"


@pytest.mark.asyncio
async def test_get_hostname_with_dashes():
    """Test hostname with dashes (per API spec: ASCII letters, digits, dashes)."""
    response_data = {"result": "eGauge-Device-123", "error": None}

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/config/net/hostname", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    hostname = await client.get_hostname()

    assert hostname == "eGauge-Device-123"


@pytest.mark.asyncio
async def test_get_hostname_uses_bearer_auth():
    """Test that get_hostname uses Bearer token authentication."""
    response_data = {"result": "eGauge42", "error": None}

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/config/net/hostname", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    await client.get_hostname()

    # Verify auth manager was called
    assert mock_auth.get_token_calls == 1


@pytest.mark.asyncio
async def test_get_hostname_missing_result_field():
    """Test that missing result field raises EgaugeParsingException."""
    response_data = {"error": None}  # No result field

    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/config/net/hostname", response_data)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "owner", "pass", mock_client, mock_auth
    )

    # Should raise exception since result field is missing
    with pytest.raises(
        EgaugeParsingException, match="Hostname response missing 'result' field"
    ):
        await client.get_hostname()


@pytest.mark.asyncio
async def test_get_hostname_permission_denied():
    """Test that 401 with valid auth raises EgaugePermissionError.

    Scenario: User is authenticated but lacks permission to read network configuration.
    - /api/config/net/hostname returns 401 (permission denied)
    - /api/auth/rights succeeds (user is authenticated)
    - Should raise EgaugePermissionError (not EgaugeAuthenticationError)
    """
    # Mock client that returns 401 for hostname but 200 for rights
    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/config/net/hostname", {}, status_code=401)
    mock_client.add_get_handler("/api/auth/rights", {"usr": "guest", "rights": []})
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "guest", "pass", mock_client, mock_auth
    )

    # Should raise permission error, not authentication error
    with pytest.raises(
        EgaugePermissionError,
        match="User 'guest' lacks permission to read device configuration",
    ):
        await client.get_hostname()


@pytest.mark.asyncio
async def test_get_hostname_authentication_failed():
    """Test that 401 with invalid auth raises EgaugeAuthenticationError.

    Scenario: Invalid credentials - both endpoints return 401.
    - /api/config/net/hostname returns 401 (authentication failed)
    - /api/auth/rights also returns 401 (credentials truly invalid)
    - Should raise EgaugeAuthenticationError
    """
    # Mock client that returns 401 for both endpoints
    mock_client = MultiResponseClient()
    mock_client.add_get_handler("/api/config/net/hostname", {}, status_code=401)
    mock_client.add_get_handler("/api/auth/rights", {}, status_code=401)
    mock_auth = MockAuthManager()

    client = EgaugeJsonClient(
        "https://egauge12345.local", "baduser", "badpass", mock_client, mock_auth
    )

    # Should raise authentication error
    with pytest.raises(
        EgaugeAuthenticationError, match="Authentication failed after token refresh"
    ):
        await client.get_hostname()
