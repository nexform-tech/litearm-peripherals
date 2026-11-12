"""WRJST six-axis force/torque sensor driver (raw SocketCAN, 1 Mbit/s).

Protocol (measured on hardware):

* standard 11-bit frames, default 1 Mbit/s;
* host receive id ``0x10``, sensor send/base id ``0x15``;
* upload uses three consecutive ids, two IEEE-754 floats per 8-byte frame::

      0x15: Fx (N)   Fy (N)
      0x16: Fz (N)   Mx (Nm)
      0x17: My (Nm)  Mz (Nm)

* integer fields are big-endian, but the payload floats are little-endian
  (the manual claims big-endian; byte order is detected from plausibility);
* upload only starts after ``8A msH msL`` is sent to the receive id;
* ``set_id`` / ``reset_id`` are stored in flash and survive power cycles.
"""

from __future__ import annotations

import math
import struct
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple

from ._can import CanFrame, CanTransport, SocketCanTransport
from .errors import (
    WristFTConnectionError,
    WristFTIdChangeError,
    WristFTProtocolError,
    WristFTTimeoutError,
)

DEFAULT_RECV = 0x10
DEFAULT_SEND = 0x15

CMD_START = 0x8A
CMD_RESET = bytes([0xDE, 0xDE, 0xDE, 0x0D, 0x0A])
CMD_SET_HDR = bytes([0xDE, 0xAA])
CMD_END = bytes([0x0D, 0x0A])

SLOTS = ("Fx", "Fy", "Fz", "Mx", "My", "Mz")
UNITS = ("N", "N", "N", "Nm", "Nm", "Nm")


@dataclass(frozen=True)
class Sample:
    """One complete force/torque sample; forces in N, torques in Nm."""

    fx: float
    fy: float
    fz: float
    mx: float
    my: float
    mz: float
    timestamp: float = 0.0
    endian: str = "little"

    def as_tuple(self) -> Tuple[float, float, float, float, float, float]:
        return (self.fx, self.fy, self.fz, self.mx, self.my, self.mz)

    @property
    def force_magnitude(self) -> float:
        return math.sqrt(self.fx**2 + self.fy**2 + self.fz**2)

    @property
    def torque_magnitude(self) -> float:
        return math.sqrt(self.mx**2 + self.my**2 + self.mz**2)


@dataclass(frozen=True)
class Candidate:
    """A consecutive three-id group that looks like sensor data."""

    base: int
    rate: float
    endian: str
    values: Tuple[float, ...]
    plausible: bool


# --------------------------------------------------------------------------- codec
def start_payload(interval_ms: int) -> bytes:
    """Build the start frame; ``interval_ms=0`` stops the upload."""
    milliseconds = max(0, min(0xFFFF, int(interval_ms)))
    return bytes([CMD_START, (milliseconds >> 8) & 0xFF, milliseconds & 0xFF])


def set_id_payload(new_recv: int, new_send: int) -> bytes:
    """Build the id-change frame (``DE AA RO R1 S0 S1 0D 0A``, big-endian ids)."""
    if not 0 <= new_recv <= 0x7FF:
        raise ValueError("new_recv must fit in 11 bits")
    if not 0 <= new_send <= 0x7FD:
        raise ValueError("new_send must be <= 0x7FD")
    return CMD_SET_HDR + new_recv.to_bytes(2, "big") + new_send.to_bytes(2, "big") + CMD_END


def fmt_hex(data: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in data)


def decode_pair(data: bytes, endian: str = "little") -> Tuple[float, float]:
    """Decode eight bytes into two floats."""
    if len(data) < 8:
        raise WristFTProtocolError("Force/torque payload is shorter than 8 bytes", length=len(data))
    fmt = "<ff" if endian == "little" else ">ff"
    return struct.unpack(fmt, bytes(data)[:8])


def plausible(values: Any) -> bool:
    """Heuristic: finite, bounded, and not an all-zero payload."""
    values = tuple(values)
    if not all(math.isfinite(value) and abs(value) < 1e5 for value in values):
        return False
    return any(abs(value) > 1e-6 for value in values)


def detect_endian(frames: Any) -> str:
    """Return ``"little"`` or ``"big"`` based on which decode looks plausible."""
    for endian in ("little", "big"):
        values: List[float] = []
        for data in frames:
            values.extend(decode_pair(data, endian))
        if plausible(values):
            return endian
    return "little"


def decode_sample(
    frames: Mapping[int, bytes],
    base: int = DEFAULT_SEND,
    endian: str = "auto",
    timestamp: Optional[float] = None,
) -> Sample:
    """Decode ``{can_id: data}`` for ids ``base``, ``base+1``, ``base+2``.

    Useful for offline analysis of candump logs and in tests.
    """
    ordered: List[bytes] = []
    for offset in range(3):
        can_id = base + offset
        if can_id not in frames:
            raise WristFTProtocolError(
                "Missing force/torque frame", can_id=f"0x{can_id:02X}", base=f"0x{base:02X}"
            )
        data = bytes(frames[can_id])
        if len(data) < 8:
            raise WristFTProtocolError(
                "Force/torque frame is shorter than 8 bytes",
                can_id=f"0x{can_id:02X}",
                length=len(data),
            )
        ordered.append(data[:8])
    if endian not in ("auto", "little", "big"):
        raise ValueError("endian must be 'auto', 'little' or 'big'")
    resolved = detect_endian(ordered) if endian == "auto" else endian
    values = [value for data in ordered for value in decode_pair(data, resolved)]
    return Sample(
        *values,
        timestamp=time.time() if timestamp is None else timestamp,
        endian=resolved,
    )


