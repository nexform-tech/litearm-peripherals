"""Handsfree Quick Link tool changer driver (Modbus RTU over a serial port).

The device exposes two coils (lock, power) and two holding registers
(temperature, firmware version).  Locking the tool implies powering the tool
on, and unlocking implies powering it off.

Safety rules encoded here:

* :meth:`QuickLink.close` never writes a coil.  Closing a process must not
  move the physical tool.
* ``lock``/``unlock`` verify the interlock after writing and raise
  :class:`~litearm_peripherals.errors.QuickLinkStateError` instead of silently
  "fixing" an inconsistent state.
* A tool change sequence (unlock -> move -> lock) is the caller's
  responsibility; this class never automates it.
"""

from __future__ import annotations

import glob
import logging
import os
import threading
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import List, Optional

from ._modbus import (
    parse_coils,
    parse_holding,
    parse_write_coil,
    read_coils_request,
    read_holding_request,
    unpack_frame,
    write_coil_request,
)
from ._serial import (
    SerialFactory,
    SerialLike,
    close_serial,
    list_serial_ports,
    normalize_port,
    open_serial,
)
from .errors import (
    QuickLinkConnectionError,
    QuickLinkProtocolError,
    QuickLinkStateError,
    QuickLinkTimeoutError,
)

log = logging.getLogger(__name__)

COIL_LOCK = 0x0000
COIL_POWER = 0x0001
HR_TEMPERATURE = 0x0000
HR_FIRMWARE = 0x0001

DEFAULT_BAUDRATE = 115200
DEFAULT_SLAVE_ADDR = 1

ENV_PORT = "LITEARM_QUICKLINK_PORT"
UDEV_SYMLINK = "/dev/HFRobotQuickLink"
BY_ID_DIR = "/dev/serial/by-id"


class LockState(IntEnum):
    """Mechanical lock state reported by coil ``0x0000``."""

    UNLOCKED = 0
    LOCKED = 1


class PowerState(IntEnum):
    """Tool power state reported by coil ``0x0001``."""

    OFF = 0
    ON = 1


@dataclass(frozen=True)
class QuickLinkStatus:
    """Snapshot of lock, power, temperature and (optionally) firmware."""

    lock: LockState
    power: PowerState
    temperature_c: int
    firmware: Optional[str] = None


def _port_text(info: object) -> str:
    attributes = ("device", "description", "interface", "product", "manufacturer", "hwid")
    return " ".join(str(getattr(info, attr, "") or "") for attr in attributes).lower()


def _is_quicklink(info: object) -> bool:
    text = _port_text(info)
    return any(token in text for token in ("handsfree", "quicklink", "quick_link"))


def find_quicklink_port() -> str:
    """Locate the Quick Link serial port.

    Detection order: ``$LITEARM_QUICKLINK_PORT``, the udev symlink
    ``/dev/HFRobotQuickLink``, ``/dev/serial/by-id`` names containing
    HandsFree/QuickLink, pyserial port metadata, then a single CH340/ttyUSB
    fallback (with a warning).
    """
    from_env = os.environ.get(ENV_PORT)
    if from_env:
        if not os.path.exists(from_env):
            raise QuickLinkConnectionError(
                f"{ENV_PORT} points to a path that does not exist", port=from_env
            )
        return from_env

    if os.path.exists(UDEV_SYMLINK):
        return UDEV_SYMLINK

    by_id: List[str] = []
    if os.path.isdir(BY_ID_DIR):
        for name in sorted(os.listdir(BY_ID_DIR)):
            lowered = name.lower()
            if any(token in lowered for token in ("handsfree", "quicklink", "quick_link")):
                by_id.append(os.path.join(BY_ID_DIR, name))
    if len(by_id) == 1:
        return by_id[0]
    if len(by_id) > 1:
        raise QuickLinkConnectionError(
            "Multiple Handsfree Quick Link devices found in /dev/serial/by-id",
            candidates=tuple(by_id),
        )

    ports = list_serial_ports()
    matched = [port.device for port in ports if _is_quicklink(port)]
    if len(matched) == 1:
        return matched[0]
    if len(matched) > 1:
        raise QuickLinkConnectionError(
            "Multiple Handsfree Quick Link devices found", candidates=tuple(matched)
        )

    candidates = [
        port.device
        for port in ports
        if port.device.startswith(("/dev/ttyUSB", "/dev/ttyACM"))
        or "ch340" in _port_text(port)
    ]
    if not candidates:
        candidates = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    if len(candidates) == 1:
        log.warning(
            "Quick Link was not identified by name; falling back to %s. "
            "Set %s to silence this warning.",
            candidates[0],
            ENV_PORT,
        )
        return candidates[0]
    if not candidates:
        raise QuickLinkConnectionError(
            "No serial port found; connect the Quick Link USB adapter "
            f"or set {ENV_PORT}"
        )
    raise QuickLinkConnectionError(
        "Multiple serial ports could be the Quick Link; set "
        f"{ENV_PORT} explicitly",
        candidates=tuple(candidates),
    )


