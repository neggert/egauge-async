import pytest

from egauge_async.utils import create_query_string


@pytest.mark.parametrize(
    "input,expected",
    [
        (["p"], "?p"),
        ([("k", "v")], "?k=v"),
        (["p", ("k", "v")], "?p&k=v"),
    ],
)
def test_create_query_string(input, expected):
    qs = create_query_string(input)
    assert qs == expected
