import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Iterable
from urllib.parse import urlparse

import pytest

from egauge_async.client import EgaugeClient
from egauge_async.data_models import RegisterData, DataRow, TimeInterval
from egauge_async.utils import QueryParam


def assert_query_params(url: str, params: Iterable[QueryParam]) -> None:
    expected_params = set(params)

    test_params = set()
    query_string = urlparse(url).query
    param_chunks = query_string.split("&")
    for chunk in param_chunks:
        if "=" in chunk:
            kv = chunk.split("=")
            assert len(kv) == 2, f"malformed query string chunk {chunk}"
            test_params.add(tuple(kv))
        else:
            test_params.add(chunk)
    assert test_params == expected_params


def mock_parser(xml_data):
    return None


@dataclass
class MockResponse:
    text: str
    status_code: int


class MockAsyncClient(object):
    def __init__(
        self,
        url: str,
        params: Optional[Iterable[QueryParam]],
        response: str,
        status_code: int = 200,
    ):
        self.parsed_url = urlparse(url)
        self.params = params
        self.response = MockResponse(response, status_code)

    async def get(self, url: str) -> MockResponse:
        parsed = urlparse(url)
        assert parsed.scheme == self.parsed_url.scheme
        assert parsed.netloc == self.parsed_url.netloc
        assert parsed.path == self.parsed_url.path
        if self.params is not None:
            assert_query_params(url, self.params)
        return self.response


@pytest.mark.asyncio
async def test_get_instantaneous_data():
    xml_data = """<?xml version="1.0" encoding="UTF-8" ?>
        <data serial="0x7">
        <ts>1603322016</ts>
        <r t="P" n="Grid" did="0">
            <v>3232317009</v>
            <i>654</i>
        </r>
        <r t="P" n="solar" did="1">
            <v>1010807136</v>
            <i>-8</i>
        </r>
        <r t="P" n="solar+" did="2">
            <v>818295664</v>
            <i>0</i>
        </r>
        </data>
    """

    egauge = EgaugeClient("http://localhost")
    egauge.client = MockAsyncClient(
        "http://localhost/cgi-bin/egauge", ["inst", "tot"], xml_data
    )
    result = await egauge.get_instantaneous_data()

    assert result.timestamp == datetime.fromtimestamp(1603322016)
    assert result.registers == {
        "Grid": RegisterData("P", 3232317009, 654.0),
        "solar": RegisterData("P", 1010807136, -8.0),
        "solar+": RegisterData("P", 818295664, 0.0),
    }


@pytest.mark.asyncio
async def test_historical_data_start():
    dt = datetime.fromtimestamp(1603322016)

    egauge = EgaugeClient("http://localhost")
    egauge.client = MockAsyncClient(
        "http://localhost/cgi-bin/egauge-show", [("t", "1603322016"), "a"], ""
    )
    egauge._parse_historical_data = mock_parser
    await egauge.get_historical_data(start=dt)


@pytest.mark.asyncio
async def test_historical_data_end():
    dt = datetime.fromtimestamp(1603322016)

    egauge = EgaugeClient("http://localhost")
    egauge.client = MockAsyncClient(
        "http://localhost/cgi-bin/egauge-show", [("f", "1603322016"), "a"], ""
    )
    egauge._parse_historical_data = mock_parser
    await egauge.get_historical_data(end=dt)


@pytest.mark.asyncio
async def test_historical_data_specific():
    dts = [
        datetime.fromtimestamp(1603322016),
        datetime.fromtimestamp(1603322216),
    ]

    egauge = EgaugeClient("http://localhost")
    egauge.client = MockAsyncClient(
        "http://localhost/cgi-bin/egauge-show",
        [("T", "1603322216,1603322016"), "a"],
        "",
    )
    egauge._parse_historical_data = mock_parser
    await egauge.get_historical_data(timestamps=dts)


