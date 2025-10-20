# Egauge-Async

`asyncio` APIs for communicating with [eGauge](https://www.egauge.net) meters.

## Examples

### Get current rates
```python
import asyncio
from egauge_async import EgaugeClient

async def get_current_rates():
    egauge = EgaugeClient("http://egaugehq.d.egauge.net")
    current_readings = egauge.get_current_rates()
    print(current_readings)

asyncio.run(get_current_rates())
```

### Get weekly changes over the last 4 weeks

```python
import asyncio
from egauge_async import EgaugeClient

async def get_weekly_changes():
    egauge = EgaugeClient("http://egaugehq.d.egauge.net")
    weekly_changes = egauge.get_weekly_changes(num_weeks=4)
    print(weekly_changes)

asyncio.run(get_weekly_changes())
```

### Get available registers

```python
import asyncio
from egauge_async import EgaugeClient

async def get_registers():
    egauge = EgaugeClient("http://egaugehq.d.egauge.net")
    instantaneous_registers = egauge.get_instantaneous_registers()j
    print(instantaneous_registers)
    historical_registers = egauge.get_historical_registers()
    print(historical_registers)

asyncio.run(get_historical_registers())
```

## Implementation Details

This package uses the publically-documented [XML API](https://kb.egauge.net/books/egauge-meter-communication/page/xml-api)
provided by eGauge Systems. It also provides support for the newer JSON API with JWT authentication.

## Testing

The project includes both unit tests and integration tests:

### Running Tests

```bash
# Run all unit tests (default)
uv run pytest

# Run with coverage
uv run pytest --cov=egauge_async

# Run integration tests (requires real eGauge device)
export EGAUGE_URL="https://egauge12345.local"
export EGAUGE_USERNAME="owner"
export EGAUGE_PASSWORD="your_password"
uv run pytest -m integration
```

Integration tests validate functionality against a real eGauge device and are automatically skipped if the required environment variables (`EGAUGE_URL`, `EGAUGE_USERNAME`, `EGAUGE_PASSWORD`) are not set.

## Disclaimer

This project is not affiliated with, endorsed by, or sponsored by eGauge Systems LLC. Any
product names, logos, brands, or other trademarks are the property of their respective
trademark holders.
