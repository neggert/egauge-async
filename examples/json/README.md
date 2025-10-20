# JSON API Examples

This directory contains examples demonstrating how to use the eGauge JSON API client to interact with eGauge energy monitoring devices.

## Prerequisites

### Install Dependencies

First, install the base library:

```bash
uv sync
```

Then install the additional dependencies needed for the examples (pandas and matplotlib):

```bash
uv sync --group examples
```

Alternatively, if you're not using `uv`, install via pip:

```bash
pip install pandas matplotlib
```

### Environment Variables

The examples use environment variables for configuration. Set these before running:

```bash
export EGAUGE_URL="https://egauge12345.local"
export EGAUGE_USERNAME="owner"
export EGAUGE_PASSWORD="your_password"
```

Or create a `.env` file and source it:

```bash
# .env file
EGAUGE_URL=https://egauge12345.local
EGAUGE_USERNAME=owner
EGAUGE_PASSWORD=your_password
```

Then source it:

```bash
source .env
```

## Examples

### 1. Current Measurements (`current_measurements.py`)

Demonstrates how to fetch instantaneous rate values from your eGauge device.

**What it does:**
- Connects to the eGauge device with JWT authentication
- Retrieves metadata for all registers (names, types, indices)
- Fetches current instantaneous measurements for all registers
- Filters measurements to show only specific register types (e.g., power registers)
- Displays results in formatted tables

**Run it:**

```bash
uv run python examples/json/current_measurements.py
```

### 2. Historical Data Plot (`historical_data_plot.py`)

Demonstrates how to fetch historical power data, process it with pandas, and create a visualization.

**What it does:**
- Fetches historical power data for the last 7 days with hourly aggregation
- Converts cumulative counter values (Watt·seconds) to average power rates (Watts)
- Loads data into a pandas DataFrame for analysis
- Creates a matplotlib line plot showing power usage trends over time
- Calculates and displays statistics (average, peak, total energy consumption)
- Saves the plot as `power_usage.png`

**Run it:**

```bash
uv run python examples/json/historical_data_plot.py
```

## Understanding Cumulative vs. Rate Values

### Current Measurements (Instantaneous Rates)

The `get_current_measurements()` method returns **instantaneous rate values** that are already in physical units:
- Power registers: Watts (W)
- Voltage registers: Volts (V)
- Current registers: Amperes (A)
- Temperature registers: Degrees Celsius (°C)

No conversion needed - use the values directly.

### Historical Data (Cumulative Counters)

The `get_historical_counters()` method returns **cumulative counter values** in "unit·seconds":
- Power registers: Watt·seconds (W·s)
- Voltage registers: Volt·seconds (V·s)
- Current registers: Ampere·seconds (A·s)

**Important:** These counters are NEVER RESET - they continuously accumulate from device startup. To get the energy consumed during each interval, you must calculate the difference between consecutive readings:

```python
# Step 1: Calculate differences between consecutive cumulative values
df['register_diff'] = df['register'].diff()

# Step 2: Convert to average rate by dividing by interval
average_rate = df['register_diff'] / interval_seconds
```

**Example:**
```python
# If you request hourly data (step = 1 hour = 3600 seconds)
# and get these cumulative counter values:
# Time 0: 10,000,000 W·s (cumulative since device startup)
# Time 1: 10,003,600 W·s (cumulative, +1 hour later)

energy_consumed = 10_003_600 - 10_000_000  # = 3,600 W·s
average_power_watts = 3_600 / 3600  # = 1 W

# This means the average power consumption during that hour was 1 Watt
```

To calculate total energy consumption (e.g., in kWh):

```python
# Sum all the differences (energy per interval in W·s) and convert to kWh
total_ws = df['Grid_diff'].sum()  # Sum of interval energies
total_kwh = total_ws / (1000 * 3600)  # W·s → kWh

# Alternatively, use the difference between last and first cumulative values
total_ws = df['Grid'].iloc[-1] - df['Grid'].iloc[0]
total_kwh = total_ws / (1000 * 3600)  # W·s → kWh
```

## Troubleshooting

### Connection Errors

If you see connection errors:
- Verify the eGauge device is accessible at the URL you provided
- Check that the device is on the same network or VPN
- Ensure the device's web interface is accessible in a browser

### Authentication Errors

If you see authentication errors:
- Verify your username and password are correct
- Check that the user account has sufficient permissions
- Try logging in via the web interface to confirm credentials

### Import Errors

If you see `ModuleNotFoundError` for pandas or matplotlib:
- Run `uv sync --group examples` to install example dependencies
- Or manually install: `pip install pandas matplotlib`

### No Data Returned

If historical queries return no data:
- Check that your time range is valid (start < end)
- Verify the device has data for the requested time period
- Ensure register names are spelled correctly
- Try querying with `registers=None` to fetch all available registers

## Additional Resources

- [eGauge WebAPI Documentation](https://kb.egauge.net/books/egauge-meter-communication/page/json-webapi)
- [eGauge Python Library GitHub](https://github.com/neggert/egauge-async)
- [Pandas Documentation](https://pandas.pydata.org/docs/)
- [Matplotlib Documentation](https://matplotlib.org/stable/contents.html)
