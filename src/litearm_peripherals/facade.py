"""Convenience facade combining the Quick Link tool changer and the F/T sensor.

The two devices are independent; :class:`PeripheralHub` only groups their
lifecycles so an application can open and close them together.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .quicklink import QuickLink, QuickLinkStatus
from .wrist_ft import Sample, WristFT


@dataclass(frozen=True)
class HubStatus:
    """Latest status of each device; ``None`` when that device is absent."""

    quicklink: Optional[QuickLinkStatus]
    wrist_ft: Optional[Sample]


class PeripheralHub:
    """Group a :class:`QuickLink` and a :class:`WristFT` under one handle."""

    def __init__(
        self,
        quicklink: Optional[QuickLink] = None,
        wrist_ft: Optional[WristFT] = None,
    ) -> None:
        self._quicklink = quicklink
        self._wrist_ft = wrist_ft

    @classmethod
    def open(
        cls,
        quicklink_port: Optional[str] = None,
        iface: str = "can0",
        with_quicklink: bool = True,
        with_wrist_ft: bool = True,
        quicklink_kwargs: Optional[Dict[str, Any]] = None,
        wrist_ft_kwargs: Optional[Dict[str, Any]] = None,
    ) -> "PeripheralHub":
        """Open the requested devices; on failure close whatever was opened."""
        quicklink = None
        wrist_ft = None
        try:
            if with_quicklink:
                quicklink = QuickLink(port=quicklink_port, **(quicklink_kwargs or {})).open()
            if with_wrist_ft:
                wrist_ft = WristFT(iface=iface, **(wrist_ft_kwargs or {})).open()
        except Exception:
            if wrist_ft is not None:
                wrist_ft.close()
            if quicklink is not None:
                quicklink.close()
            raise
        return cls(quicklink, wrist_ft)

    @property
    def quicklink(self) -> Optional[QuickLink]:
        return self._quicklink

    @property
    def wrist_ft(self) -> Optional[WristFT]:
        return self._wrist_ft

    def read_status(self) -> HubStatus:
        """Read one status snapshot from each connected device."""
        quicklink_status = self._quicklink.read_status() if self._quicklink else None
        wrist_ft_sample = (
            self._wrist_ft.read(self._wrist_ft.timeout) if self._wrist_ft else None
        )
        return HubStatus(quicklink_status, wrist_ft_sample)

    def close(self) -> None:
        """Close both devices.  Idempotent and never unlocks the tool."""
        first_error: Optional[Exception] = None
        for device in (self._wrist_ft, self._quicklink):
            if device is None:
                continue
            try:
                device.close()
            except Exception as exc:  # pragma: no cover - best effort cleanup
                if first_error is None:
                    first_error = exc
        self._wrist_ft = None
        self._quicklink = None
        if first_error is not None:
            raise first_error

    def __enter__(self) -> "PeripheralHub":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
