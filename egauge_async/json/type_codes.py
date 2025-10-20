"""Type code metadata for eGauge registers."""

from dataclasses import dataclass

from egauge_async.json.models import RegisterType


@dataclass(frozen=True)
class TypeCodeInfo:
    """Metadata for an eGauge register type code.

    Attributes:
        type_code: The RegisterType enum value
        description: Human-readable description
        rate_unit: Unit for rate/instantaneous values (e.g., "W", "V", "A")
        quantum: Multiplier to convert raw cumulative values to physical units
        cumulative_unit: Unit for accumulated values (e.g., "W·s", "V·s")
    """

    type_code: RegisterType
    description: str
    rate_unit: str | None
    quantum: float
    cumulative_unit: str | None


TYPE_CODES: dict[RegisterType, TypeCodeInfo] = {
    # Numeric types
    RegisterType.WHOLE_NUMBER: TypeCodeInfo(
        RegisterType.WHOLE_NUMBER, "Whole number", None, 1.0, None
    ),
    RegisterType.NUMBER_3_DECIMAL: TypeCodeInfo(
        RegisterType.NUMBER_3_DECIMAL, "Number with 3 decimal places", None, 0.001, None
    ),
    RegisterType.DISCRETE: TypeCodeInfo(
        RegisterType.DISCRETE, "Discrete number", None, 1.0, None
    ),
    # Electrical - Power & Energy
    RegisterType.POWER: TypeCodeInfo(RegisterType.POWER, "Power", "W", 1.0, "W·s"),
    RegisterType.APPARENT_POWER: TypeCodeInfo(
        RegisterType.APPARENT_POWER, "Apparent power", "VA", 1.0, "VA·s"
    ),
    RegisterType.REACTIVE_POWER: TypeCodeInfo(
        RegisterType.REACTIVE_POWER, "Reactive power", "var", 1.0, "var·s"
    ),
    # Electrical - Voltage & Current
    RegisterType.VOLTAGE: TypeCodeInfo(
        RegisterType.VOLTAGE, "Voltage", "V", 0.001, "V·s"
    ),
    RegisterType.CURRENT: TypeCodeInfo(
        RegisterType.CURRENT, "Electrical current", "A", 0.001, "A·s"
    ),
    RegisterType.RESISTANCE: TypeCodeInfo(
        RegisterType.RESISTANCE, "Electric resistance", "Ω", 1.0, "Ω·s"
    ),
    RegisterType.ELECTRIC_CHARGE: TypeCodeInfo(
        RegisterType.ELECTRIC_CHARGE, "Electric charge", "Ah", 0.001, "Ah·s"
    ),
    # Environmental
    RegisterType.TEMPERATURE: TypeCodeInfo(
        RegisterType.TEMPERATURE, "Temperature", "°C", 0.001, "°C·s"
    ),
    RegisterType.HUMIDITY: TypeCodeInfo(
        RegisterType.HUMIDITY, "Relative humidity", "%", 0.001, "%·s"
    ),
    RegisterType.PRESSURE: TypeCodeInfo(
        RegisterType.PRESSURE, "Pressure", "Pa", 1.0, "Pa·s"
    ),
    RegisterType.AIR_QUALITY: TypeCodeInfo(
        RegisterType.AIR_QUALITY, "Air quality index", "s", 0.001, "s·s"
    ),
    # Frequency & Signal
    RegisterType.FREQUENCY: TypeCodeInfo(
        RegisterType.FREQUENCY, "Frequency", "Hz", 0.001, "Hz·s"
    ),
    RegisterType.ANGLE: TypeCodeInfo(RegisterType.ANGLE, "Angle", "°", 0.001, "°·s"),
    RegisterType.THD: TypeCodeInfo(
        RegisterType.THD, "Total harmonic distortion", "%", 0.001, "%·s"
    ),
    # Flow & Mass
    RegisterType.MASS_FLOW: TypeCodeInfo(
        RegisterType.MASS_FLOW, "Mass flow", "g/s", 1.0, "g"
    ),
    RegisterType.VOLUMETRIC_FLOW: TypeCodeInfo(
        RegisterType.VOLUMETRIC_FLOW, "Volumetric flow", "m³/s", 1e-9, "m³"
    ),
    RegisterType.MASS: TypeCodeInfo(RegisterType.MASS, "Mass", "g", 0.001, "g·s"),
    RegisterType.SPEED: TypeCodeInfo(RegisterType.SPEED, "Speed", "m/s", 0.001, "m"),
    # Other
    RegisterType.PERCENTAGE: TypeCodeInfo(
        RegisterType.PERCENTAGE, "Percentage", "%", 0.001, "%·s"
    ),
    RegisterType.MONETARY: TypeCodeInfo(
        RegisterType.MONETARY, "Monetary accrual rate", "$/s", 2**-29, "$·s"
    ),
    RegisterType.IRRADIANCE: TypeCodeInfo(
        RegisterType.IRRADIANCE, "Irradiance", "W/m²", 1.0, "W·s/m²"
    ),
    RegisterType.PPM: TypeCodeInfo(
        RegisterType.PPM, "Parts per million", "ppm", 0.001, "ppm·s"
    ),
}


def get_quantum(type_code: RegisterType) -> float:
    """Get the quantum multiplier for a register type code.

    Args:
        type_code: The RegisterType to look up

    Returns:
        The quantum multiplier (float)

    Raises:
        KeyError: If type_code is not in TYPE_CODES
    """
    return TYPE_CODES[type_code].quantum
