#!/usr/bin/env python3
"""Continuously print force/torque samples, stopping after N samples."""

from __future__ import annotations

import argparse
import contextlib

from litearm_peripherals import WristFT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iface", default="can0")
    parser.add_argument("--interval", type=int, default=10, help="upload period in ms")
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args()

    with WristFT(iface=args.iface) as ft:
        with contextlib.closing(ft.stream(args.interval)) as samples:
            for index, sample in enumerate(samples, start=1):
                print(
                    f"{index:4d}  F=({sample.fx:7.3f}, {sample.fy:7.3f}, {sample.fz:7.3f}) N"
                    f"  M=({sample.mx:7.3f}, {sample.my:7.3f}, {sample.mz:7.3f}) Nm"
                )
                if index >= args.count:
                    break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
