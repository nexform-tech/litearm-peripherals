"""Exception hierarchy for :mod:`litearm_peripherals`.

All errors raised by this package derive from :class:`PeripheralsError`, so a
single ``except PeripheralsError`` catches everything.  Each subclass groups
errors by device and failure mode, and carries optional structured context
(port, CAN id, request bytes, ...) for logging and debugging.
"""

from __future__ import annotations

from typing import Any, Dict


class PeripheralsError(Exception):
    """Base class for every error raised by this package."""

    def __init__(self, message: str = "", **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context: Dict[str, Any] = dict(context)

    def __str__(self) -> str:
        if not self.context:
            return self.message
        details = ", ".join(f"{key}={value!r}" for key, value in self.context.items())
        return f"{self.message} ({details})"


# --------------------------------------------------------------------------- quick link
class QuickLinkError(PeripheralsError):
    """Base class for Handsfree Quick Link errors."""


class QuickLinkConnectionError(QuickLinkError):
    """The serial port could not be detected, opened, or is already in use."""


class QuickLinkTimeoutError(QuickLinkError):
    """The device did not answer a Modbus request before the deadline."""


class QuickLinkProtocolError(QuickLinkError):
    """A Modbus frame was malformed, had a bad CRC, or carried an exception."""


class QuickLinkStateError(QuickLinkError):
    """The reported lock/power state is inconsistent with the command sent."""


# --------------------------------------------------------------------------- wrist FT
class WristFTError(PeripheralsError):
    """Base class for WRJST six-axis force/torque sensor errors."""


class WristFTConnectionError(WristFTError):
    """The CAN interface could not be opened, or the transport failed."""


class WristFTTimeoutError(WristFTError):
    """No complete force/torque sample arrived before the deadline."""


class WristFTProtocolError(WristFTError):
    """A CAN frame or sensor payload was malformed or implausible."""


class WristFTIdChangeError(WristFTError):
    """Changing or resetting the sensor CAN ids could not be verified."""
