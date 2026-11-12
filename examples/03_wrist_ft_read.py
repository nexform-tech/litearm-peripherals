#!/usr/bin/env python3
"""Start the F/T sensor upload and print one six-axis sample."""

from __future__ import annotations

import argparse

from litearm_peripherals import WristFT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iface", default="can0")
    parser.add_argument("--interval", type=int, default=10, help="upload period in ms")
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()

    with WristFT(iface=args.iface, auto_start=False) as ft:
        ft.start(args.interval)
        sample = ft.read(timeout=args.timeout)
        print(
            f"Fx={sample.fx:8.3f} N   Fy={sample.fy:8.3f} N   Fz={sample.fz:8.3f} N"
        )
        print(
            f"Mx={sample.mx:8.3f} Nm  My={sample.my:8.3f} Nm  Mz={sample.mz:8.3f} Nm"
        )
        print(f"|F|={sample.force_magnitude:.3f} N  |M|={sample.torque_magnitude:.3f} Nm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
