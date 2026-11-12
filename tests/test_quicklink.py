from concurrent.futures import ThreadPoolExecutor

import pytest

from litearm_peripherals import LockState, PowerState, QuickLink
from litearm_peripherals.errors import (
    QuickLinkConnectionError,
    QuickLinkStateError,
    QuickLinkTimeoutError,
)
from tests.fake_serial import FakeSerial


@pytest.fixture()
def fake() -> FakeSerial:
    return FakeSerial("/dev/fake-quicklink", 115200)


@pytest.fixture()
def tool(fake: FakeSerial):
    def factory(port: str, baudrate: int, timeout: float = 0.5) -> FakeSerial:
        return fake

    instance = QuickLink(
        port=fake.port,
        serial_factory=factory,
        timeout=0.05,
        retries=2,
        tx_guard=0,
        retry_backoff=0,
    ).open()
    yield instance
    instance.close()


def test_read_status(tool: QuickLink) -> None:
    status = tool.read_status(include_firmware=True)
    assert status.lock is LockState.UNLOCKED
    assert status.power is PowerState.OFF
    assert status.temperature_c == 25
    assert status.firmware == "1.11"


def test_signed_temperature(tool: QuickLink, fake: FakeSerial) -> None:
    fake.temperature = -10
    assert tool.read_temperature() == -10


def test_lock_and_unlock(tool: QuickLink, fake: FakeSerial) -> None:
    tool.lock()
    assert fake.lock is True and fake.power is True
    assert tool.read_lock_state() is LockState.LOCKED
    assert tool.read_power_state() is PowerState.ON

    tool.unlock()
    assert fake.lock is False and fake.power is False
    assert tool.read_lock_state() is LockState.UNLOCKED
    assert tool.read_power_state() is PowerState.OFF


def test_power_commands(tool: QuickLink, fake: FakeSerial) -> None:
    tool.power_on()
    assert fake.power is True
    tool.power_off()
    assert fake.power is False


def test_inconsistent_interlock_raises(tool: QuickLink, fake: FakeSerial) -> None:
    fake.break_interlock = True
    with pytest.raises(QuickLinkStateError):
        tool.lock()


def test_write_retries_once(tool: QuickLink, fake: FakeSerial) -> None:
    fake.drop_responses = 1
    tool.lock()
    fc05_writes = [frame for frame in fake.writes if frame[1] == 0x05]
    assert len(fc05_writes) == 2


def test_write_timeout_after_retries(tool: QuickLink, fake: FakeSerial) -> None:
    fake.drop_responses = 10
    tool.retries = 1
    with pytest.raises(QuickLinkTimeoutError):
        tool.lock()
    fc05_writes = [frame for frame in fake.writes if frame[1] == 0x05]
    assert len(fc05_writes) == 2


def test_corrupt_response_retried(tool: QuickLink, fake: FakeSerial) -> None:
    fake.corrupt_responses = 1
    tool.lock()
    assert fake.lock is True


def test_close_never_writes(tool: QuickLink, fake: FakeSerial) -> None:
    tool.open()
    before = list(fake.writes)
    tool.close()
    assert fake.writes == before
    assert fake.is_open is False


def test_duplicate_open_raises(fake: FakeSerial) -> None:
    def factory(port: str, baudrate: int, timeout: float = 0.5) -> FakeSerial:
        return fake

    first = QuickLink(port=fake.port, serial_factory=factory, tx_guard=0)
    second = QuickLink(port=fake.port, serial_factory=factory, tx_guard=0)
    first.open()
    try:
        with pytest.raises(QuickLinkConnectionError, match="already open"):
            second.open()
    finally:
        first.close()


def test_threads_are_serialized(tool: QuickLink) -> None:
    tool.open()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: tool.read_temperature(), range(32)))
    assert results == [25] * 32