class QuickLink:
    """Synchronous driver for one Handsfree Quick Link tool changer.

    Example::

        with QuickLink(port="/dev/ttyUSB0") as tool:
            print(tool.read_status())
            tool.lock()          # lock also powers the tool on
            tool.unlock()        # unlock also powers the tool off
    """

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = DEFAULT_BAUDRATE,
        slave_addr: int = DEFAULT_SLAVE_ADDR,
        timeout: float = 0.5,
        retries: int = 2,
        tx_guard: float = 0.002,
        retry_backoff: float = 0.05,
        serial_factory: Optional[SerialFactory] = None,
    ) -> None:
        if not 1 <= slave_addr <= 247:
            raise ValueError("slave_addr must be between 1 and 247")
        if baudrate <= 0:
            raise ValueError("baudrate must be positive")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if retries < 0:
            raise ValueError("retries must be non-negative")
        self.port = normalize_port(port) if port else None
        self.baudrate = baudrate
        self.slave_addr = slave_addr
        self.timeout = timeout
        self.retries = retries
        self.tx_guard = tx_guard
        self.retry_backoff = retry_backoff
        self._serial_factory = serial_factory
        self._handle: Optional[SerialLike] = None
        self._io_lock = threading.RLock()

    # ------------------------------------------------------------------ lifecycle
    @property
    def is_open(self) -> bool:
        return self._handle is not None and bool(getattr(self._handle, "is_open", True))

    def open(self) -> "QuickLink":
        """Open the serial port, detecting it when *port* was omitted."""
        with self._io_lock:
            if self._handle is not None:
                return self
            port = self.port or find_quicklink_port()
            self._handle = open_serial(
                port,
                self.baudrate,
                timeout=self.timeout,
                serial_factory=self._serial_factory,
            )
            self.port = normalize_port(port)
            return self

    def close(self) -> None:
        """Close the serial port.  Never writes a coil (never unlocks)."""
        with self._io_lock:
            if self._handle is None:
                return
            close_serial(self._handle, self.port or "")
            self._handle = None

    def __enter__(self) -> "QuickLink":
        return self.open()

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------ transport
    def _require_open(self) -> SerialLike:
        if self._handle is None:
            raise QuickLinkConnectionError(
                "QuickLink is not open; call open() or use 'with QuickLink(...)'",
                port=self.port,
            )
        return self._handle

    @staticmethod
    def _drain(handle: SerialLike) -> None:
        try:
            handle.reset_input_buffer()
        except Exception:  # pragma: no cover - best effort
            pass

    def _read_exact(
        self, handle: SerialLike, size: int, deadline: float, request: bytes
    ) -> bytes:
        buffer = bytearray()
        while len(buffer) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise QuickLinkTimeoutError(
                    "Timed out waiting for a Modbus response",
                    port=self.port,
                    expected=size,
                    actual=len(buffer),
                    request_hex=request.hex(" "),
                )
            try:
                chunk = handle.read(size - len(buffer))
            except Exception as exc:
                raise QuickLinkConnectionError(
                    f"Serial read failed on {self.port}: {exc}", port=self.port
                ) from exc
            if chunk:
                buffer.extend(chunk)
            else:
                time.sleep(0.001)
        return bytes(buffer)

    def _transact(self, request: bytes, expected_length: int) -> bytes:
        handle = self._require_open()
        with self._io_lock:
            self._drain(handle)
            try:
                handle.write(request)
                handle.flush()
            except Exception as exc:
                raise QuickLinkConnectionError(
                    f"Serial write failed on {self.port}: {exc}", port=self.port
                ) from exc
            deadline = time.monotonic() + self.timeout
            if self.tx_guard > 0:
                time.sleep(min(self.tx_guard, max(0.0, deadline - time.monotonic())))
            header = self._read_exact(handle, 2, deadline, request)
            if header[1] & 0x80:
                rest = self._read_exact(handle, 3, deadline, request)
            else:
                rest = self._read_exact(handle, expected_length - 2, deadline, request)
            return header + rest

    def _read_pdu(self, request: bytes, expected_length: int) -> bytes:
        return unpack_frame(self._transact(request, expected_length), self.slave_addr)

    # ------------------------------------------------------------------ reads
    def read_lock_state(self) -> LockState:
        pdu = self._read_pdu(read_coils_request(self.slave_addr, COIL_LOCK, 1), 6)
        return LockState.LOCKED if parse_coils(pdu, 1)[0] else LockState.UNLOCKED

    def read_power_state(self) -> PowerState:
        pdu = self._read_pdu(read_coils_request(self.slave_addr, COIL_POWER, 1), 6)
        return PowerState.ON if parse_coils(pdu, 1)[0] else PowerState.OFF

    def read_temperature(self) -> int:
        pdu = self._read_pdu(read_holding_request(self.slave_addr, HR_TEMPERATURE, 1), 7)
        value = parse_holding(pdu, 1)[0]
        return value - 0x10000 if value > 0x7FFF else value

    def read_firmware(self) -> str:
        pdu = self._read_pdu(read_holding_request(self.slave_addr, HR_FIRMWARE, 1), 7)
        value = parse_holding(pdu, 1)[0]
        return f"{value >> 8}.{value & 0xFF}"

    def read_status(self, include_firmware: bool = False) -> QuickLinkStatus:
        """Read lock, power and temperature atomically (same lock)."""
        with self._io_lock:
            lock = self.read_lock_state()
            power = self.read_power_state()
            temperature = self.read_temperature()
            firmware = self.read_firmware() if include_firmware else None
        return QuickLinkStatus(lock, power, temperature, firmware)

    # ------------------------------------------------------------------ writes
    def _write_coil(self, coil: int, value: bool) -> None:
        request = write_coil_request(self.slave_addr, coil, value)
        last_error: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                pdu = self._read_pdu(request, 8)
                parse_write_coil(pdu, coil, value)
                return
            except (QuickLinkTimeoutError, QuickLinkProtocolError) as exc:
                last_error = exc
                if attempt < self.retries and self.retry_backoff > 0:
                    time.sleep(self.retry_backoff)
        assert last_error is not None
        raise last_error

    def lock(self) -> None:
        """Lock the tool (also powers it on) and verify the interlock."""
        self._write_coil(COIL_LOCK, True)
        self._verify_interlock(LockState.LOCKED, PowerState.ON, "lock")

    def unlock(self) -> None:
        """Unlock the tool (also powers it off) and verify the interlock."""
        self._write_coil(COIL_LOCK, False)
        self._verify_interlock(LockState.UNLOCKED, PowerState.OFF, "unlock")

    def power_on(self) -> None:
        """Power the tool on independently of the lock for diagnostics."""
        self._write_coil(COIL_POWER, True)
        state = self.read_power_state()
        if state is not PowerState.ON:
            raise QuickLinkStateError(
                "power_on was acknowledged but the power state is off", power=state.name
            )

    def power_off(self) -> None:
        """Power the tool off independently of the lock for diagnostics."""
        self._write_coil(COIL_POWER, False)
        state = self.read_power_state()
        if state is not PowerState.OFF:
            raise QuickLinkStateError(
                "power_off was acknowledged but the power state is on", power=state.name
            )

    def _verify_interlock(
        self, expected_lock: LockState, expected_power: PowerState, action: str
    ) -> None:
        lock = self.read_lock_state()
        power = self.read_power_state()
        if lock is not expected_lock or power is not expected_power:
            raise QuickLinkStateError(
                f"{action} was acknowledged but the interlock state is inconsistent",
                expected=f"lock={expected_lock.name}, power={expected_power.name}",
                actual=f"lock={lock.name}, power={power.name}",
            )
