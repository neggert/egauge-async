"""Integration tests for EgaugeJsonClient against real eGauge devices.

These tests require access to a real eGauge device and are designed to work with
any device configuration without assumptions about specific registers.

Setup:
    Set these environment variables before running:
    - EGAUGE_URL: Full URL to eGauge device (e.g., "https://egauge12345.local")
    - EGAUGE_USERNAME: Username for authentication (typically "owner")
    - EGAUGE_PASSWORD: Password for authentication

Running:
    # Run only integration tests
    uv run pytest -m integration

    # Run all tests except integration
    uv run pytest -m "not integration"

    # Run all tests including integration
    uv run pytest

Notes:
    - Tests use SSL verification disabled (eGauges use self-signed certificates)
    - Tests are read-only and should not modify device state
    - Tests auto-skip if environment variables are not set
"""

import math
import os
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
import httpx

from egauge_async.json.client import EgaugeJsonClient
from egauge_async.json.models import RegisterInfo, RegisterType
from egauge_async.exceptions import (
    EgaugeUnknownRegisterError,
    EgaugeAuthenticationError,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(scope="module")
def egauge_config():
    """Load eGauge connection details from environment variables.

    Returns:
        dict with 'url', 'username', 'password' keys

    Raises:
        pytest.skip if required environment variables are not set
    """
    url = os.environ.get("EGAUGE_URL")
    username = os.environ.get("EGAUGE_USERNAME")
    password = os.environ.get("EGAUGE_PASSWORD")

    if not all([url, username, password]):
        pytest.skip(
            "Integration tests require EGAUGE_URL, EGAUGE_USERNAME, and "
            "EGAUGE_PASSWORD environment variables"
        )

    return {"url": url, "username": username, "password": password}


@pytest_asyncio.fixture
async def http_client():
    """Create HTTP client with SSL verification disabled for self-signed certs.

    Yields:
        httpx.AsyncClient configured for eGauge devices
    """
    async with httpx.AsyncClient(verify=False) as client:
        yield client


@pytest_asyncio.fixture
async def real_client(egauge_config, http_client):
    """Create EgaugeJsonClient connected to real device.

    Args:
        egauge_config: Configuration from environment variables
        http_client: Shared HTTP client

    Yields:
        EgaugeJsonClient instance connected to real eGauge device
    """
    client = EgaugeJsonClient(
        base_url=egauge_config["url"],
        username=egauge_config["username"],
        password=egauge_config["password"],
        client=http_client,
    )
    yield client


# ============================================================================
# A. Authentication & Token Management Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auth_successful_login(real_client):
    """Test that we can successfully authenticate and get a JWT token."""
    # Trigger authentication by making an API call
    registers = await real_client.get_register_info()

    # Should successfully return data without raising authentication errors
    assert isinstance(registers, dict)
    assert len(registers) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auth_token_caching(real_client):
    """Test that JWT tokens are cached and reused across requests."""
    # First request - triggers authentication
    await real_client.get_register_info()
    first_token = (
        real_client.auth._token_state.token if real_client.auth._token_state else None
    )

    # Second request - should reuse cached token
    await real_client.get_current_measurements()
    second_token = (
        real_client.auth._token_state.token if real_client.auth._token_state else None
    )

    # Tokens should be the same (not re-authenticated)
    assert first_token is not None
    assert second_token is not None
    assert first_token == second_token


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auth_invalid_credentials(egauge_config, http_client):
    """Test that invalid credentials result in authentication error."""
    # Create client with wrong password
    client = EgaugeJsonClient(
        base_url=egauge_config["url"],
        username=egauge_config["username"],
        password="definitely_wrong_password",
        client=http_client,
    )

    # Should raise authentication error
    with pytest.raises(EgaugeAuthenticationError):
        await client.get_register_info()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auth_concurrent_requests(real_client):
    """Test that concurrent requests handle token management correctly."""
    # Make multiple concurrent requests
    tasks = [
        real_client.get_current_measurements(),
        real_client.get_register_info(),
        real_client.get_current_measurements(),
    ]

    results = await asyncio.gather(*tasks)

    # All requests should succeed
    assert len(results) == 3
    assert all(isinstance(r, dict) for r in results)


# ============================================================================
# B. Register Information Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_info_basic(real_client):
    """Test fetching register metadata and validate structure."""
    registers = await real_client.get_register_info()

    # Should return a non-empty dictionary
    assert isinstance(registers, dict)
    assert len(registers) > 0

    # Check structure of each register
    for name, info in registers.items():
        assert isinstance(name, str)
        assert len(name) > 0
        assert isinstance(info, RegisterInfo)
        assert info.name == name
        assert isinstance(info.type, RegisterType)
        assert isinstance(info.idx, int)
        assert info.idx >= 0
        # did can be None for virtual registers
        assert info.did is None or isinstance(info.did, int)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_info_caching(real_client):
    """Test that register info is cached after first fetch."""
    # First call
    registers1 = await real_client.get_register_info()

    # Cache should be populated
    assert real_client._register_cache is not None

    # Second call should return same object (from cache)
    registers2 = await real_client.get_register_info()

    assert registers1 is registers2  # Same object reference


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_info_required_fields(real_client):
    """Test that all registers have required fields populated."""
    registers = await real_client.get_register_info()

    for name, info in registers.items():
        # Name must be non-empty string
        assert isinstance(info.name, str)
        assert len(info.name) > 0

        # Type must be valid RegisterType
        assert isinstance(info.type, RegisterType)
        assert info.type.value in RegisterType._value2member_map_

        # Index must be non-negative integer
        assert isinstance(info.idx, int)
        assert info.idx >= 0


# ============================================================================
# C. Current Measurements Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_current_measurements_all(real_client):
    """Test fetching current measurements for all registers."""
    measurements = await real_client.get_current_measurements()

    # Should return non-empty dictionary
    assert isinstance(measurements, dict)
    assert len(measurements) > 0

    # Each measurement should be a valid float
    for name, rate in measurements.items():
        assert isinstance(name, str)
        assert len(name) > 0
        assert isinstance(rate, (int, float))
        assert not isinstance(rate, bool)  # bool is subclass of int


@pytest.mark.integration
@pytest.mark.asyncio
async def test_current_measurements_filtered(real_client):
    """Test fetching measurements for specific registers only."""
    # First get all registers to pick some for filtering
    all_registers = await real_client.get_register_info()
    assert len(all_registers) > 0

    # Pick first register for filtered query
    register_names = list(all_registers.keys())
    test_register = register_names[0]

    # Fetch measurements for just this register
    measurements = await real_client.get_current_measurements(registers=[test_register])

    # Should return exactly one measurement
    assert len(measurements) == 1
    assert test_register in measurements
    assert isinstance(measurements[test_register], (int, float))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_current_measurements_multiple_filtered(real_client):
    """Test fetching measurements for multiple specific registers."""
    # Get available registers
    all_registers = await real_client.get_register_info()

    # If device has at least 2 registers, test filtering multiple
    if len(all_registers) >= 2:
        register_names = list(all_registers.keys())[:2]

        measurements = await real_client.get_current_measurements(
            registers=register_names
        )

        # Should return exactly the requested registers
        assert len(measurements) == len(register_names)
        for name in register_names:
            assert name in measurements
            assert isinstance(measurements[name], (int, float))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_current_measurements_unknown_register(real_client):
    """Test that requesting unknown register raises appropriate error."""
    # First ensure cache is populated
    await real_client.get_register_info()

    # Request a register that definitely doesn't exist
    with pytest.raises(EgaugeUnknownRegisterError, match="Unknown register"):
        await real_client.get_current_measurements(
            registers=["NonexistentRegisterName_12345"]
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_current_measurements_data_validity(real_client):
    """Test that current measurement values are valid and reasonable."""
    measurements = await real_client.get_current_measurements()

    for name, rate in measurements.items():
        # Rate should be a finite number
        assert isinstance(rate, (int, float))
        assert not isinstance(rate, bool)

        # Should not be NaN or infinity
        assert math.isfinite(rate), f"Register {name} has non-finite rate: {rate}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_current_counters_all(real_client):
    """Test fetching current cumulative counter values for all registers."""
    counters = await real_client.get_current_counters()

    # Should return non-empty dictionary
    assert isinstance(counters, dict)
    assert len(counters) > 0

    # Each counter should be a valid float
    for name, value in counters.items():
        assert isinstance(name, str)
        assert len(name) > 0
        assert isinstance(value, (int, float))
        assert not isinstance(value, bool)  # bool is subclass of int


@pytest.mark.integration
@pytest.mark.asyncio
async def test_current_counters_filtered(real_client):
    """Test fetching counters for specific registers only."""
    # First get all registers to pick some for filtering
    all_registers = await real_client.get_register_info()
    assert len(all_registers) > 0

    # Pick first register for filtered query
    register_names = list(all_registers.keys())
    test_register = register_names[0]

    # Fetch counters for just this register
    counters = await real_client.get_current_counters(registers=[test_register])

    # Should return exactly one counter
    assert len(counters) == 1
    assert test_register in counters
    assert isinstance(counters[test_register], (int, float))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_current_counters_data_validity(real_client):
    """Test that current counter values are valid and reasonable."""
    counters = await real_client.get_current_counters()

    for name, value in counters.items():
        # Counter value should be a finite number
        assert isinstance(value, (int, float))
        assert not isinstance(value, bool)

        # Should not be NaN or infinity
        assert math.isfinite(value), f"Register {name} has non-finite counter: {value}"

        # Counters are cumulative, so should generally be non-negative
        # (though some registers like grid import/export can be negative)
        # Just verify it's a reasonable value (not absurdly large)
        assert abs(value) < 1e20, f"Register {name} has unreasonable counter: {value}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_current_counters_vs_measurements_consistency(real_client):
    """Test that counters and measurements return data for same registers."""
    counters = await real_client.get_current_counters()
    measurements = await real_client.get_current_measurements()

    # Both should return data for the same set of registers
    # (Though measurements might have fewer if some registers don't have rates)
    assert len(counters) > 0
    assert len(measurements) > 0

    # All registers in measurements should also be in counters
    for reg_name in measurements.keys():
        assert reg_name in counters, (
            f"Register {reg_name} has measurement but no counter"
        )


# ============================================================================
# D. Historical Data Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_historical_basic_query(real_client):
    """Test fetching recent historical data."""
    # Query last hour of data at 1-minute intervals
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=1)
    step = timedelta(minutes=1)

    result = await real_client.get_historical_counters(
        start_time=start_time, end_time=end_time, step=step, max_rows=10
    )

    # Should return a list of data rows
    assert isinstance(result, list)
    # Should have some data (up to 10 rows requested)
    assert len(result) > 0
    assert len(result) <= 10

    # Each row should have timestamp and register data
    for row in result:
        assert isinstance(row, dict)
        assert "ts" in row
        assert isinstance(row["ts"], datetime)

        # Should have at least one register value
        register_values = {k: v for k, v in row.items() if k != "ts"}
        assert len(register_values) > 0

        # All values should be floats
        for reg_name, value in register_values.items():
            assert isinstance(reg_name, str)
            assert isinstance(value, (int, float))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_historical_with_filters(real_client):
    """Test fetching historical data for specific registers."""
    # Get available registers
    all_registers = await real_client.get_register_info()
    register_names = list(all_registers.keys())[:1]  # Just one register

    # Query recent data
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=1)
    step = timedelta(minutes=5)

    result = await real_client.get_historical_counters(
        start_time=start_time,
        end_time=end_time,
        step=step,
        registers=register_names,
        max_rows=5,
    )

    # Should return data
    assert len(result) > 0

    # Each row should only contain the requested register(s) plus timestamp
    for row in result:
        assert "ts" in row
        register_values = {k: v for k, v in row.items() if k != "ts"}

        # Should only have the requested register(s)
        assert set(register_values.keys()).issubset(set(register_names))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_historical_quantum_conversion(real_client):
    """Test that historical values are properly converted from quantum units."""
    # Query recent data
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=1)
    step = timedelta(minutes=5)

    result = await real_client.get_historical_counters(
        start_time=start_time, end_time=end_time, step=step, max_rows=5
    )

    # Should return valid data
    assert len(result) > 0

    # All values should be finite numbers (proper quantum conversion)
    for row in result:
        for key, value in row.items():
            if key != "ts":
                assert isinstance(value, (int, float))
                assert math.isfinite(value), f"Non-finite value for {key}: {value}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_historical_timestamp_ordering(real_client):
    """Test that timestamps are correctly calculated and ordered."""
    # Query recent data
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=1)
    step = timedelta(minutes=5)

    result = await real_client.get_historical_counters(
        start_time=start_time, end_time=end_time, step=step, max_rows=10
    )

    assert len(result) > 0

    # Extract timestamps
    timestamps = [row["ts"] for row in result]

    # All timestamps should be datetime objects
    assert all(isinstance(ts, datetime) for ts in timestamps)

    # All timestamps should have timezone info
    assert all(ts.tzinfo is not None for ts in timestamps)

    # Timestamps should be within requested range (with some tolerance)
    for ts in timestamps:
        # Allow some tolerance for eGauge's actual data availability
        assert start_time - timedelta(hours=24) <= ts <= end_time + timedelta(hours=1)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_historical_multiple_ranges(real_client):
    """Test that multiple ranges in response are handled correctly."""
    # Query a longer time period that might span multiple ranges
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=7)
    step = timedelta(hours=1)

    result = await real_client.get_historical_counters(
        start_time=start_time, end_time=end_time, step=step, max_rows=50
    )

    # Should return data
    assert len(result) > 0

    # Each row should be valid
    for row in result:
        assert "ts" in row
        assert isinstance(row["ts"], datetime)

        # Should have at least one register value
        register_values = {k: v for k, v in row.items() if k != "ts"}
        assert len(register_values) > 0


