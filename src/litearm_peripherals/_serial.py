"""Serial-port helpers with lazy pyserial import and in-process ownership.

Importing this module must never require pyserial; the dependency is imported
only inside :func:`open_serial`.  The registry prevents two :class:`QuickLink`
objects in the same process from interleaving bytes on one device.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Callable, Dict, List, Optional, Protocol

from .errors import QuickLinkConnectionError


class SerialLike(Protocol):
    """Subset of :class:`serial.Serial` used by the driver."""

    @property
    def is_open(self) -> bool: ...

    @property
    def in_waiting(self) -> int: ...

    def read(self, size: int = 1) -> bytes: ...

    def write(self, data: bytes) -> int: ...

    def flush(self) -> None: ...

    def reset_input_buffer(self) -> None: ...

    def close(self) -> None: ...


SerialFactory = Callable[..., SerialLike]

_REGISTRY: Dict[str, SerialLike] = {}
_REGISTRY_LOCK = threading.Lock()


def normalize_port(port: str) -> str:
    """Uppercase Windows ``comN`` names; leave POSIX paths unchanged."""
    if port and len(port) >= 4 and port[:3].upper() == "COM" and port[3:].isdigit():
        return "COM" + port[3:]
    return port


def _registry_key(port: str) -> str:
    try:
        return os.path.realpath(port)
    except OSError:
        return port


def list_serial_ports() -> List[Any]:
    """Return pyserial ``ListPortInfo`` objects, or an empty list if unavailable."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    try:
        return list(list_ports.comports())
    except Exception:  # pragma: no cover - defensive against odd drivers
        return []


def open_serial(
    port: str,
    baudrate: int,
    timeout: float = 0.5,
    serial_factory: Optional[SerialFactory] = None,
) -> SerialLike:
    """Open *port* exclusively within this process and return the handle."""
    port = normalize_port(port)
    key = _registry_key(port)
    with _REGISTRY_LOCK:
        if key in _REGISTRY:
            raise QuickLinkConnectionError(
                "Serial port is already open in this process", port=port
            )
        if serial_factory is None:
            try:
                import serial
            except ImportError as exc:  # pragma: no cover - dependency is declared
                raise QuickLinkConnectionError(
                    "pyserial is required to use QuickLink; install it with 'pip install pyserial'",
                    port=port,
                ) from exc
            factory: SerialFactory = serial.Serial
        else:
            factory = serial_factory
        try:
            handle = factory(port, baudrate, timeout=timeout)
        except Exception as exc:
            raise QuickLinkConnectionError(
                f"Cannot open serial port {port}: {exc}", port=port
            ) from exc
        _REGISTRY[key] = handle
    return handle


def close_serial(handle: SerialLike, port: str) -> None:
    """Close *handle* and drop it from the ownership registry."""
    key = _registry_key(normalize_port(port))
    with _REGISTRY_LOCK:
        if _REGISTRY.get(key) is handle:
            del _REGISTRY[key]
    try:
        handle.close()
    except Exception:  # pragma: no cover - closing must be best-effort
        pass
