#!/usr/bin/env python3
"""Read both peripherals through the PeripheralHub facade."""

from __future__ import annotations

import argparse

from litearm_peripherals import PeripheralHub


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=None, help="Quick Link serial port")
    parser.add_argument("--iface", default="can0", help="CAN interface for the F/T sensor")
    args = parser.parse_args()

    with PeripheralHub.open(quicklink_port=args.port, iface=args.iface) as hub:
        status = hub.read_status()
        if status.quicklink is not None:
            print(
                f"lock={status.quicklink.lock.name} "
                f"power={status.quicklink.power.name} "
                f"temperature={status.quicklink.temperature_c} C"
            )
        if status.wrist_ft is not None:
            sample = status.wrist_ft
            print(
                f"F=({sample.fx:.3f}, {sample.fy:.3f}, {sample.fz:.3f}) N  "
                f"M=({sample.mx:.3f}, {sample.my:.3f}, {sample.mz:.3f}) Nm"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
