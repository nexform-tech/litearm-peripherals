This guide installs and verifies the LiteArm peripherals SDK for robotics
application developers.

# Setup

## Prerequisites

- Linux with Python 3.9 or newer (the CAN side uses raw `SocketCAN`).
- A USB-RS485 adapter for the Quick Link tool changer.
- A CAN adapter for the F/T sensor; the interface must support 1 Mbit/s.
- `pyserial` is installed as a dependency; no other runtime packages are
  needed.

## 1. Install dependencies

```bash
git clone https://github.com/nexform-tech/litearm-peripherals.git
cd litearm-peripherals
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

Drop `[dev]` when you only need the runtime library.

## 2. Wire the hardware

Quick Link over USB-RS485: Modbus RTU, slave 1, 115200 baud. Check the device
node:

```bash
ls -l /dev/ttyUSB* /dev/HFRobotQuickLink
```

F/T sensor over CAN: bring the interface up at 1 Mbit/s before opening it.

```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
```

For slcan adapters:

```bash
sudo slcand -o -c -f -s8 /dev/ttyACM0 can0
sudo ip link set can0 up
```

## 3. Verify

Offline checks need no hardware:

```bash
./test.sh
python examples/07_offline_decode.py
```

Expected result: `ruff` reports no issues, pytest reports all tests passing
with the live tests skipped, and the decoder prints six force/torque values
with `endian = little`.

With hardware attached, read one device at a time:

```bash
python examples/01_quicklink_status.py --port /dev/ttyUSB0
python examples/03_wrist_ft_read.py --iface can0
```

## Troubleshooting

**`QuickLinkConnectionError: No serial port found`**

The adapter is missing or auto-detection is ambiguous. Pass `--port`, or set
`LITEARM_QUICKLINK_PORT`.

**Modbus timeouts**

Confirm slave 1 / 115200, check the A/B wiring, and make sure no other process
holds the serial port.

**`WristFTConnectionError`**

The interface is missing or down. Run the `ip link` commands above and confirm
the sensor is powered.

**`WristFTTimeoutError`**

The sensor only uploads after a start frame. Check the bus speed (1 Mbit/s),
the interface, and the receive id (`0x10` by default).
