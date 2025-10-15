import datetime
from dataclasses import dataclass

import httpx

from egauge_async.json.auth import JwtAuthManager
from egauge_async.json.models import RegisterType


@dataclass
class RegisterInfo:
    name: str
    type: RegisterType
    idx: int
    did: int | None = None


class EgaugeJsonClient:
    def __init__(
        self, base_url: str, username: str, password: str, client: httpx.AsyncClient
    ):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.client = client
        self.auth = JwtAuthManager(base_url, username, password, client)
        self._register_cache: dict[str, RegisterInfo] | None = None

    async def _get_with_auth(
        self, url: str, params: dict[str, str] | None = None
    ) -> httpx.Response:
        """Make authenticated GET request with JWT bearer token."""
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
            indices = [reg_info[name].idx for name in registers if name in reg_info]

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

    def get_historical_counters(
        self,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
        step: datetime.timedelta,
        registers: list[str] | None = None,
        max_rows: int | None = None,
    ) -> list[dict[str, datetime.datetime | float]]:
        """
        Gets historical values of register counters

        Returned values contain the eGauge's cumulative counter at a given timestamp, not the
        measured value. The eGauge internally increments each counter by the measured value every second,
        so the counter contains an integral over time of the measurements. The units of this value are
        `unit * seconds` (for example power registers will return values in Watt * seconds).

        Args:
            start_time: earliest time to return
            end_time: latest time to return
            step: time interval between consecutive entries
            registers: list of registers to query. If `None`, returns values for all registers.
            max_rows: maximum number of rows to return (requires eGauge firmware >= 4.7)

        Returns:
            A list of data rows. Each row is a dict containing a "ts" key with the entry's timestamp
            as well as a key for each register. Register values contain the _cumulative counter_ of the
            corresponding eGauge register at that timestamp.
        """

        pass
