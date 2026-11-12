import pytest

from litearm_peripherals.errors import WristFTProtocolError
from litearm_peripherals.wrist_ft import (
    decode_pair,
    decode_sample,
    detect_endian,
    plausible,
    set_id_payload,
    start_payload,
)

SAMPLE_FRAMES = {
    0x15: bytes.fromhex("79 5B C7 40 10 99 DC C0"),
    0x16: bytes.fromhex("B7 D9 F1 C0 3C 0B D6 3D"),
    0x17: bytes.fromhex("92 21 30 BD 93 FB AB 3E"),
}


def test_decode_measured_sample() -> None:
    sample = decode_sample(SAMPLE_FRAMES)
    expected = (6.2299, -6.8937, -7.5578, 0.10451, -0.04300, 0.33590)
    for actual, wanted in zip(sample.as_tuple(), expected):
        assert actual == pytest.approx(wanted, abs=1e-3)
    assert sample.endian == "little"
    assert sample.force_magnitude == pytest.approx(11.9773, abs=1e-3)
    assert sample.torque_magnitude == pytest.approx(0.3544, abs=1e-3)


def test_big_endian_is_implausible() -> None:
    ordered = [SAMPLE_FRAMES[0x15], SAMPLE_FRAMES[0x16], SAMPLE_FRAMES[0x17]]
    assert detect_endian(ordered) == "little"
    big_values = [value for data in ordered for value in decode_pair(data, "big")]
    assert plausible(big_values) is False


def test_missing_frame_raises() -> None:
    with pytest.raises(WristFTProtocolError, match="Missing"):
        decode_sample({0x15: SAMPLE_FRAMES[0x15], 0x16: SAMPLE_FRAMES[0x16]})


def test_short_frame_raises() -> None:
    with pytest.raises(WristFTProtocolError, match="shorter"):
        decode_pair(b"\x00\x01")


def test_start_payload() -> None:
    assert start_payload(10) == bytes([0x8A, 0x00, 0x0A])
    assert start_payload(0) == bytes([0x8A, 0x00, 0x00])
    assert start_payload(0x1_0000) == bytes([0x8A, 0xFF, 0xFF])


def test_set_id_payload() -> None:
    assert set_id_payload(0x10, 0x20) == bytes(
        [0xDE, 0xAA, 0x00, 0x10, 0x00, 0x20, 0x0D, 0x0A]
    )
    with pytest.raises(ValueError):
        set_id_payload(0x10, 0x7FE)
