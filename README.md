litearm-peripherals is a Python SDK that drives the Handsfree Quick Link tool changer and the WRJST six-axis force/torque sensor from one package.

# litearm-peripherals

[English](README.md) | [简体中文](README.zh-CN.md)

Python SDK for two robot peripherals:

| Device | Transport | Class |
|---|---|---|
| Handsfree Quick Link tool changer | Modbus RTU over USB-RS485 | `QuickLink` |
| WRJST six-axis force/torque sensor | Raw Linux SocketCAN, 1 Mbit/s | `WristFT` |

An optional `PeripheralHub` facade groups both device lifecycles.

- Typed exception hierarchy and context-manager support
- Works offline: protocol logic is tested with fake serial/CAN transports
- No runtime dependency beyond `pyserial`; the CAN side uses the standard library
- Python 3.9+

New here? Start with [QUICKSTART.md](QUICKSTART.md). The [documentation index](docs/index.md) covers setup and architecture.

## Install

```bash
git clone <repository-url>
cd litearm-peripherals
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"        # omit [dev] for runtime only
```

## Hardware setup

### Quick Link (USB-RS485)

The tool changer uses Modbus RTU: **115200 baud, slave 1** by default.
Connect the adapter and confirm the device node:

```bash
ls -l /dev/ttyUSB* /dev/HFRobotQuickLink
```

The official udev rule creates `/dev/HFRobotQuickLink`. A generic CH340
USB-RS485 adapter appears as `/dev/ttyUSB0`; both work.

Port detection order used when `port` is omitted:

1. `$LITEARM_QUICKLINK_PORT`
2. `/dev/HFRobotQuickLink`
3. `/dev/serial/by-id/*HandsFree*` or `*QuickLink*`
4. pyserial port metadata containing HandsFree/QuickLink
5. a single `/dev/ttyUSB*` / `/dev/ttyACM*` fallback (a warning is logged)

If several candidates remain, set `LITEARM_QUICKLINK_PORT` explicitly.

### F/T sensor (CAN)

The sensor uses standard 11-bit frames at **1 Mbit/s** and does **not** upload
until it receives a start frame. Bring the interface up first:

```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
```

For slcan adapters (CANable2, some CH340 boards):

```bash
sudo slcand -o -c -f -s8 /dev/ttyACM0 can0
sudo ip link set can0 up
```

## Quick start

### Quick Link

```python
from litearm_peripherals import QuickLink

with QuickLink(port="/dev/ttyUSB0") as tool:
    status = tool.read_status(include_firmware=True)
    print(status.lock, status.power, status.temperature_c, status.firmware)

    tool.lock()      # locks the tool and powers it on
    tool.unlock()    # unlocks the tool and powers it off
```

### Six-axis force/torque sensor

```python
from litearm_peripherals import WristFT

with WristFT(iface="can0") as ft:
    ft.start(10)                       # 100 Hz upload
    sample = ft.read(timeout=1.0)
    print(sample.fx, sample.fy, sample.fz,
          sample.mx, sample.my, sample.mz)
```

For continuous acquisition:

```python
import contextlib

with WristFT(iface="can0") as ft:
    with contextlib.closing(ft.stream(10)) as samples:
        for sample in samples:
            print(sample.force_magnitude)
```

### Both devices

```python
from litearm_peripherals import PeripheralHub

with PeripheralHub.open(quicklink_port="/dev/ttyUSB0", iface="can0") as hub:
    status = hub.read_status()
    print(status.quicklink)
    print(status.wrist_ft)
```

## API reference

### `QuickLink`

| Member | Description |
|---|---|
| `QuickLink(port=None, baudrate=115200, slave_addr=1, timeout=0.5, retries=2, tx_guard=0.002, retry_backoff=0.05)` | Configure the driver; `port=None` enables auto-detection |
| `open()` / `close()` / `with` | Open or close the serial port; `close()` never writes a coil |
| `read_status(include_firmware=False)` | `QuickLinkStatus(lock, power, temperature_c, firmware)` |
| `read_lock_state()` / `read_power_state()` | `LockState` / `PowerState` |
| `read_temperature()` | Signed temperature in °C |
| `read_firmware()` | `"major.minor"` |
| `lock()` / `unlock()` | Write the lock coil and verify the lock/power interlock |
| `power_on()` / `power_off()` | Write the power coil for diagnostics |

