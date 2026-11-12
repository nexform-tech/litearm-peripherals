import pytest

from litearm_peripherals._modbus import (
    crc16,
    pack_frame,
    parse_coils,
    parse_holding,
    parse_write_coil,
    read_coils_request,
    read_holding_request,
    unpack_frame,
    write_coil_request,
)
from litearm_peripherals.errors import QuickLinkProtocolError


@pytest.mark.parametrize(
    ("frame", "expected"),
    [
        (read_coils_request(1, 0, 1), "01 01 00 00 00 01 FD CA"),
        (read_coils_request(1, 0, 2), "01 01 00 00 00 02 BD CB"),
        (read_holding_request(1, 0, 2), "01 03 00 00 00 02 C4 0B"),
        (write_coil_request(1, 0, True), "01 05 00 00 FF 00 8C 3A"),
        (write_coil_request(1, 0, False), "01 05 00 00 00 00 CD CA"),
    ],
)
def test_standard_crc_vectors(frame: bytes, expected: str) -> None:
    assert frame.hex(" ").upper() == expected


def test_crc16_known_value() -> None:
    assert crc16(bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x02])) == 0x0BC4


def test_parse_coils() -> None:
    assert parse_coils(bytes([0x01, 0x01, 0x01]), 1) == [True]
    assert parse_coils(bytes([0x01, 0x01, 0x00]), 1) == [False]
    assert parse_coils(bytes([0x01, 0x01, 0b00000101]), 3) == [True, False, True]


def test_parse_holding() -> None:
    assert parse_holding(bytes([0x03, 0x02, 0xFF, 0xFB]), 1) == [0xFFFB]
    assert parse_holding(bytes([0x03, 0x04, 0x00, 0x01, 0x01, 0x0B]), 2) == [1, 0x010B]


def test_parse_write_coil_echo() -> None:
    parse_write_coil(bytes([0x05, 0x00, 0x00, 0xFF, 0x00]), 0, True)
    parse_write_coil(bytes([0x05, 0x00, 0x00, 0x00, 0x00]), 0, False)
    with pytest.raises(QuickLinkProtocolError):
        parse_write_coil(bytes([0x05, 0x00, 0x01, 0xFF, 0x00]), 0, True)


def test_unpack_validates_crc() -> None:
    frame = read_coils_request(1, 0, 1)
    assert unpack_frame(frame, 1) == bytes([0x01, 0x00, 0x00, 0x00, 0x01])
    corrupted = frame[:-1] + bytes([frame[-1] ^ 0xFF])
    with pytest.raises(QuickLinkProtocolError, match="CRC"):
        unpack_frame(corrupted, 1)


def test_unpack_validates_slave() -> None:
    frame = read_coils_request(2, 0, 1)
    with pytest.raises(QuickLinkProtocolError, match="slave"):
        unpack_frame(frame, 1)


def test_exception_response() -> None:
    frame = pack_frame(1, bytes([0x81, 0x02]))
    with pytest.raises(QuickLinkProtocolError, match="exception") as info:
        unpack_frame(frame, 1)
    assert info.value.context["code"] == 0x02


def test_short_response() -> None:
    with pytest.raises(QuickLinkProtocolError):
        unpack_frame(b"\x01\x01", 1)
    with pytest.raises(QuickLinkProtocolError):
        parse_coils(bytes([0x01, 0x08, 0x00]), 8)
