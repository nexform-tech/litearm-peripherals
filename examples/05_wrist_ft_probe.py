#!/usr/bin/env python3
"""Scan the CAN bus for the three consecutive ids used by the sensor."""

from __future__ import annotations

import argparse

from litearm_peripherals import WristFT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iface", default="can0")
    parser.add_argument("--duration", type=float, default=3.0)
    parser.add_argument(
        "--start",
        type=int,
        default=10,
        help="send a start frame at this period first; 0 skips it",
    )
    args = parser.parse_args()

    with WristFT(iface=args.iface) as ft:
        start_ms = args.start or None
        candidates = ft.probe(duration=args.duration, start_ms=start_ms)
        if not candidates:
            print("No force/torque data found. Is the sensor powered and the bus at 1 Mbit/s?")
            return 1
        for candidate in candidates:
            print(
                f"base=0x{candidate.base:02X}  rate={candidate.rate:7.1f} Hz"
                f"  endian={candidate.endian}  plausible={candidate.plausible}"
            )
            print("  " + "  ".join(f"{value:9.3f}" for value in candidate.values))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
