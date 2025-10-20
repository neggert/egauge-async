from datetime import datetime as dt, timedelta, timezone

import httpx

from egauge_async.json.auth import JwtAuthManager
from egauge_async.json.models import RegisterType, RegisterInfo
from egauge_async.json.type_codes import get_quantum
from egauge_async.exceptions import (
    EgaugeUnknownRegisterError,
    EgaugeParsingException,
    EgaugeAuthenticationError,
)


class EgaugeJsonClient:
    """Async client for eGauge JSON API with JWT authentication.

    This client can be used as an async context manager for automatic cleanup:

        async with httpx.AsyncClient(verify=False) as http_client:
            async with EgaugeJsonClient(url, user, pwd, http_client) as client:
                data = await client.get_current_measurements()

    Note: The httpx.AsyncClient must be managed by the caller. This client
    only handles JWT token cleanup via close().
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        client: httpx.AsyncClient,
        auth: JwtAuthManager | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.client = client
        self.auth = auth or JwtAuthManager(base_url, username, password, client)
        self._register_cache: dict[str, RegisterInfo] | None = None

    async def _get_with_auth(
        self, url: str, params: dict[str, str] | None = None
    ) -> httpx.Response:
        """Make authenticated GET request with automatic token refresh.

        Handles token expiration transparently:
        1. Gets valid token (may trigger proactive refresh)
        2. Makes request with Bearer token
        3. On 401: invalidates token, re-authenticates, retries once

        Args:
            url: Full URL to request
            params: Optional query parameters

        Returns:
            HTTP response object

        Raises:
            EgaugeAuthenticationError: If authentication fails after retry
        """
        # Get valid token (may refresh proactively)
        token = await self.auth.get_token()
        headers = {"Authorization": f"Bearer {token}"}

        # Make initial request
        response = await self.client.get(url, params=params, headers=headers)

        # Handle 401 - token may be expired despite checks (clock skew, revocation, etc.)
        if response.status_code == 401:
            # Invalidate cached token and re-authenticate
            await self.auth.invalidate_token()
            token = await self.auth.get_token()
            headers = {"Authorization": f"Bearer {token}"}

            # Retry request once
            response = await self.client.get(url, params=params, headers=headers)

            # If still 401, authentication is truly failing
            if response.status_code == 401:
                raise EgaugeAuthenticationError(
                    "Authentication failed after token refresh. "
                    "Please verify your credentials."
                )

        return response

    async def get_register_info(self) -> dict[str, RegisterInfo]:
        """Get register metadata (name, type, index, database ID).

        Returns:
            Dictionary mapping register name to RegisterInfo
        """
        if self._register_cache is not None:
            return self._register_cache

        url = f"{self.base_url}/api/register"
        response = await self._get_with_auth(url)
        response.raise_for_status()

        data = response.json()
        registers: dict[str, RegisterInfo] = {}

        for reg in data.get("registers", []):
            # Validate required fields are present
            if "name" not in reg:
                raise EgaugeParsingException(
                    "Register missing 'name' field in response"
                )
            if "type" not in reg:
                raise EgaugeParsingException(
                    f"Register '{reg['name']}' missing 'type' field in response"
                )
            if "idx" not in reg:
                raise EgaugeParsingException(
                    f"Register '{reg['name']}' missing 'idx' field in response"
                )

            registers[reg["name"]] = RegisterInfo(
                name=reg["name"],
                type=RegisterType(reg["type"]),
                idx=reg["idx"],
                did=reg.get("did"),  # None for virtual registers
            )

        self._register_cache = registers
        return registers

    async def get_current_measurements(
        self, registers: list[str] | None = None
    ) -> dict[str, float]:
        """Get current instantaneous measurements (rate values).

        Args:
            registers: List of register names to query. If None, returns all registers.

        Returns:
            Dictionary mapping register name to current rate value (already in physical units)
        """
        url = f"{self.base_url}/api/register"
        params: dict[str, str] = {"rate": ""}

        # Filter to specific registers if requested
        if registers is not None and len(registers) > 0:
            # Get register info to map names to indices
            reg_info = await self.get_register_info()
            indices: list[int] = []
            for r in registers:
                if r not in reg_info:
                    raise EgaugeUnknownRegisterError(f"Unknown register {r}")
                indices.append(reg_info[r].idx)

            if indices:
                # Build reg parameter: "none+idx1+idx2+idx3"
                reg_param = "none" + "".join(f"+{idx}" for idx in indices)
                params["reg"] = reg_param

        response = await self._get_with_auth(url, params)
        response.raise_for_status()

        data = response.json()
        measurements: dict[str, float] = {}

        for reg in data.get("registers", []):
            if "name" not in reg:
                raise EgaugeParsingException(
                    "Register missing 'name' field in response"
                )
            if "rate" not in reg:
                raise EgaugeParsingException(
                    f"Register '{reg['name']}' missing 'rate' field in response"
                )
            measurements[reg["name"]] = reg["rate"]

        return measurements

    async def get_historical_counters(
        self,
        start_time: dt,
        end_time: dt,
        step: timedelta,
        registers: list[str] | None = None,
        max_rows: int | None = None,
    ) -> list[dict[str, dt | float]]:
        """Get historical cumulative counter values with quantum conversion.

        Returned values contain the eGauge's cumulative counter at a given timestamp, not the
        measured value. The eGauge internally increments each counter by the measured value every second,
        so the counter contains an integral over time of the measurements. The units of this value are
        `unit * seconds` (for example power registers will return values in Watt * seconds).

        Args:
            start_time: Earliest timestamp to return
            end_time: Latest timestamp to return
            step: Time interval between consecutive entries
            registers: List of register names to query. If None, returns all registers.
            max_rows: Maximum number of rows to return (requires firmware >= 4.7)

        Returns:
            List of data rows. Each row is a dict with:
            - "ts": datetime (timestamp)
            - Register names mapped to physical cumulative values (float, in rate_unit·seconds)
        """
        url = f"{self.base_url}/api/register"

        # Convert datetimes to Unix timestamps
        start_ts = int(start_time.timestamp())
        end_ts = int(end_time.timestamp())
        step_seconds = int(step.total_seconds())

        # Build query parameters
        params: dict[str, str] = {"time": f"{start_ts}:{step_seconds}:{end_ts}"}

        # Filter to specific registers if requested
        if registers is not None and len(registers) > 0:
            reg_info = await self.get_register_info()
            indices: list[int] = []
            for r in registers:
                if r not in reg_info:
                    raise EgaugeUnknownRegisterError(f"Unknown register {r}")
                indices.append(reg_info[r].idx)

            if indices:
                reg_param = "none" + "".join(f"+{idx}" for idx in indices)
                params["reg"] = reg_param

        if max_rows is not None:
            params["max-rows"] = str(max_rows)

        response = await self._get_with_auth(url, params)
        response.raise_for_status()

        data = response.json()

        # Extract register names and types
        registers_list = data.get("registers", [])

        # Validate required fields and extract data
        reg_names: list[str] = []
        reg_types: list[RegisterType] = []
        for r in registers_list:
            if "name" not in r:
                raise EgaugeParsingException(
                    "Register missing 'name' field in response"
                )
            if "type" not in r:
                raise EgaugeParsingException(
                    f"Register '{r['name']}' missing 'type' field in response"
                )
            reg_names.append(r["name"])
            reg_types.append(RegisterType(r["type"]))

        # Parse ranges and convert values
        result: list[dict[str, dt | float]] = []

        for range_obj in data.get("ranges", []):
            ts = float(range_obj["ts"])
            delta = range_obj["delta"]

            for i, row in enumerate(range_obj["rows"]):
                # Calculate timestamp for this row
                row_ts = dt.fromtimestamp(ts - i * delta, tz=timezone.utc)
                row_dict: dict[str, dt | float] = {"ts": row_ts}

                # Convert each value with quantum
                for j, value_str in enumerate(row):
                    raw_value = int(value_str)
                    quantum = get_quantum(reg_types[j])
                    physical_value = raw_value * quantum
                    row_dict[reg_names[j]] = physical_value

                result.append(row_dict)

        return result

    async def close(self) -> None:
        """Close the client and revoke JWT token.

        This method logs out and revokes the current JWT token. The httpx.AsyncClient
        is NOT closed as it is managed by the caller.

        This is called automatically when using the client as a context manager.
        """
        await self.auth.logout()

    async def __aenter__(self) -> "EgaugeJsonClient":
        """Enter async context manager."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit async context manager and cleanup resources."""
        await self.close()
