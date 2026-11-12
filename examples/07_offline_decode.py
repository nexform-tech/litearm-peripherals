#!/usr/bin/env python3
"""Decode recorded CAN frames without any hardware.

The frames below are a real measurement; float payloads are little-endian.
"""

from __future__ import annotations

from litearm_peripherals import decode_sample

FRAMES = {
    0x15: bytes.fromhex("79 5B C7 40 10 99 DC C0"),  # Fx, Fy
    0x16: bytes.fromhex("B7 D9 F1 C0 3C 0B D6 3D"),  # Fz, Mx
    0x17: bytes.fromhex("92 21 30 BD 93 FB AB 3E"),  # My, Mz
}


def main() -> int:
    sample = decode_sample(FRAMES)
    for name, value, unit in zip(
        ("Fx", "Fy", "Fz", "Mx", "My", "Mz"), sample.as_tuple(), ("N", "N", "N", "Nm", "Nm", "Nm")
    ):
        print(f"{name} = {value:9.4f} {unit}")
    print(f"endian = {sample.endian}")
    print(f"|F| = {sample.force_magnitude:.4f} N, |M| = {sample.torque_magnitude:.4f} Nm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
