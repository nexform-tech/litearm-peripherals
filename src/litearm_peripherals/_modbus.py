"""Minimal Modbus RTU codec used by :class:`~litearm_peripherals.QuickLink`.

Only the three function codes the tool changer implements are supported:
``0x01`` read coils, ``0x03`` read holding registers, ``0x05`` write single coil.
Frames are standard Modbus RTU: slave address, PDU, then CRC16 (low byte first).
"""

from __future__ import annotations

from typing import List, Sequence, Union

from .errors import QuickLinkProtocolError

FC_READ_COILS = 0x01
FC_READ_HOLDING_REGISTERS = 0x03
FC_WRITE_SINGLE_COIL = 0x05
EXCEPTION_FLAG = 0x80

COIL_ON = 0xFF00
COIL_OFF = 0x0000


def crc16(data: bytes) -> int:
    """Return the standard Modbus RTU CRC16 of *data* (reflected poly 0xA001)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def pack_frame(slave: int, pdu: Sequence[int]) -> bytes:
    """Build ``slave + PDU + CRC`` as transmitted on the wire."""
    body = bytes([slave]) + bytes(pdu)
    checksum = crc16(body)
    return body + bytes([checksum & 0xFF, (checksum >> 8) & 0xFF])


def _validate_frame(frame: bytes, slave: int) -> bytes:
    """Validate CRC and slave address, return the PDU (raises on error)."""
    if len(frame) < 4:
        raise QuickLinkProtocolError(
            "Modbus response too short", length=len(frame), request_hex=frame.hex(" ")
        )
    body = frame[:-2]
    received = frame[-2] | (frame[-1] << 8)
    expected = crc16(body)
    if received != expected:
        raise QuickLinkProtocolError(
            "Modbus CRC mismatch",
            expected=f"0x{expected:04X}",
            actual=f"0x{received:04X}",
            request_hex=frame.hex(" "),
        )
    if body[0] != slave:
        raise QuickLinkProtocolError(
            "Unexpected Modbus slave address",
            expected=slave,
            actual=body[0],
            request_hex=frame.hex(" "),
        )
    pdu = body[1:]
    if not pdu:
        raise QuickLinkProtocolError("Empty Modbus PDU", request_hex=frame.hex(" "))
    if pdu[0] & EXCEPTION_FLAG:
        code = pdu[1] if len(pdu) > 1 else 0
        raise QuickLinkProtocolError(
            f"Modbus exception 0x{code:02X}",
            function=pdu[0] & ~EXCEPTION_FLAG,
            code=code,
            request_hex=frame.hex(" "),
        )
    return pdu


def unpack_frame(frame: bytes, slave: int) -> bytes:
    """Validate a response frame and return its PDU."""
    return _validate_frame(bytes(frame), slave)


# --------------------------------------------------------------------------- requests
def _build(slave: int, function: int, address: int, value: int) -> bytes:
    for name, number in (("slave", slave), ("address", address), ("value", value)):
        if not 0 <= number <= 0xFFFF:
            raise ValueError(f"{name} out of range: {number}")
    pdu = bytes(
        [function, (address >> 8) & 0xFF, address & 0xFF, (value >> 8) & 0xFF, value & 0xFF]
    )
    return pack_frame(slave, pdu)


def read_coils_request(slave: int, start: int, quantity: int) -> bytes:
    return _build(slave, FC_READ_COILS, start, quantity)


def read_holding_request(slave: int, start: int, quantity: int) -> bytes:
    return _build(slave, FC_READ_HOLDING_REGISTERS, start, quantity)


def write_coil_request(slave: int, coil: int, value: Union[bool, int]) -> bytes:
    raw = COIL_ON if bool(value) else COIL_OFF
    return _build(slave, FC_WRITE_SINGLE_COIL, coil, raw)


# --------------------------------------------------------------------------- responses
def _expect_function(pdu: bytes, function: int) -> None:
    if not pdu or pdu[0] != function:
        actual = f"0x{pdu[0]:02X}" if pdu else "empty"
        raise QuickLinkProtocolError(
            "Unexpected Modbus function code", expected=f"0x{function:02X}", actual=actual
        )


def parse_coils(pdu: bytes, quantity: int) -> List[bool]:
    """Decode an FC01 response into *quantity* booleans (LSB first)."""
    _expect_function(pdu, FC_READ_COILS)
    if len(pdu) < 2:
        raise QuickLinkProtocolError("FC01 response missing byte count")
    byte_count = pdu[1]
    if byte_count < (quantity + 7) // 8 or len(pdu) < 2 + byte_count:
        raise QuickLinkProtocolError(
            "FC01 response shorter than expected",
            expected=2 + (quantity + 7) // 8,
            actual=len(pdu),
        )
    data = pdu[2 : 2 + byte_count]
    return [bool(data[index // 8] & (1 << (index % 8))) for index in range(quantity)]


def parse_holding(pdu: bytes, quantity: int) -> List[int]:
    """Decode an FC03 response into *quantity* unsigned 16-bit registers."""
    _expect_function(pdu, FC_READ_HOLDING_REGISTERS)
    if len(pdu) < 2:
        raise QuickLinkProtocolError("FC03 response missing byte count")
    byte_count = pdu[1]
    if byte_count < quantity * 2 or len(pdu) < 2 + byte_count:
        raise QuickLinkProtocolError(
            "FC03 response shorter than expected",
            expected=2 + quantity * 2,
            actual=len(pdu),
        )
    return [
        (pdu[2 + index * 2] << 8) | pdu[3 + index * 2]
        for index in range(quantity)
    ]


def parse_write_coil(pdu: bytes, coil: int, value: bool) -> None:
    """Verify that an FC05 response echoes the request."""
    _expect_function(pdu, FC_WRITE_SINGLE_COIL)
    if len(pdu) < 5:
        raise QuickLinkProtocolError("FC05 response too short", actual=len(pdu))
    echo_coil = (pdu[1] << 8) | pdu[2]
    echo_value = (pdu[3] << 8) | pdu[4]
    expected_value = COIL_ON if value else COIL_OFF
    if echo_coil != coil or echo_value != expected_value:
        raise QuickLinkProtocolError(
            "FC05 response does not echo the request",
            expected=f"coil=0x{coil:04X}, value=0x{expected_value:04X}",
            actual=f"coil=0x{echo_coil:04X}, value=0x{echo_value:04X}",
        )