def test_parse_instantaneous_data():
    xml_data = """<?xml version="1.0" encoding="UTF-8" ?>
        <data serial="0x7">
        <ts>1603319893</ts>
        <r t="P" n="Grid" did="0">
            <v>3231302713</v>
        </r>
        <r t="P" n="solar" did="1">
            <v>1010775416</v>
        </r>
        <r t="P" n="solar+" did="2">
            <v>818258107</v>
        </r>
        </data>
    """

    result = EgaugeClient._parse_instantaneous_data(xml_data)

    assert result.timestamp == datetime.fromtimestamp(1603319893)
    assert result.registers == {
        "Grid": RegisterData("P", 3231302713),
        "solar": RegisterData("P", 1010775416),
        "solar+": RegisterData("P", 818258107),
    }


def test_parse_instantaneous_data_with_rate():
    xml_data = """<?xml version="1.0" encoding="UTF-8" ?>
        <data serial="0x7">
        <ts>1603322016</ts>
        <r t="P" n="Grid" did="0">
            <v>3232317009</v>
            <i>654</i>
        </r>
        <r t="P" n="solar" did="1">
            <v>1010807136</v>
            <i>-8</i>
        </r>
        <r t="P" n="solar+" did="2">
            <v>818295664</v>
            <i>0</i>
        </r>
        </data>
    """
    parsed_data = EgaugeClient._parse_instantaneous_data(xml_data)

    assert parsed_data.timestamp == datetime.fromtimestamp(1603322016)
    assert parsed_data.registers == {
        "Grid": RegisterData("P", 3232317009, 654.0),
        "solar": RegisterData("P", 1010807136, -8.0),
        "solar+": RegisterData("P", 818295664, 0.0),
    }


def test_parse_historical_data_empty():
    xml_data = """<?xml version="1.0" encoding="UTF-8" ?>
        <!DOCTYPE group PUBLIC "-//ESL/DTD eGauge 1.0//EN" "http://www.egauge.net/DTD/egauge-hist.dtd">
        <group serial="0x7">
        <data columns="3" time_stamp="0x5f92089c" time_delta="86400" epoch="0x5f84cf10">
            <cname t="P" did="0">Grid</cname>
            <cname t="P" did="1">solar</cname>
            <cname t="P" did="2">solar+</cname>
        </data>
        </group>
    """
    parsed_data = EgaugeClient._parse_historical_data(xml_data)

    assert len(parsed_data) == 0


def test_parse_historical_data_normal():
    xml_data = """<?xml version="1.0" encoding="UTF-8" ?>
        <!DOCTYPE group PUBLIC "-//ESL/DTD eGauge 1.0//EN" "http://www.egauge.net/DTD/egauge-hist.dtd">
        <group serial="0x7">
        <data columns="3" time_stamp="0x5f8f7a00" time_delta="86400" epoch="0x5f84cf10">
            <cname t="P" did="0">Grid</cname>
            <cname t="P" did="1">solar</cname>
            <cname t="P" did="2">solar+</cname>
            <r>
            <c>3136544148</c>
            <c>988860527</c>
            <c>796054990</c>
            </r>
            <r>
            <c>3043043665</c>
            <c>982249490</c>
            <c>788995937</c>
            </r>
        </data>
        </group>
    """
    parsed_data = EgaugeClient._parse_historical_data(xml_data)

    assert parsed_data == [
        DataRow(
            timestamp=datetime.fromtimestamp(1603238400),
            registers={
                "Grid": RegisterData("P", 3136544148),
                "solar": RegisterData("P", 988860527),
                "solar+": RegisterData("P", 796054990),
            },
        ),
        DataRow(
            timestamp=datetime.fromtimestamp(1603152000),
            registers={
                "Grid": RegisterData("P", 3043043665),
                "solar": RegisterData("P", 982249490),
                "solar+": RegisterData("P", 788995937),
            },
        ),
    ]


