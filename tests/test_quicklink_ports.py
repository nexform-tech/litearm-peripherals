import os
from types import SimpleNamespace

import pytest

import litearm_peripherals.quicklink as quicklink
from litearm_peripherals.errors import QuickLinkConnectionError
from litearm_peripherals.quicklink import QuickLink, find_quicklink_port


def _info(device: str, description: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        device=device,
        description=description,
        interface="",
        product="",
        manufacturer="",
        hwid="",
    )


def test_env_var_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(quicklink.ENV_PORT, "/dev/ttyFAKE")
    real_exists = os.path.exists
    monkeypatch.setattr(
        quicklink.os.path, "exists", lambda path: path == "/dev/ttyFAKE" or real_exists(path)
    )
    assert find_quicklink_port() == "/dev/ttyFAKE"


def test_missing_env_path_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(quicklink.ENV_PORT, "/dev/ttyMISSING")
    monkeypatch.setattr(quicklink.os.path, "exists", lambda path: False)
    with pytest.raises(QuickLinkConnectionError, match="does not exist"):
        find_quicklink_port()


def test_udev_symlink(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(quicklink.ENV_PORT, raising=False)
    monkeypatch.setattr(
        quicklink.os.path, "exists", lambda path: path == quicklink.UDEV_SYMLINK
    )
    assert find_quicklink_port() == quicklink.UDEV_SYMLINK


def test_by_id_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(quicklink.ENV_PORT, raising=False)
    monkeypatch.setattr(quicklink.os.path, "exists", lambda path: False)
    monkeypatch.setattr(
        quicklink.os.path, "isdir", lambda path: path == quicklink.BY_ID_DIR
    )
    monkeypatch.setattr(
        quicklink.os, "listdir", lambda path: ["usb-HandsFree_QuickLink_123"]
    )
    expected = os.path.join(quicklink.BY_ID_DIR, "usb-HandsFree_QuickLink_123")
    assert find_quicklink_port() == expected


def test_multiple_by_id_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(quicklink.ENV_PORT, raising=False)
    monkeypatch.setattr(quicklink.os.path, "exists", lambda path: False)
    monkeypatch.setattr(
        quicklink.os.path, "isdir", lambda path: path == quicklink.BY_ID_DIR
    )
    monkeypatch.setattr(
        quicklink.os,
        "listdir",
        lambda path: ["usb-HandsFree_QuickLink_1", "usb-QuickLink_2"],
    )
    with pytest.raises(QuickLinkConnectionError, match="Multiple"):
        find_quicklink_port()


def test_pyserial_metadata_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(quicklink.ENV_PORT, raising=False)
    monkeypatch.setattr(quicklink.os.path, "exists", lambda path: False)
    monkeypatch.setattr(quicklink.os.path, "isdir", lambda path: False)
    monkeypatch.setattr(
        quicklink,
        "list_serial_ports",
        lambda: [_info("/dev/ttyUSB3", "HandsFree QuickLink Bridge")],
    )
    assert find_quicklink_port() == "/dev/ttyUSB3"


def test_single_fallback_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(quicklink.ENV_PORT, raising=False)
    monkeypatch.setattr(quicklink.os.path, "exists", lambda path: False)
    monkeypatch.setattr(quicklink.os.path, "isdir", lambda path: False)
    monkeypatch.setattr(
        quicklink, "list_serial_ports", lambda: [_info("/dev/ttyUSB0", "USB Serial")]
    )
    assert find_quicklink_port() == "/dev/ttyUSB0"


def test_multiple_fallback_ports_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(quicklink.ENV_PORT, raising=False)
    monkeypatch.setattr(quicklink.os.path, "exists", lambda path: False)
    monkeypatch.setattr(quicklink.os.path, "isdir", lambda path: False)
    monkeypatch.setattr(
        quicklink,
        "list_serial_ports",
        lambda: [_info("/dev/ttyUSB0", "USB Serial"), _info("/dev/ttyUSB1", "USB Serial")],
    )
    with pytest.raises(QuickLinkConnectionError, match="Multiple"):
        find_quicklink_port()


def test_no_port_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(quicklink.ENV_PORT, raising=False)
    monkeypatch.setattr(quicklink.os.path, "exists", lambda path: False)
    monkeypatch.setattr(quicklink.os.path, "isdir", lambda path: False)
    monkeypatch.setattr(quicklink, "list_serial_ports", lambda: [])
    monkeypatch.setattr(quicklink.glob, "glob", lambda pattern: [])
    with pytest.raises(QuickLinkConnectionError, match="No serial port"):
        find_quicklink_port()


def test_windows_port_normalized() -> None:
    tool = QuickLink(port="com5", serial_factory=lambda *args, **kwargs: None)
    assert tool.port == "COM5"
