import pytest

from litearm_peripherals import LockState, PeripheralHub, QuickLink, WristFT
from litearm_peripherals.facade import HubStatus
from tests.fake_can import FakeFTSensor
from tests.fake_serial import FakeSerial


@pytest.fixture()
def fake_serial() -> FakeSerial:
    return FakeSerial("/dev/fake-hub", 115200)


def _quicklink(fake: FakeSerial) -> QuickLink:
    return QuickLink(
        port=fake.port,
        serial_factory=lambda *args, **kwargs: fake,
        timeout=0.05,
        tx_guard=0,
        retry_backoff=0,
    )


def test_hub_with_both_devices(fake_serial: FakeSerial) -> None:
    sensor = FakeFTSensor()
    hub = PeripheralHub(_quicklink(fake_serial), WristFT(transport=sensor.transport))
    hub.quicklink.open()
    hub.wrist_ft.open()
    status = hub.read_status()
    assert isinstance(status, HubStatus)
    assert status.quicklink is not None
    assert status.quicklink.lock is LockState.UNLOCKED
    assert status.wrist_ft is not None
    assert status.wrist_ft.fx == pytest.approx(6.2299, abs=1e-3)
    hub.close()


def test_open_only_quicklink(fake_serial: FakeSerial) -> None:
    hub = PeripheralHub.open(
        quicklink_port=fake_serial.port,
        with_wrist_ft=False,
        quicklink_kwargs={
            "serial_factory": lambda *args, **kwargs: fake_serial,
            "timeout": 0.05,
            "tx_guard": 0,
            "retry_backoff": 0,
        },
    )
    try:
        assert hub.quicklink is not None
        assert hub.wrist_ft is None
        status = hub.read_status()
        assert status.quicklink is not None
        assert status.wrist_ft is None
    finally:
        hub.close()


def test_close_is_idempotent_and_never_unlocks(fake_serial: FakeSerial) -> None:
    hub = PeripheralHub(_quicklink(fake_serial), None)
    hub.quicklink.open()
    hub.quicklink.lock()
    assert fake_serial.lock is True
    hub.close()
    assert fake_serial.lock is True
    hub.close()


def test_empty_hub() -> None:
    hub = PeripheralHub.open(with_quicklink=False, with_wrist_ft=False)
    status = hub.read_status()
    assert status.quicklink is None
    assert status.wrist_ft is None
    hub.close()
