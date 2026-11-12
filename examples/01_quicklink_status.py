#!/usr/bin/env python3
"""Read the Quick Link lock, power, temperature and firmware status."""

from __future__ import annotations

import argparse

from litearm_peripherals import QuickLink


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=None, help="serial port; auto-detect when omitted")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--slave", type=int, default=1)
    args = parser.parse_args()

    with QuickLink(port=args.port, baudrate=args.baudrate, slave_addr=args.slave) as tool:
        status = tool.read_status(include_firmware=True)
        print(f"port        : {tool.port}")
        print(f"lock        : {status.lock.name}")
        print(f"power       : {status.power.name}")
        print(f"temperature : {status.temperature_c} C")
        print(f"firmware    : {status.firmware}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
