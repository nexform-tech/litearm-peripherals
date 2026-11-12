"""Python SDK for two LiteArm peripherals.

* :class:`QuickLink` — Handsfree Quick Link tool changer, Modbus RTU over a
  USB-RS485 adapter.  Lock/unlock also switches tool power on/off.
* :class:`WristFT` — WRJST six-axis force/torque sensor over raw SocketCAN.
* :class:`PeripheralHub` — optional facade that owns both devices.

Quick start::

    from litearm_peripherals import QuickLink, WristFT

    with QuickLink(port="/dev/ttyUSB0") as tool:
        print(tool.read_status())

    with WristFT(iface="can0") as ft:
        ft.start(10)                 # 100 Hz upload
        sample = ft.read(timeout=1.0)
        print(sample.fx, sample.fy, sample.fz,
              sample.mx, sample.my, sample.mz)
"""

from __future__ import annotations

from importlib import metadata

from .errors import (
    PeripheralsError,
    QuickLinkConnectionError,
    QuickLinkError,
    QuickLinkProtocolError,
    QuickLinkStateError,
    QuickLinkTimeoutError,
    WristFTConnectionError,
    WristFTError,
    WristFTIdChangeError,
    WristFTProtocolError,
    WristFTTimeoutError,
)
from .facade import HubStatus, PeripheralHub
from .quicklink import (
    LockState,
    PowerState,
    QuickLink,
    QuickLinkStatus,
    find_quicklink_port,
)
from .wrist_ft import Candidate, Sample, WristFT, decode_sample


def _detect_version() -> str:
    try:
        return metadata.version("litearm-peripherals")
    except metadata.PackageNotFoundError:
        return "0.0.0+source"


__version__ = _detect_version()

__all__ = [
    "__version__",
    "PeripheralsError",
    "QuickLink",
    "QuickLinkError",
    "QuickLinkConnectionError",
    "QuickLinkTimeoutError",
    "QuickLinkProtocolError",
    "QuickLinkStateError",
    "QuickLinkStatus",
    "LockState",
    "PowerState",
    "find_quicklink_port",
    "WristFT",
    "Sample",
    "Candidate",
    "decode_sample",
    "WristFTError",
    "WristFTConnectionError",
    "WristFTTimeoutError",
    "WristFTProtocolError",
    "WristFTIdChangeError",
    "PeripheralHub",
    "HubStatus",
]
