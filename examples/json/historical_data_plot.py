#!/usr/bin/env python3
"""
Example: Fetching Historical Power Data and Creating a Plot

This example demonstrates how to:
1. Connect to an eGauge device using the JSON API
2. Retrieve historical power data for the last 7 days with hourly aggregation
3. Convert cumulative counter values (W·s) to average power rates (W)
4. Load data into a pandas DataFrame for analysis
5. Create a matplotlib line plot showing power usage over time
6. Save the plot to a PNG file

Key Concept: Historical Data Returns Cumulative Counters
------------------------------------------------------------
The JSON API's get_historical_counters() method returns cumulative counter
values in "unit·seconds" (e.g., Watt·seconds for power registers). These
counters are NEVER RESET - they continuously accumulate from device startup.

To get the energy consumed during each interval, calculate the difference
between consecutive readings. Then convert to average power:

    1. energy_interval = counter[t] - counter[t-1]  (using pandas .diff())
    2. average_rate = energy_interval / interval_seconds

For example, if readings show:
    Time 0: 10,000,000 W·s (cumulative)
    Time 1:  10,003,600 W·s (cumulative, +1 hour later)

    Energy consumed = 10,003,600 - 10,000,000 = 3,600 W·s
    Average power = 3,600 W·s / 3,600 s = 1 W
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone

import httpx
import matplotlib.pyplot as plt
import pandas as pd

from egauge_async.json.client import EgaugeJsonClient


async def main() -> None:
    # Get connection details from environment variables
    base_url = os.environ.get("EGAUGE_URL", "https://egauge12345.local")
    username = os.environ.get("EGAUGE_USERNAME", "owner")
    password = os.environ.get("EGAUGE_PASSWORD", "default")

    print(f"Connecting to eGauge device at {base_url}...")
    print()

    # Create HTTP client with SSL verification disabled (eGauges use self-signed certs)
    async with httpx.AsyncClient(verify=False) as http_client:
        # Create eGauge JSON client
        client = EgaugeJsonClient(
            base_url=base_url,
            username=username,
            password=password,
            client=http_client,
        )

        # Step 1: Get register information to find power registers
        print("Fetching register information...")
        registers = await client.get_register_info()

        # Find all power registers (type 'P')
        power_registers = [
            name for name, info in registers.items() if info.type.value == "P"
        ]

        if not power_registers:
            print("No power registers found on this device!")
            return

        print(
            f"Found {len(power_registers)} power register(s): {', '.join(power_registers)}"
        )
        print()

        # Step 2: Define time range - last 7 days with hourly aggregation
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=7)
        step = timedelta(hours=1)

        print("Fetching historical data:")
        print(f"  Start: {start_time.isoformat()}")
        print(f"  End:   {end_time.isoformat()}")
        print(f"  Step:  {step.total_seconds():.0f} seconds (1 hour)")
        print(f"  Registers: {', '.join(power_registers)}")
        print()

        # Step 3: Fetch historical counter data
        print("Downloading data from eGauge device...")
        data = await client.get_historical_counters(
            start_time=start_time,
            end_time=end_time,
            step=step,
            registers=power_registers,
        )

        print(f"Retrieved {len(data)} data points.")
        print()

        # Step 4: Convert to pandas DataFrame
        print("Converting to pandas DataFrame...")
        df = pd.DataFrame(data)

        # Set timestamp as index for time-series operations
        df.set_index("ts", inplace=True)

        # Sort in chronological order. The eGauge returns results in reverse chronological order.
        df.sort_index(inplace=True)

        # Calculate differences between consecutive rows to get energy consumed
        # during each interval (cumulative counters are never reset)
        interval_seconds = step.total_seconds()

        for register in power_registers:
            if register in df.columns:
                # Calculate the difference between consecutive cumulative values
                # to get the energy consumed (W·s) during each interval
                df[f"{register}_diff"] = df[register].diff()

                # Convert energy consumed (W·s) to average power (W)
                # by dividing by the interval in seconds
                df[f"{register}_watts"] = df[f"{register}_diff"] / interval_seconds

        print(f"DataFrame shape: {df.shape}")
        print()
        print("First few rows:")
        print(df.head())
        print()
        print("Last few rows:")
        print(df.tail())
        print()

        # Step 5: Create a plot
        print("Creating plot...")

        # Create figure with appropriate size
        plt.figure(figsize=(14, 8))

        # Plot each power register as a separate line
        for register in power_registers:
            rate_column = f"{register}_watts"
            if rate_column in df.columns:
                plt.plot(df.index, df[rate_column], label=register, linewidth=1.5)

        # Customize the plot
        plt.xlabel("Time (UTC)", fontsize=12)
        plt.ylabel("Power (Watts)", fontsize=12)
        plt.title(
            "Historical Power Usage - Last 7 Days (Hourly Average)",
            fontsize=14,
            fontweight="bold",
        )
        plt.legend(loc="best", fontsize=10)
        plt.grid(True, alpha=0.3)

        # Format x-axis to show dates nicely
        plt.gcf().autofmt_xdate()

        # Add horizontal line at y=0 for reference
        plt.axhline(y=0, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)

        # Tight layout to prevent label cutoff
        plt.tight_layout()

        # Save the plot
        output_file = "power_usage.png"
        plt.savefig(output_file, dpi=150, bbox_inches="tight")
        print(f"Plot saved to: {output_file}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