def _find_triples(stats: Mapping[int, Dict[str, Any]], duration: float) -> List[Candidate]:
    candidates: List[Candidate] = []
    for base in sorted(stats):
        group = [stats.get(base + offset) for offset in range(3)]
        if not all(
            entry is not None
            and entry["dlc8"] >= 3
            and entry["dlc8"] >= 0.5 * entry["n"]
            for entry in group
        ):
            continue
        frames = [entry["last"] for entry in group]  # type: ignore[index]
        endian = detect_endian(frames)
        values: List[float] = []
        for data in frames:
            values.extend(decode_pair(data, endian))
        rate = min(entry["n"] for entry in group) / max(duration, 1e-9)  # type: ignore[index]
        candidates.append(
            Candidate(
                base=base,
                rate=rate,
                endian=endian,
                values=tuple(values),
                plausible=plausible(values),
            )
        )
    candidates.sort(key=lambda item: (not item.plausible, item.base != DEFAULT_SEND, -item.rate))
    return candidates


class WristFT:
    """Synchronous driver for one WRJST six-axis sensor.

    Example::

        with WristFT(iface="can0") as ft:
            ft.start(10)                 # 100 Hz upload
            sample = ft.read(timeout=1.0)
            print(sample.fx, sample.fy, sample.fz,
                  sample.mx, sample.my, sample.mz)
    """

    def __init__(
        self,
        iface: str = "can0",
        base: int = DEFAULT_SEND,
        recv: int = DEFAULT_RECV,
        endian: str = "auto",
        timeout: float = 0.5,
        transport: Optional[CanTransport] = None,
        auto_start: bool = True,
        interval_ms: int = 10,
    ) -> None:
        if endian not in ("auto", "little", "big"):
            raise ValueError("endian must be 'auto', 'little' or 'big'")
        if not 0 <= base <= 0x7FD:
            raise ValueError("base id must leave room for base+1 and base+2")
        if not 0 <= recv <= 0x7FF:
            raise ValueError("recv id must fit in 11 bits")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.iface = iface
        self.base = base
        self.recv = recv
        self.timeout = timeout
        self.auto_start = auto_start
        self.interval_ms = interval_ms
        self._endian = endian
        self._endian_is_auto = endian == "auto"
        self._transport = transport
        self._lock = threading.RLock()
        self._started = False

    # ------------------------------------------------------------------ lifecycle
    @property
    def is_open(self) -> bool:
        return self._transport is not None

    @property
    def endian(self) -> str:
        return self._endian

    def open(self) -> "WristFT":
        with self._lock:
            if self._transport is None:
                self._transport = SocketCanTransport(self.iface)
            return self

    def close(self) -> None:
        with self._lock:
            if self._transport is not None:
                self._transport.close()
                self._transport = None
            self._started = False

    def __enter__(self) -> "WristFT":
        return self.open()

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _require_transport(self) -> CanTransport:
        if self._transport is None:
            raise WristFTConnectionError(
                "WristFT is not open; call open() or use 'with WristFT(...)'",
                iface=self.iface,
            )
        return self._transport

    def _send(self, can_id: int, data: bytes) -> None:
        self._require_transport().send(CanFrame(can_id, bytes(data), len(data)))

    # ------------------------------------------------------------------ upload control
    def start(self, interval_ms: int = 10) -> None:
        """Start the sensor upload (``interval_ms=0`` stops it)."""
        with self._lock:
            self._send(self.recv, start_payload(interval_ms))
            self._started = interval_ms > 0
            self.interval_ms = interval_ms

    def stop(self) -> None:
        """Stop the sensor upload."""
        self.start(0)

    def _start_upload_on(self, recv: int, interval_ms: int = 10) -> None:
        self._send(recv, start_payload(interval_ms))

    # ------------------------------------------------------------------ reading
    def _recv_sample(self, timeout: float) -> Optional[Sample]:
        transport = self._require_transport()
        frames: Dict[int, bytes] = {}
        resolved: Optional[str] = None if self._endian == "auto" else self._endian
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            frame = transport.recv(min(remaining, 0.1))
            if frame is None:
                continue
            offset = frame.can_id - self.base
            if not 0 <= offset <= 2 or frame.dlc != 8 or len(frame.data) < 8:
                continue
            frames[offset] = frame.data[:8]
            if len(frames) == 3:
                ordered = [frames[index] for index in range(3)]
                if resolved is None:
                    resolved = detect_endian(ordered)
                    self._endian = resolved
                values = [value for data in ordered for value in decode_pair(data, resolved)]
                return Sample(*values, timestamp=time.time(), endian=resolved)

    def read(self, timeout: Optional[float] = None) -> Sample:
        """Read one complete sample, raising on timeout."""
        limit = self.timeout if timeout is None else timeout
        with self._lock:
            if self.auto_start and not self._started:
                self.start(self.interval_ms)
            sample = self._recv_sample(limit)
            if sample is None:
                raise WristFTTimeoutError(
                    "No complete force/torque sample received",
                    iface=self.iface,
                    base=f"0x{self.base:02X}",
                    hint=(
                        "the sensor only uploads after the start frame; call start() "
                        "or use probe(start_ms=...) and check that the interface is at 1 Mbit/s"
                    ),
                )
            return sample

    def read_raw(self, timeout: Optional[float] = None) -> Optional[Tuple[int, int, bytes]]:
        """Receive one raw standard frame as ``(can_id, dlc, data)``."""
        limit = self.timeout if timeout is None else timeout
        frame = self._require_transport().recv(limit)
        if frame is None:
            return None
        return frame.can_id, frame.dlc, frame.data

    def stream(self, interval_ms: int = 10) -> Iterator[Sample]:
        """Yield samples until the consumer stops or the connection fails."""
        with self._lock:
            started_here = not self._started
            self.start(interval_ms)
        try:
            while True:
                yield self.read(self.timeout)
        finally:
            if started_here:
                with self._lock:
                    try:
                        self.stop()
                    finally:
                        self._started = False

    # ------------------------------------------------------------------ discovery
    def _collect(self, duration: float) -> Dict[int, Dict[str, Any]]:
        transport = self._require_transport()
        stats: Dict[int, Dict[str, Any]] = {}
        deadline = time.monotonic() + duration
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            frame = transport.recv(min(remaining, 0.1))
            if frame is None:
                continue
            entry = stats.setdefault(frame.can_id, {"n": 0, "dlc8": 0, "last": b""})
            entry["n"] += 1
            if frame.dlc == 8 and len(frame.data) >= 8:
                entry["dlc8"] += 1
                entry["last"] = frame.data[:8]
        return stats

    def probe(self, duration: float = 3.0, start_ms: Optional[int] = None) -> List[Candidate]:
        """Scan the bus for three consecutive ids carrying plausible floats."""
        with self._lock:
            if start_ms is not None:
                self.start(start_ms)
            stats = self._collect(duration)
            candidates = _find_triples(stats, duration)
            if candidates and candidates[0].plausible:
                self.base = candidates[0].base
        return candidates

    def _count_base(self, base: int, timeout: float) -> Dict[int, int]:
        transport = self._require_transport()
        seen = {base: 0, base + 1: 0, base + 2: 0}
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            frame = transport.recv(min(remaining, 0.1))
            if frame is None:
                continue
            if frame.dlc == 8 and frame.can_id in seen:
                seen[frame.can_id] += 1
        return seen

    def _verify_uploading(self, base: int, recv: int, timeout: float = 1.2) -> bool:
        seen = self._count_base(base, 0.3)
        if any(seen.values()):
            return True
        self._start_upload_on(recv, 10)
        seen = self._count_base(base, timeout)
        return any(seen.values())

    # ------------------------------------------------------------------ id change
    def set_id(self, new_recv: int, new_send: int) -> None:
        """Change the sensor receive/send ids and verify the new upload.

        The write is stored in flash.  On failure the local ids are left
        unchanged and :class:`WristFTIdChangeError` is raised; use
        :meth:`probe` to rediscover the sensor.
        """
        payload = set_id_payload(new_recv, new_send)
        with self._lock:
            targets = [self.recv]
            if self.base != self.recv:
                targets.append(self.base)
            for target in targets:
                self._send(target, payload)
                if self._verify_uploading(new_send, new_recv):
                    self.recv, self.base = new_recv, new_send
                    if self._endian_is_auto:
                        self._endian = "auto"
                    return
            raise WristFTIdChangeError(
                "Could not verify the new sensor ids; the sensor state is unknown",
                attempted_recv=new_recv,
                attempted_send=new_send,
                hint="run probe() to rediscover the sensor, then reset_id() if needed",
            )

    def reset_id(self) -> None:
        """Broadcast the factory ids (``0x10``/``0x15``) and verify them."""
        with self._lock:
            self._send(0x7FF, CMD_RESET)
            if not self._verify_uploading(DEFAULT_SEND, DEFAULT_RECV):
                raise WristFTIdChangeError(
                    "Could not verify the factory ids after reset",
                    attempted_recv=DEFAULT_RECV,
                    attempted_send=DEFAULT_SEND,
                    hint="run probe() to see which ids are currently uploading",
                )
            self.recv, self.base = DEFAULT_RECV, DEFAULT_SEND
            if self._endian_is_auto:
                self._endian = "auto"

    def send_raw(self, can_id: int, data: bytes) -> None:
        """Send an arbitrary standard frame (advanced use only)."""
        self._send(can_id, data)
