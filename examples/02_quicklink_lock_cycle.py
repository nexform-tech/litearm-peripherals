#!/usr/bin/env python3
"""Lock the tool, wait, then unlock it.

This example moves hardware.  It refuses to run unless ``--yes`` is passed.
The unlock happens in ``finally`` so the tool is left released, but a crashed
process still requires the caller to check the physical state.
"""

from __future__ import annotations

import argparse
import time

from litearm_peripherals import QuickLink


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=None, help="serial port; auto-detect when omitted")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--slave", type=int, default=1)
    parser.add_argument("--hold", type=float, default=3.0, help="seconds to stay locked")
    parser.add_argument("--yes", action="store_true", help="confirm that the tool may move")
    args = parser.parse_args()

    if not args.yes:
        print("Refusing to lock hardware without --yes.")
        return 2

    with QuickLink(port=args.port, baudrate=args.baudrate, slave_addr=args.slave) as tool:
        print(f"before: {tool.read_status()}")
        try:
            tool.lock()
            print(f"locked: {tool.read_status()}")
            time.sleep(args.hold)
        finally:
            tool.unlock()
            print(f"after : {tool.read_status()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
