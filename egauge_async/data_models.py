# pyright: reportDeprecated=false
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, Optional
from warnings import deprecated


@deprecated("RegisterData is deprecated and will be removed in egauge-async v0.6.0.")
@dataclass
class RegisterData(object):
    """Data from a single register

    Args:
        register_type_code: type code describing the data stored in the register.
            Type codes are described in the [Egauge API docs]_.
        value: register value
        rate: rate of change of the last second
    """

    register_type_code: str
    value: int
    rate: Optional[float] = None


@deprecated("DataRow is deprecated and will be removed in egauge-async v0.6.0.")
@dataclass
class DataRow(object):
    """A row of data from the Egauge

    Args:
        timestamp: the time at which the reading was recorded
        registers: dictionary mapping register name to the corresponding data
    """

    timestamp: datetime
    registers: Dict[str, RegisterData]


@deprecated("TimeInterval is deprecated and will be removed in egauge-async v0.6.0.")
class TimeInterval(Enum):
    """Time intervals supported by the Egauge API"""

    SECOND = 1
    MINUTE = 2
    HOUR = 3
    DAY = 4
