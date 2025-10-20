#!/usr/bin/env python3
"""
Example: Fetching Current Measurements from eGauge Device

This example demonstrates how to:
1. Connect to an eGauge device using the JSON API with JWT authentication
2. Retrieve register metadata (names, types, indices)
3. Fetch current instantaneous measurements (rates) for all registers
4. Fetch measurements for specific registers only
5. Display results in a formatted table

The JSON API returns instantaneous rate values already converted to physical
units (e.g., Watts for power registers, Volts for voltage, etc.).
"""

import asyncio
import os
from datetime import datetime, timezone

import httpx

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

        # Step 1: Get register metadata
        print("=" * 80)
        print("REGISTER INFORMATION")
        print("=" * 80)

        registers = await client.get_register_info()

        print(f"Found {len(registers)} registers:")
        print()
        print(f"{'Name':<30} {'Type':<15} {'Index':<8} {'Database ID':<12}")
        print("-" * 80)

        for name, info in registers.items():
            did_str = str(info.did) if info.did is not None else "virtual"
            print(f"{name:<30} {info.type.value:<15} {info.idx:<8} {did_str:<12}")

        print()

        # Step 2: Get current measurements for all registers
        print("=" * 80)
        print("CURRENT MEASUREMENTS (ALL REGISTERS)")
        print("=" * 80)
        print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
        print()

        measurements = await client.get_current_measurements()

        print(f"{'Register Name':<30} {'Current Rate':<20} {'Unit'}")
        print("-" * 80)

        for name, rate in measurements.items():
            # Get the register type to determine the unit
            reg_info = registers.get(name)
            unit = reg_info.type.value if reg_info else "?"

            # Format the rate value based on magnitude
            if abs(rate) >= 1000:
                rate_str = f"{rate:,.2f}"
            elif abs(rate) >= 0.01:
                rate_str = f"{rate:.2f}"
            else:
                rate_str = f"{rate:.6f}"

            print(f"{name:<30} {rate_str:<20} {unit}")

        print()

        # Step 3: Get current measurements for specific registers only
        # Find some power registers to demonstrate filtering
        power_registers = [
            name for name, info in registers.items() if info.type.value == "P"
        ]

        if power_registers:
            print("=" * 80)
            print("CURRENT MEASUREMENTS (POWER REGISTERS ONLY)")
            print("=" * 80)
            print(
                f"Filtering to {len(power_registers)} power register(s): {', '.join(power_registers)}"
            )
            print()

            power_measurements = await client.get_current_measurements(
                registers=power_registers
            )

            print(f"{'Register Name':<30} {'Power (W)':<20}")
            print("-" * 80)

            for name, rate in power_measurements.items():
                rate_str = f"{rate:,.2f}"
                print(f"{name:<30} {rate_str:<20}")

            print("-" * 80)
            print()


if __name__ == "__main__":
    asyncio.run(main())