`LockState` is `UNLOCKED`/`LOCKED`; `PowerState` is `OFF`/`ON`.

### `WristFT`

| Member | Description |
|---|---|
| `WristFT(iface="can0", base=0x15, recv=0x10, endian="auto", timeout=0.5, transport=None, auto_start=True, interval_ms=10)` | Configure the driver; `transport` allows injection in tests |
| `open()` / `close()` / `with` | Open or close the CAN interface |
| `start(interval_ms=10)` / `stop()` | Start or stop the sensor upload |
| `read(timeout=None)` | One `Sample`, raises `WristFTTimeoutError` on timeout |
| `stream(interval_ms=10)` | Iterator of samples; stops the upload if it started it |
| `probe(duration=3.0, start_ms=None)` | List of `Candidate` three-id groups |
| `set_id(new_recv, new_send)` / `reset_id()` | Change or restore flash-stored ids |
| `read_raw(timeout=None)` | `(can_id, dlc, data)` or `None` |
| `endian` | Resolved byte order (`"little"` or `"big"`) |

`Sample` exposes `fx/fy/fz` (N), `mx/my/mz` (Nm), `as_tuple()`,
`force_magnitude` and `torque_magnitude`.

### `PeripheralHub`

| Member | Description |
|---|---|
| `PeripheralHub.open(quicklink_port=None, iface="can0", with_quicklink=True, with_wrist_ft=True, quicklink_kwargs=None, wrist_ft_kwargs=None)` | Open the requested devices |
| `quicklink` / `wrist_ft` | The underlying device, or `None` |
| `read_status()` | `HubStatus(quicklink, wrist_ft)` |
| `close()` | Close both devices; never unlocks the tool |

## Exceptions

All errors derive from `PeripheralsError`.

| Branch | Classes |
|---|---|
| Quick Link | `QuickLinkError`, `QuickLinkConnectionError`, `QuickLinkTimeoutError`, `QuickLinkProtocolError`, `QuickLinkStateError` |
| F/T sensor | `WristFTError`, `WristFTConnectionError`, `WristFTTimeoutError`, `WristFTProtocolError`, `WristFTIdChangeError` |

```python
from litearm_peripherals import PeripheralsError

try:
    tool.lock()
except PeripheralsError as error:
    print(error)
```

## Safety notes

- **`QuickLink.close()` never unlocks.** Closing a process does not move the
  physical tool.
- Locking implies power-on and unlocking implies power-off. `lock()` and
  `unlock()` verify the interlock and raise `QuickLinkStateError` instead of
  silently correcting an inconsistent state.
- A tool-change sequence (unlock → move → lock) belongs to the application;
  this SDK never automates it.
- The F/T sensor only uploads after a start frame. IDs written by `set_id()`
  are stored in flash and survive power cycles; use `reset_id()` to restore
  `0x10`/`0x15`.
- Float payloads are little-endian even though the vendor manual says
  big-endian. The driver detects the byte order from plausibility.
- `set_id()` / `reset_id()` raise `WristFTIdChangeError` if the new upload
  cannot be verified; local ids are left unchanged. Run `probe()` to
  rediscover the sensor.

## Development

```bash
./test.sh              # ruff + offline pytest
python -m build        # wheel + sdist
```

Hardware tests are opt-in:

```bash
LITEARM_LIVE=1 pytest tests/test_live.py
LITEARM_LIVE=1 LITEARM_LIVE_WRITES=1 pytest tests/test_live.py   # moving/writing tests
```

Use `LITEARM_LIVE_QUICKLINK_PORT` and `LITEARM_LIVE_CAN_IFACE` to point at
non-default ports/interfaces.

## Troubleshooting

| Symptom | Check |
|---|---|
| `QuickLinkConnectionError: No serial port found` | Adapter plugged in? Set `port=` or `LITEARM_QUICKLINK_PORT` |
| Modbus timeouts | Slave address and baud rate (default 1 / 115200), A/B wiring, another process holding the port |
| `QuickLinkStateError` after lock | Power interlock is inconsistent; inspect the tool before retrying |
| `WristFTConnectionError` | Interface missing or down; see the setup commands printed in the error |
| `WristFTTimeoutError` | Sensor powered? Start frame sent? Bus at 1 Mbit/s? Correct receive id? |
| Implausible F/T values | Wrong base id or byte order; run `probe()` and `reset_id()` |

## License

Apache-2.0. See [LICENSE](LICENSE).
