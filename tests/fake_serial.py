"""Pyserial-compatible fake that emulates the Handsfree Quick Link device."""

from __future__ import annotations

from typing import List, Optional

from litearm_peripherals._modbus import crc16, pack_frame


class FakeSerial:
    def __init__(self, port: str, baudrate: int, timeout: Optional[float] = None) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_open = True
        self.writes: List[bytes] = []
        self.lock = False
        self.power = False
        self.temperature = 25
        self.firmware = 0x010B  # 1.11
        self.drop_responses = 0
        self.corrupt_responses = 0
        self.exception_code: Optional[int] = None
        self.break_interlock = False
        self._rx = bytearray()

    @property
    def in_waiting(self) -> int:
        return len(self._rx)

    def reset_input_buffer(self) -> None:
        self._rx.clear()

    def write(self, data: bytes) -> int:
        request = bytes(data)
        self.writes.append(request)
        if self.drop_responses > 0:
            self.drop_responses -= 1
            return len(request)
        response = self._handle(request)
        if response:
            if self.corrupt_responses > 0:
                self.corrupt_responses -= 1
                response = response[:-1] + bytes([response[-1] ^ 0xFF])
            self._rx.extend(response)
        return len(request)

    def read(self, size: int = 1) -> bytes:
        if not self._rx:
            return b""
        chunk = bytes(self._rx[:size])
        del self._rx[:size]
        return chunk

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.is_open = False

    # ------------------------------------------------------------------ device model
    def _handle(self, request: bytes) -> bytes:
        if len(request) < 4:
            return b""
        body = request[:-2]
        received = request[-2] | (request[-1] << 8)
        if crc16(body) != received:
            return b""
        slave, function = body[0], body[1]
        if slave != 1:
            return b""
        if self.exception_code is not None:
            return pack_frame(slave, bytes([function | 0x80, self.exception_code]))
        if function == 0x05:
            return self._write_coil(slave, body, request)
        if function == 0x01:
            return self._read_coils(slave, body)
        if function == 0x03:
            return self._read_registers(slave, body)
        return pack_frame(slave, bytes([function | 0x80, 0x01]))

    def _write_coil(self, slave: int, body: bytes, request: bytes) -> bytes:
        coil = (body[2] << 8) | body[3]
        value = (body[4] << 8) | body[5] == 0xFF00
        if coil == 0x0000:
            self.lock = value
            self.power = value if not self.break_interlock else not value
        elif coil == 0x0001:
            self.power = value
        else:
            return pack_frame(slave, bytes([0x85, 0x02]))
        return request

    def _read_coils(self, slave: int, body: bytes) -> bytes:
        address = (body[2] << 8) | body[3]
        quantity = (body[4] << 8) | body[5]
        bits = 0
        if address == 0x0000 and self.lock:
            bits |= 0x01
        if address == 0x0001 and self.power:
            bits |= 0x01
        return pack_frame(slave, bytes([0x01, (quantity + 7) // 8, bits]))

    def _read_registers(self, slave: int, body: bytes) -> bytes:
        address = (body[2] << 8) | body[3]
        quantity = (body[4] << 8) | body[5]
        values = []
        for offset in range(quantity):
            if address + offset == 0x0000:
                values.append(self.temperature & 0xFFFF)
            elif address + offset == 0x0001:
                values.append(self.firmware & 0xFFFF)
            else:
                values.append(0)
        payload = bytearray([0x03, quantity * 2])
        for value in values:
            payload.extend([(value >> 8) & 0xFF, value & 0xFF])
        return pack_frame(slave, bytes(payload))
