import pytest

from litearm_peripherals import Sample, WristFT
from litearm_peripherals.errors import WristFTIdChangeError, WristFTTimeoutError
from tests.fake_can import FakeCanTransport, FakeFTSensor


@pytest.fixture()
def sensor() -> FakeFTSensor:
    return FakeFTSensor()


@pytest.fixture()
def ft(sensor: FakeFTSensor):
    instance = WristFT(transport=sensor.transport, timeout=0.05)
    yield instance
    instance.close()


def test_read_sample(ft: WristFT) -> None:
    sample = ft.read()
    assert isinstance(sample, Sample)
    assert sample.fx == pytest.approx(6.2299, abs=1e-3)
    assert sample.mz == pytest.approx(0.3359, abs=1e-3)
    assert sample.endian == "little"
    assert ft.endian == "little"


def test_start_frame_is_sent(ft: WristFT, sensor: FakeFTSensor) -> None:
    ft.read()
    first = sensor.transport.sent[0]
    assert first.can_id == 0x10
    assert first.data == bytes([0x8A, 0x00, 0x0A])


def test_read_timeout_raises() -> None:
    empty = WristFT(transport=FakeCanTransport(), auto_start=False, timeout=0.02)
    with pytest.raises(WristFTTimeoutError):
        empty.read()


def test_stream_stops_what_it_started(ft: WristFT, sensor: FakeFTSensor) -> None:
    stream = ft.stream(10)
    sample = next(stream)
    assert sample.fz == pytest.approx(-7.5578, abs=1e-3)
    stream.close()
    stops = [frame for frame in sensor.transport.sent if frame.data == bytes([0x8A, 0, 0])]
    assert len(stops) == 1


def test_probe_finds_three_consecutive_ids() -> None:
    sensor = FakeFTSensor(samples_per_start=4)
    ft = WristFT(transport=sensor.transport, timeout=0.05)
    candidates = ft.probe(duration=0.15, start_ms=10)
    assert candidates
    assert candidates[0].base == 0x15
    assert candidates[0].plausible is True
    assert ft.base == 0x15


def test_set_id_updates_local_state(ft: WristFT, sensor: FakeFTSensor) -> None:
    ft.read()
    ft.set_id(0x10, 0x20)
    assert sensor.base == 0x20
    assert ft.base == 0x20
    assert ft.recv == 0x10


def test_set_id_failure_keeps_local_state(
    ft: WristFT, sensor: FakeFTSensor, monkeypatch: pytest.MonkeyPatch
) -> None:
    sensor.ignore_set_id = True
    monkeypatch.setattr(ft, "_verify_uploading", lambda *args, **kwargs: False)
    with pytest.raises(WristFTIdChangeError):
        ft.set_id(0x10, 0x20)
    assert ft.base == 0x15
    assert ft.recv == 0x10


def test_reset_id() -> None:
    sensor = FakeFTSensor(base=0x20, recv=0x10)
    sensor.uploading = True
    ft = WristFT(transport=sensor.transport, base=0x20, timeout=0.05)
    ft.reset_id()
    assert sensor.base == 0x15
    assert ft.base == 0x15


def test_read_raw(ft: WristFT, sensor: FakeFTSensor) -> None:
    sensor.transport.feed(0x15, b"\x01\x02\x03\x04\x05\x06\x07\x08")
    frame = ft.read_raw(0.05)
    assert frame == (0x15, 8, b"\x01\x02\x03\x04\x05\x06\x07\x08")


def test_close_closes_transport(ft: WristFT, sensor: FakeFTSensor) -> None:
    ft.close()
    assert sensor.transport.closed is True
    assert ft.is_open is False
