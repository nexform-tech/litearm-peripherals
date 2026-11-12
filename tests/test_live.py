"""Hardware tests.  Skipped unless LITEARM_LIVE=1; writes need LITEARM_LIVE_WRITES=1."""

import os

import pytest

from litearm_peripherals import QuickLink, WristFT

pytestmark = pytest.mark.live


def _quicklink_port() -> str:
    return os.environ.get("LITEARM_LIVE_QUICKLINK_PORT", "/dev/ttyUSB0")


def test_quicklink_read_status() -> None:
    with QuickLink(port=_quicklink_port()) as tool:
        status = tool.read_status(include_firmware=True)
        assert -40 <= status.temperature_c <= 125
        assert status.firmware


@pytest.mark.live_write
def test_quicklink_lock_then_unlock() -> None:
    with QuickLink(port=_quicklink_port()) as tool:
        tool.lock()
        assert tool.read_lock_state().name == "LOCKED"
        tool.unlock()
        assert tool.read_lock_state().name == "UNLOCKED"


def test_wrist_ft_read() -> None:
    iface = os.environ.get("LITEARM_LIVE_CAN_IFACE", "can0")
    with WristFT(iface=iface) as ft:
        ft.start(10)
        sample = ft.read(timeout=2.0)
        assert sample.force_magnitude < 1e4
