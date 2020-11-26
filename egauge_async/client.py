import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Iterable
from xml.etree import ElementTree

import httpx

from egauge_async.exceptions import EgaugeHTTPErrorCode, EgaugeParsingException
from egauge_async.data_models import DataRow, RegisterData, TimeInterval
from egauge_async.utils import create_query_string, QueryParam


logger = logging.getLogger(__name__)


class EgaugeClient(object):
    """Provides `async` read access to an Egauge device using the [documented XML API]_

    Args:
        uri: Base URI for the Egauge device, e.g. "http://egauge12345.local". Both HTTP
            and HTTPS are supported.
        username: Username for authentication if enabled on the Egauge
        password: Password for authentication if enabled on the Egauge

    .. [documented XML API] https://kb.egauge.net/books/egauge-meter-communication/page/xml-api
    """

    def __init__(
        self, uri: str, username: Optional[str] = None, password: Optional[str] = None
    ):
        self.uri = uri
        auth: Optional[httpx.DigestAuth] = None
        if username is not None and password is not None:
            auth = httpx.DigestAuth(username=username, password=password)

        # turn off SSL verification. eGauges use self-signed certs
        self.client = httpx.AsyncClient(auth=auth, verify=False)

    async def close(self):
        """Clean up the HTTP session"""
        await self.client.aclose()

    async def get_instantaneous_data(self) -> DataRow:
        """Get a current snapshot of data on the eGauge.

        Returned information includes current cumulative values for each register
        along with rate of change over the last second.

        Returns:
            A single row of data
        """
        url = self.uri + "/cgi-bin/egauge"
        params: List[QueryParam] = ["inst", "tot"]
        response = await self.client.get(url + create_query_string(params))
        if response.status_code != 200:
            raise EgaugeHTTPErrorCode(response.status_code)
        return self._parse_instantaneous_data(response.text)

    @staticmethod
    def _parse_instantaneous_data(xml: str) -> DataRow:
        """Parse XML response from the instantaneous endpoint"""
        logger.debug(f"Parsing instantaneous XML data:\n{xml}")
        root = ElementTree.fromstring(xml)
        ts_elem = root.find("ts")
        if ts_elem is None:
            raise EgaugeParsingException("Could not find element 'ts'")
        ts_str = ts_elem.text
        if ts_str is None:
            raise EgaugeParsingException("Empty timestamp element")
        ts = datetime.fromtimestamp(int(ts_str))
        register_data: Dict[str, RegisterData] = {}
        rows = root.findall("r")
        for r in rows:
            try:
                name = r.attrib["n"]
            except KeyError:
                raise EgaugeParsingException(
                    'Could not find attribute "n" for element "r"'
                )
            try:
                register_type = r.attrib["t"]
            except KeyError:
                raise EgaugeParsingException(
                    'Could not find attribute "t" for element "r"'
                )

            value_elem = r.find("v")
            if value_elem is None:
                raise EgaugeParsingException(
                    'Could not find element "v" inside element "r"'
                )
            value_str = value_elem.text
            if value_str is None:
                raise EgaugeParsingException('Element "v" is empty')
            value = int(value_str)

            rate: Optional[float] = None
            rate_elem = r.find("i")
            if rate_elem is not None:
                rate_str = rate_elem.text
                if rate_str is None:
                    raise EgaugeParsingException('Element "i" is empty')
                rate = float(rate_str)

            register_data[name] = RegisterData(register_type, value, rate)
        return DataRow(timestamp=ts, registers=register_data)

    async def get_historical_data(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        interval: Optional[TimeInterval] = None,
        skip_rows: Optional[int] = None,
        timestamps: Optional[Iterable[datetime]] = None,
        max_rows: Optional[int] = None,
    ) -> List[DataRow]:
        """Get stored historical data

        There are a variety of options that control what data is returned.

        Args:
            start: Oldest timestamp to return data for
            end: Newest timestamp to return data for
            interval: Time interval for this query. This controls the time interval
                between returned data rows. Even if only a single data row is retrieved,
                the timestamp of the requested row will be rounded to the nearest even
                value of this interval
            skip_rows: Number of time intervals to skip between rows. E.g. if
                `interval=TimeInterval.DAY`, set `skip_rows=6` to get one row per week.
            timestamps: Iterable of timestamps to request data for. If specified, most other
                paramters are ignored. Note that the Egauge stores older data at a less granular
                level, so the returned data will often not exactly match the requested timestamp.
                Instead, the nearest stored data point will be returned.
            max_rows: Maximum number of rows to return. Note that this sometimes interacts strangely
                with other arguments, leading to less rows returned that expected. This is a limitation
                of the Egauge API.

        Returns:
            The requested data, ordered from newest to oldest
        """
        url = self.uri + "/cgi-bin/egauge-show"
        params: List[QueryParam] = ["a"]
        if start is not None:
            params.append(("t", str(int(start.timestamp()))))
        if end is not None:
            params.append(("f", str(int(end.timestamp()))))
        if interval is not None:
            if interval == TimeInterval.SECOND:
                params.append("S")
            elif interval == TimeInterval.MINUTE:
                params.append("m")
            elif interval == TimeInterval.HOUR:
                params.append("h")
            elif interval == TimeInterval.DAY:
                params.append("d")
            else:
                raise ValueError(f"Unrecognized value {interval} for interval")
        if skip_rows is not None:
            params.append(("s", str(skip_rows)))
        if timestamps is not None:
            ts = ",".join(
                [str(int(t.timestamp())) for t in sorted(timestamps, reverse=True)]
            )
            params.append(("T", ts))
        if max_rows is not None:
            params.append(("n", str(max_rows)))
        response = await self.client.get(url + create_query_string(params))
        if response.status_code != 200:
            raise EgaugeHTTPErrorCode(response.status_code)
        return self._parse_historical_data(response.text)

    @staticmethod
    def _parse_historical_data(xml: str) -> List[DataRow]:
        """Parse the XML response returned by the stored data query"""
        logger.debug(f"Parsing historical XML data: {xml}")
        root = ElementTree.fromstring(xml)
        rows: List[DataRow] = []
        col_names: List[str] = []
        col_types: List[str] = []
        for data_element in root.findall("data"):
            try:
                start_ts = datetime.fromtimestamp(
                    int(data_element.attrib["time_stamp"], base=16)
                )
            except KeyError:
                raise EgaugeParsingException(
                    'Could not find element "time_stamp" for element "data"'
                )
            try:
                delta = timedelta(seconds=int(data_element.attrib["time_delta"]))
            except KeyError:
                raise EgaugeParsingException(
                    'Could not find element "time_delta" for element "data"'
                )

            if len(col_names) == 0:
                for cname in data_element.findall("cname"):
                    cname_str = cname.text
                    if cname_str is None:
                        raise EgaugeParsingException('"cname" element is empty')
                    col_names.append(cname_str)
                    try:
                        register_type = cname.attrib["t"]
                    except KeyError:
                        raise EgaugeParsingException(
                            'Could not find attribute "t" for element "cname"'
                        )
                    col_types.append(register_type)

            if len(col_names) == 0:
                raise EgaugeParsingException("Could not find column names in response")

            for row_num, row in enumerate(data_element.findall("r")):
                ts = start_ts - row_num * delta
                registers = {}
                for i, col in enumerate(row.findall("c")):
                    col_str = col.text
                    if col_str is None:
                        raise EgaugeParsingException('"c" element is empty')
                    registers[col_names[i]] = RegisterData(col_types[i], int(col_str))
                rows.append(DataRow(timestamp=ts, registers=registers))

        return rows

    async def get_instantaneous_registers(self) -> Dict[str, str]:
        """Get names and register type codes of instantaneous registers

        Register type codes are documented in the [XML API documentation]_

        Note that for computed registers, the names can differ from those returned
        by `get_historical_registers`. E.g. the total usage register is called
        "Total Usage" when queried through the instantaneous endpoint, but "use" when
        queried through the historical endpoint

        Returns:
            dictionary mapping register name to register type code

        .. [XML API documentation] https://kb.egauge.net/books/egauge-meter-communication/page/xml-api
        """
        if not hasattr(self, "_inst_registers"):
            data = await self.get_instantaneous_data()
            self._inst_registers = {
                k: v.register_type_code for k, v in data.registers.items()
            }
        return self._inst_registers

    async def get_historical_registers(self) -> Dict[str, str]:
        """Get names and register type codes of historical registers

        Register type codes are documented in the [XML API documentation]_

        Note that for computed registers, the names can differ from those returned
        by `get_instantaneous_registers`. E.g. the total usage register is called
        "Total Usage" when queried through the instantaneous endpoint, but "use" when
        queried through the historical endpoint

        Returns:
            dictionary mapping register name to register type code

        .. [XML API documentation] https://kb.egauge.net/books/egauge-meter-communication/page/xml-api
        """
        if not hasattr(self, "_hist_registers"):
            data = await self.get_historical_data(
                max_rows=1, interval=TimeInterval.SECOND
            )
            self._hist_registers = {
                k: v.register_type_code for k, v in data[0].registers.items()
            }
        return self._hist_registers

    async def get_current_rates(self) -> Dict[str, float]:
        """Get current rates for all registers

        Returns:
            dict of register names to rates
        """
        data = await self.get_instantaneous_data()
        return {k: r.rate for k, r in data.registers.items() if r.rate is not None}

    async def get_interval_changes(
        self,
        since: datetime,
        interval: TimeInterval,
        interval_multiplier: int = 1,
    ) -> List[Dict[str, Any]]:
        """Get change in register values over regular intervals, e.g. hourly, daily, or weekly.

        Args:
            since: start timestamp of first measurement interval
            interval: time interval requested
            interval_multiplier: multiplier for interval. For example, to retrieve
                usage at 15 minute intervals, pass `interval=TimePeriod.MINUTE`
                and `interval_multiplier=15`

        Returns:
            A list of data points. Each item in the list contains the keys:
                - `start_ts`: timestamp at the start of the measurement interval
                - `end_ts`: timestamp at the end of the measurement interval
                - `measurements`: a dictionary containing a the change in value
                    of each register over the interval

        Examples:
            Get weekly change for last 4 weeks. For power registers, this corresponds
            to energy in Watt-seconds (= Joules) consumed each week.

            Note that `start` is *5* weeks ago::

                c = EgaugeClient(...)
                data = await c.get_interval_usage(
                    start=datetime.now() - timedelta(weeks=5)
                    interval=TimeInterval.DAY,
                    interval_multiplier=7,
                )
        """
        data = await self.get_historical_data(
            start=since,
            interval=interval,
            skip_rows=interval_multiplier - 1,
        )
        data.sort(key=lambda d: d.timestamp)
        output = []
        for i in range(len(data) - 1):
            start = data[i].timestamp
            end = data[i + 1].timestamp
            start_vals = {k: r.value for k, r in data[i].registers.items()}
            end_vals = {k: r.value for k, r in data[i + 1].registers.items()}
            meas = {k: end_vals[k] - start_vals[k] for k in end_vals.keys()}
            output.append({"start_ts": start, "end_ts": end, "measurements": meas})
        return output

    async def get_hourly_changes(self, num_hours: int):
        """Get hourly register changes

        E.g. for a power register, this corresponds to hourly energy usage in Joules

        Args:
            num_hours: number of hours of data to return

        Returns:
            A list of data points. Each item in the list contains the keys:
                - `start_ts`: timestamp at the start of the hour
                - `end_ts`: timestamp at the end of the hour
                - `measurements`: a dictionary containing a the change in value
                    of each register over the hour
        """

        since = datetime.now() - timedelta(hours=num_hours + 1)
        return await self.get_interval_changes(since=since, interval=TimeInterval.HOUR)

    async def get_daily_changes(self, num_days: int):
        """Get daily register changes

        E.g. for a power register, this corresponds to daily energy usage in Joules

        Args:
            num_days: number of days of data to return

        Returns:
            A list of data points. Each item in the list contains the keys:
                - `start_ts`: timestamp at the start of the day
                - `end_ts`: timestamp at the end of the day
                - `measurements`: a dictionary containing a the change in value
                    of each register over the day
        """
        since = datetime.now() - timedelta(days=num_days + 1)
        return await self.get_interval_changes(since=since, interval=TimeInterval.DAY)

    async def get_weekly_changes(self, num_weeks: int):
        """Get weekly register changes

        E.g. for a power register, this corresponds to weekly energy usage in Joules

        Args:
            num_weeks: number of weeks of data to return

        Returns:
            A list of data points. Each item in the list contains the keys:
                - `start_ts`: timestamp at the start of the week
                - `end_ts`: timestamp at the end of the week
                - `measurements`: a dictionary containing a the change in value
                    of each register over the week
        """
        since = datetime.now() - timedelta(weeks=num_weeks + 1)
        return await self.get_interval_changes(
            since=since, interval=TimeInterval.DAY, interval_multiplier=7
        )