# ============================================================================
# E. Error Handling Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_error_invalid_time_range(real_client):
    """Test handling of invalid time range (start > end)."""
    # This may or may not raise an error depending on eGauge firmware
    # but should at least not crash
    end_time = datetime.now(timezone.utc) - timedelta(days=7)
    start_time = datetime.now(timezone.utc)  # Start after end
    step = timedelta(hours=1)

    # Should either return empty list or handle gracefully
    result = await real_client.get_historical_counters(
        start_time=start_time, end_time=end_time, step=step, max_rows=10
    )

    # Result should be a list (may be empty)
    assert isinstance(result, list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_error_historical_unknown_register(real_client):
    """Test that requesting unknown register in historical query raises error."""
    # Ensure cache is populated
    await real_client.get_register_info()

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=1)
    step = timedelta(minutes=5)

    # Request non-existent register
    with pytest.raises(EgaugeUnknownRegisterError, match="Unknown register"):
        await real_client.get_historical_counters(
            start_time=start_time,
            end_time=end_time,
            step=step,
            registers=["NonexistentRegister_99999"],
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_error_token_invalidation_recovery(real_client):
    """Test that client recovers from token invalidation."""
    # Make initial request to establish token
    await real_client.get_register_info()

    # Manually invalidate token
    await real_client.auth.invalidate_token()

    # Next request should automatically re-authenticate
    measurements = await real_client.get_current_measurements()

    # Should succeed
    assert isinstance(measurements, dict)
    assert len(measurements) > 0


# ============================================================================
# F. Data Consistency Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_consistency_register_names(real_client):
    """Test that register names are consistent across different endpoints."""
    # Get register names from metadata
    register_info = await real_client.get_register_info()
    info_names = set(register_info.keys())

    # Get register names from current measurements
    measurements = await real_client.get_current_measurements()
    measurement_names = set(measurements.keys())

    # All measurement names should be in register info
    # (there might be virtual registers in measurements)
    assert measurement_names.issubset(info_names) or info_names.issubset(
        measurement_names
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_consistency_historical_vs_current(real_client):
    """Test that historical and current endpoints return same register set."""
    # Get current measurements
    current = await real_client.get_current_measurements()
    current_names = set(current.keys())

    # Get recent historical data
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=5)
    step = timedelta(minutes=1)

    historical = await real_client.get_historical_counters(
        start_time=start_time, end_time=end_time, step=step, max_rows=1
    )

    if len(historical) > 0:
        historical_names = set(k for k in historical[0].keys() if k != "ts")

        # Should have similar register sets (allowing for some variation)
        # Historical might have fewer registers depending on configuration
        assert len(current_names & historical_names) > 0


# ============================================================================
# G. User Rights and Device Serial Number Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_user_rights(real_client):
    """Test fetching authenticated user's rights/privileges."""
    user_rights = await real_client.get_user_rights()

    # Should return username
    assert isinstance(user_rights.usr, str)
    assert len(user_rights.usr) > 0

    # Should return list of rights
    assert isinstance(user_rights.rights, list)
    # Owner typically has save/ctrl rights, but list could be empty for restricted users
    for right in user_rights.rights:
        assert isinstance(right, str)
        # Common rights are "save" and "ctrl"
        assert right in ["save", "ctrl"] or len(right) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_device_serial_number(real_client):
    """Test fetching device serial number."""
    serial_number = await real_client.get_device_serial_number()

    # Should return a non-empty string
    assert isinstance(serial_number, str)
    assert len(serial_number) > 0

    # Serial numbers typically contain alphanumeric characters
    # Examples: "G10400", "0Y0035"
    assert serial_number.replace("-", "").replace("_", "").isalnum()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_rights_consistent_with_username(real_client, egauge_config):
    """Test that user rights username matches the authenticated user."""
    user_rights = await real_client.get_user_rights()

    # Username in rights should match the configured username
    assert user_rights.usr == egauge_config["username"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_serial_number_consistent_across_calls(real_client):
    """Test that serial number is consistent across multiple calls."""
    serial1 = await real_client.get_device_serial_number()
    serial2 = await real_client.get_device_serial_number()

    # Serial number should be the same every time
    assert serial1 == serial2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_hostname(real_client):
    """Test fetching device hostname."""
    hostname = await real_client.get_hostname()

    # Should return a non-empty string
    assert isinstance(hostname, str)
    assert len(hostname) > 0

    # Per API spec: hostname consists of ASCII letters, digits, and dashes only
    # Allow alphanumeric characters and dashes
    assert all(c.isalnum() or c == "-" for c in hostname), (
        f"Hostname '{hostname}' contains invalid characters. "
        f"Expected only ASCII letters, digits, and dashes."
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hostname_consistent_across_calls(real_client):
    """Test that hostname is consistent across multiple calls."""
    hostname1 = await real_client.get_hostname()
    hostname2 = await real_client.get_hostname()

    # Hostname should be the same every time
    assert hostname1 == hostname2
