"""In-memory CAN transport and a tiny WRJST sensor model for offline tests."""

from __future__ import annotations

import queue
import struct
from typing import Iterable, Optional, Tuple

from litearm_peripherals._can import CanFrame
from litearm_peripherals.wrist_ft import (
    CMD_RESET,
    CMD_SET_HDR,
    DEFAULT_RECV,
    DEFAULT_SEND,
)


class FakeCanTransport:
    def __init__(self) -> None:
        self.sent: list[CanFrame] = []
        self.queue: "queue.Queue[CanFrame]" = queue.Queue()
        self.closed = False
        self.on_send = None

    def send(self, frame: CanFrame) -> None:
        self.sent.append(frame)
        if self.on_send is not None:
            self.on_send(frame, self)

    def recv(self, timeout: Optional[float] = None) -> Optional[CanFrame]:
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        self.closed = True

    def feed(self, can_id: int, data: bytes, dlc: int = 8) -> None:
        self.queue.put(CanFrame(can_id, bytes(data), dlc))


class FakeFTSensor:
    """Emits three-frame samples on start and supports id changes in memory."""

    def __init__(
        self,
        base: int = DEFAULT_SEND,
        recv: int = DEFAULT_RECV,
        values: Tuple[float, ...] = (6.2299, -6.8937, -7.5578, 0.1045, -0.0430, 0.3359),
        samples_per_start: int = 4,
    ) -> None:
        self.base = base
        self.recv = recv
        self.values = values
        self.samples_per_start = samples_per_start
        self.uploading = False
        self.ignore_set_id = False
        self.transport = FakeCanTransport()
        self.transport.on_send = self._on_send

    def emit_sample(self, values: Optional[Iterable[float]] = None) -> None:
        data = tuple(values) if values is not None else self.values
        for index in range(3):
            payload = struct.pack("<ff", data[index * 2], data[index * 2 + 1])
            self.transport.feed(self.base + index, payload)

    def _on_send(self, frame: CanFrame, transport: FakeCanTransport) -> None:
        data = frame.data
        if frame.can_id in (self.recv, self.base) and data[:2] == CMD_SET_HDR:
            if self.ignore_set_id:
                return
            self.recv = int.from_bytes(data[2:4], "big")
            self.base = int.from_bytes(data[4:6], "big")
            if self.uploading:
                self.emit_sample()
            return
        if frame.can_id == 0x7FF and data == CMD_RESET:
            self.recv, self.base = DEFAULT_RECV, DEFAULT_SEND
            if self.uploading:
                self.emit_sample()
            return
        if frame.can_id == self.recv and len(data) >= 3 and data[0] == 0x8A:
            interval = int.from_bytes(data[1:3], "big")
            self.uploading = interval > 0
            if self.uploading:
                for _ in range(self.samples_per_start):
                    self.emit_sample()
