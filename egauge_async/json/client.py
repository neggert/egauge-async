from datetime import datetime as dt, timedelta, timezone

import httpx

from egauge_async.json.auth import JwtAuthManager
from egauge_async.json.models import RegisterType, RegisterInfo
from egauge_async.json.type_codes import get_quantum
from egauge_async.exceptions import EgaugeUnknownRegisterError


class EgaugeJsonClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        client: httpx.AsyncClient,
        auth: JwtAuthManager | None,
    ):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.client = client
        self.auth = auth or JwtAuthManager(base_url, username, password, client)
        self._register_cache: dict[str, RegisterInfo] | None = None

    async def _get_with_auth(
        self, url: str, params: dict[str, str] | None = None
    ) -> httpx.Response:
        """Make authenticated GET request with JWT bearer token."""
        # TODO: need to handle refreshing the token if it's expired
        token = await self.auth.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        return await self.client.get(url, params=params, headers=headers)

    async def get_register_info(self) -> dict[str, RegisterInfo]:
        """Get register metadata (name, type, index, database ID).

        Returns:
            Dictionary mapping register name to RegisterInfo
        """
        if self._register_cache is not None:
            return self._register_cache

        url = f"{self.base_url}/register"
        response = await self._get_with_auth(url)
        response.raise_for_status()

        data = response.json()
        registers: dict[str, RegisterInfo] = {}

        for reg in data.get("registers", []):
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
        url = f"{self.base_url}/register"
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
            if "rate" in reg:
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
        url = f"{self.base_url}/register"

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
        reg_names = [r["name"] for r in registers_list]
        reg_types = [RegisterType(r["type"]) for r in registers_list]

        # Parse ranges and convert values
        result: list[dict[str, dt | float]] = []

        for range_obj in data.get("ranges", []):
            ts = float(range_obj["ts"])
            delta = range_obj["delta"]

            for i, row in enumerate(range_obj["rows"]):
                # Calculate timestamp for this row
                row_ts = dt.fromtimestamp(ts + i * delta, tz=timezone.utc)
                row_dict: dict[str, dt | float] = {"ts": row_ts}

                # Convert each value with quantum
                for j, value_str in enumerate(row):
                    raw_value = int(value_str)
                    quantum = get_quantum(reg_types[j])
                    physical_value = raw_value * quantum
                    row_dict[reg_names[j]] = physical_value

                result.append(row_dict)

        return result
