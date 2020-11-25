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
provided by eGauge Systems.

## Disclaimer

This project is not affiliated with, endorsed by, or sponsored by eGauge Systems LLC. Any
product names, logos, brands, or other trademarks are the property of their respective
trademark holders.
