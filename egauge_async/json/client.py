import datetime
from dataclasses import dataclass

import httpx

from egauge_async.json.models import RegisterType


@dataclass
class RegisterInfo:
    name: str
    type: RegisterType
    idx: int
    did: int


class EgaugeJsonClient:
    def __init__(
        self, base_url: str, username: str, password: str, client: httpx.AsyncClient
    ):
        pass

    def get_register_info(self) -> dict[str, RegisterInfo]:
        pass

    def get_current_measurements(
        self, registers: list[str] | None = None
    ) -> dict[str, float]:
        """
        Gets the current measurements

        Args:
            registers: list of registers to query. If `None`, returns values for all registers.

        Returns:
            A dict mapping register name to measurement
        """
        pass

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
