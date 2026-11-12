"""Raw Linux SocketCAN transport for the WRJST force/torque sensor.

The transport is deliberately tiny and injectable: :class:`WristFT` accepts any
object implementing :class:`CanTransport`, which lets tests feed frames from a
queue without touching a CAN interface.
"""

from __future__ import annotations

import select
import socket
import struct
import time
from dataclasses import dataclass
from typing import Optional, Protocol

from .errors import WristFTConnectionError, WristFTProtocolError

CAN_FRAME_FMT = "=IB3x8s"  # struct can_frame: id, dlc, 3 padding bytes, 8 data bytes
CAN_FRAME_SIZE = struct.calcsize(CAN_FRAME_FMT)
CAN_SFF_MASK = 0x7FF
CAN_EFF_FLAG = 0x80000000
CAN_RTR_FLAG = 0x40000000
CAN_ERR_FLAG = 0x20000000

AF_CAN = getattr(socket, "AF_CAN", 29)
CAN_RAW = getattr(socket, "CAN_RAW", 1)


@dataclass(frozen=True)
class CanFrame:
    """A classic CAN frame with a standard 11-bit identifier."""

    can_id: int
    data: bytes
    dlc: int = 8


class CanTransport(Protocol):
    """Minimal transport interface consumed by :class:`WristFT`."""

    def send(self, frame: CanFrame) -> None: ...

    def recv(self, timeout: Optional[float] = None) -> Optional[CanFrame]: ...

    def close(self) -> None: ...


def setup_hint(iface: str = "can0", bitrate: int = 1000000) -> str:
    """Return shell commands that bring a CAN interface up at *bitrate*."""
    return (
        f"Bring {iface} up at {bitrate} bit/s before using WristFT:\n"
        f"  sudo ip link set {iface} down\n"
        f"  sudo ip link set {iface} type can bitrate {bitrate}\n"
        f"  sudo ip link set {iface} up\n"
        "For slcan adapters (e.g. CANable2):\n"
        f"  sudo slcand -o -c -f -s8 /dev/ttyACM0 {iface}\n"
        f"  sudo ip link set {iface} up\n"
        f"Check with: ip -details link show {iface}"
    )


class SocketCanTransport:
    """SocketCAN transport bound to one interface (default ``can0``)."""

    def __init__(self, iface: str = "can0") -> None:
        self.iface = iface
        self._sock: Optional[socket.socket] = None
        self._open()

    def _open(self) -> None:
        try:
            sock = socket.socket(AF_CAN, socket.SOCK_RAW, CAN_RAW)
            sock.bind((self.iface,))
        except OSError as exc:
            raise WristFTConnectionError(
                f"Cannot open CAN interface {self.iface}: {exc}",
                iface=self.iface,
                hint=setup_hint(self.iface),
            ) from exc
        except AttributeError as exc:  # pragma: no cover - non-Linux Python
            raise WristFTConnectionError(
                "SocketCAN is only available on Linux", iface=self.iface
            ) from exc
        self._sock = sock

    def _require_socket(self) -> socket.socket:
        if self._sock is None:
            raise WristFTConnectionError("CAN transport is closed", iface=self.iface)
        return self._sock

    def send(self, frame: CanFrame) -> None:
        if not 0 <= frame.can_id <= CAN_SFF_MASK:
            raise WristFTProtocolError(
                "Standard CAN id out of range", can_id=frame.can_id
            )
        data = bytes(frame.data)
        if len(data) > 8:
            raise WristFTProtocolError("CAN payload exceeds 8 bytes", length=len(data))
        raw = struct.pack(CAN_FRAME_FMT, frame.can_id, len(data), data.ljust(8, b"\x00"))
        try:
            self._require_socket().send(raw)
        except OSError as exc:
            raise WristFTConnectionError(
                f"CAN send failed on {self.iface}: {exc}",
                iface=self.iface,
                can_id=frame.can_id,
            ) from exc

    def recv(self, timeout: Optional[float] = None) -> Optional[CanFrame]:
        sock = self._require_socket()
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            if deadline is None:
                wait: Optional[float] = None
            else:
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                wait = min(left, 0.1)
            try:
                ready, _, _ = select.select([sock], [], [], wait)
            except InterruptedError:
                continue
            except OSError as exc:
                raise WristFTConnectionError(
                    f"CAN select failed on {self.iface}: {exc}", iface=self.iface
                ) from exc
            if not ready:
                continue
            try:
                raw = sock.recv(CAN_FRAME_SIZE)
            except OSError as exc:
                raise WristFTConnectionError(
                    f"CAN receive failed on {self.iface}: {exc}", iface=self.iface
                ) from exc
            if len(raw) != CAN_FRAME_SIZE:
                continue
            can_id, dlc, data = struct.unpack(CAN_FRAME_FMT, raw)
            if can_id & (CAN_EFF_FLAG | CAN_RTR_FLAG | CAN_ERR_FLAG):
                continue
            if dlc > 8:
                continue
            return CanFrame(can_id & CAN_SFF_MASK, data[:dlc], dlc)

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
