from dataclasses import dataclass
from enum import StrEnum


class RegisterType(StrEnum):
    """eGauge register type codes with their API string values."""

    # Numeric types
    WHOLE_NUMBER = "#"
    NUMBER_3_DECIMAL = "#3"
    DISCRETE = "d"

    # Electrical - Power & Energy
    POWER = "P"
    APPARENT_POWER = "S"
    REACTIVE_POWER = "var"

    # Electrical - Voltage & Current
    VOLTAGE = "V"
    CURRENT = "I"
    RESISTANCE = "R"
    ELECTRIC_CHARGE = "Qe"

    # Environmental
    TEMPERATURE = "T"
    HUMIDITY = "h"
    PRESSURE = "Pa"
    AIR_QUALITY = "aq"

    # Frequency & Signal
    FREQUENCY = "F"
    ANGLE = "a"
    THD = "THD"

    # Flow & Mass
    MASS_FLOW = "Q"
    VOLUMETRIC_FLOW = "Qv"
    MASS = "m"
    SPEED = "v"

    # Other
    PERCENTAGE = "%"
    MONETARY = "$"
    IRRADIANCE = "Ee"
    PPM = "ppm"


@dataclass
class RegisterInfo:
    name: str
    type: RegisterType
    idx: int
    did: int | None = None


@dataclass
class NonceResponse:
    """Response from /auth/unauthorized endpoint containing server nonce"""

    realm: str
    nonce: str
    error: str | None = None


@dataclass
class AuthResponse:
    """Response from /auth/login endpoint containing JWT token"""

    jwt: str
    error: str | None = None


@dataclass
class UserRights:
    """Response from /auth/rights endpoint containing user privileges"""

    usr: str
    rights: list[str]
