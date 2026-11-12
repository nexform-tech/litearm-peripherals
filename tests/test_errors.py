from litearm_peripherals.errors import (
    PeripheralsError,
    QuickLinkConnectionError,
    QuickLinkError,
    QuickLinkProtocolError,
    QuickLinkStateError,
    QuickLinkTimeoutError,
    WristFTConnectionError,
    WristFTError,
    WristFTIdChangeError,
    WristFTProtocolError,
    WristFTTimeoutError,
)


def test_hierarchy() -> None:
    quicklink_errors = [
        QuickLinkError,
        QuickLinkConnectionError,
        QuickLinkTimeoutError,
        QuickLinkProtocolError,
        QuickLinkStateError,
    ]
    wrist_errors = [
        WristFTError,
        WristFTConnectionError,
        WristFTTimeoutError,
        WristFTProtocolError,
        WristFTIdChangeError,
    ]
    for error in quicklink_errors + wrist_errors:
        assert issubclass(error, PeripheralsError)


def test_message_includes_context() -> None:
    error = QuickLinkTimeoutError("no answer", port="/dev/ttyUSB0", expected=8)
    assert "no answer" in str(error)
    assert "port='/dev/ttyUSB0'" in str(error)
    assert "expected=8" in str(error)


def test_plain_message_without_context() -> None:
    assert str(QuickLinkError("boom")) == "boom"