def test_parse_historical_data_multidata():
    xml_data = """<?xml version="1.0" encoding="UTF-8" ?>
        <!DOCTYPE group PUBLIC "-//ESL/DTD eGauge 1.0//EN" "http://www.egauge.net/DTD/egauge-hist.dtd">
        <group serial="0x7">
        <data columns="3" time_stamp="0x5f84cf10" time_delta="86400" epoch="0x5f84cf10">
            <cname t="P" did="0">Grid</cname>
            <cname t="P" did="1">solar</cname>
            <cname t="P" did="2">solar+</cname>
            <r>
            <c>2198488901</c>
            <c>189917949</c>
            <c>-5783639</c>
            </r>
        </data>
        <data time_stamp="0x5f90cb80" time_delta="86400">
            <r>
            <c>3247728141</c>
            <c>1010788032</c>
            <c>818295664</c>
            </r>
        </data>
        </group>
"""
    parsed_data = EgaugeClient._parse_historical_data(xml_data)

    assert parsed_data == [
        DataRow(
            timestamp=datetime.fromtimestamp(1602539280),
            registers={
                "Grid": RegisterData("P", 2198488901),
                "solar": RegisterData("P", 189917949),
                "solar+": RegisterData("P", -5783639),
            },
        ),
        DataRow(
            timestamp=datetime.fromtimestamp(1603324800),
            registers={
                "Grid": RegisterData("P", 3247728141),
                "solar": RegisterData("P", 1010788032),
                "solar+": RegisterData("P", 818295664),
            },
        ),
    ]


@pytest.mark.asyncio
async def test_get_instantaneous_registers():
    xml_data = """<?xml version="1.0" encoding="UTF-8" ?>
        <data serial="0x7">
        <ts>1603322016</ts>
        <r t="P" n="Grid" did="0">
            <v>3232317009</v>
            <i>654</i>
        </r>
        <r t="P" n="solar" did="1">
            <v>1010807136</v>
            <i>-8</i>
        </r>
        <r t="P" n="solar+" did="2">
            <v>818295664</v>
            <i>0</i>
        </r>
        </data>
    """

    egauge = EgaugeClient("http://localhost")
    egauge.client = MockAsyncClient("http://localhost/cgi-bin/egauge", None, xml_data)
    result = await egauge.get_instantaneous_registers()

    assert result == {
        "Grid": "P",
        "solar": "P",
        "solar+": "P",
    }


@pytest.mark.asyncio
async def test_historical_data_registers():
    xml_data = """<?xml version="1.0" encoding="UTF-8" ?>
        <!DOCTYPE group PUBLIC "-//ESL/DTD eGauge 1.0//EN" "http://www.egauge.net/DTD/egauge-hist.dtd">
        <group serial="0x7">
        <data columns="3" time_stamp="0x5f8f7a00" time_delta="86400" epoch="0x5f84cf10">
            <cname t="P" did="0">Grid</cname>
            <cname t="P" did="1">solar</cname>
            <cname t="P" did="2">solar+</cname>
            <r>
            <c>3136544148</c>
            <c>988860527</c>
            <c>796054990</c>
            </r>
        </data>
        </group>
    """

    egauge = EgaugeClient("http://localhost")
    egauge.client = MockAsyncClient(
        "http://localhost/cgi-bin/egauge-show", None, xml_data
    )
    result = await egauge.get_historical_registers()
    assert result == {"Grid": "P", "solar": "P", "solar+": "P"}


@pytest.mark.asyncio
async def test_get_interval_changes(mocker):
    t1 = datetime.fromtimestamp(1000000000)
    t2 = t1 - timedelta(days=1)
    t3 = t1 - timedelta(days=2)

    egauge = EgaugeClient("http://localhost")
    f = asyncio.Future()
    f.set_result(
        [
            DataRow(timestamp=t1, registers={"reg": RegisterData("P", 123459)}),
            DataRow(timestamp=t2, registers={"reg": RegisterData("P", 123457)}),
            DataRow(timestamp=t3, registers={"reg": RegisterData("P", 123456)}),
        ]
    )
    egauge.get_historical_data = mocker.Mock(return_value=f)
    mock_dt = mocker.MagicMock(wrap=datetime)
    mock_dt.now.return_value = t1
    mocker.patch("datetime.datetime", mock_dt)

    result = await egauge.get_interval_changes(since=t3, interval=TimeInterval.DAY)

    egauge.get_historical_data.assert_called_once_with(
        start=t3, interval=TimeInterval.DAY, skip_rows=0
    )

    assert result == [
        {"start_ts": t3, "end_ts": t2, "measurements": {"reg": 1}},
        {"start_ts": t2, "end_ts": t1, "measurements": {"reg": 2}},
    ]
