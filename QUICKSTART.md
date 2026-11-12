# Quick start

Get one reading from each device in about five minutes. No hardware is needed
to install or run the tests.

## 1. Install

```bash
git clone <repository-url>
cd litearm-peripherals
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

`[dev]` adds pytest, ruff and build. Drop it for runtime only.

## 2. Quick Link over USB-RS485

Wire the adapter to the tool changer and plug it in.

```bash
ls -l /dev/ttyUSB* /dev/HFRobotQuickLink
```

Read the status once:

```bash
python examples/01_quicklink_status.py --port /dev/ttyUSB0
```

Expected output resembles:

```
lock=UNLOCKED power=OFF temperature=31 C firmware=1.11
```

Omit `--port` to use auto-detection. If it fails, set the port explicitly:

```bash
export LITEARM_QUICKLINK_PORT=/dev/ttyUSB0
```

Lock and unlock (this moves the tool):

```bash
python examples/02_quicklink_lock_cycle.py --port /dev/ttyUSB0 --yes
```

The script unlocks in its `finally` block. Locking implies power-on; unlocking
implies power-off.

## 3. Six-axis F/T sensor over CAN

Bring the bus up at 1 Mbit/s **before** opening the interface. The sensor does
not upload until it receives a start frame.

For a native CAN adapter:

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

Read one sample:

```bash
python examples/03_wrist_ft_read.py --iface can0
```

Stream samples:

```bash
python examples/04_wrist_ft_stream.py --iface can0
```

If you see no data, scan for the sensor's three consecutive ids:

```bash
python examples/05_wrist_ft_probe.py --iface can0 --duration 3
```

## 4. Both devices

```bash
python examples/06_peripheral_hub.py --port /dev/ttyUSB0 --iface can0
```

## 5. Offline check

Decode recorded frames without hardware:

```bash
python examples/07_offline_decode.py
```

Run the full offline suite:

```bash
./test.sh
```

## Common errors

| Error | Fix |
|---|---|
| `QuickLinkConnectionError: No serial port found` | Set `--port` or `LITEARM_QUICKLINK_PORT` |
| Modbus timeouts | Check slave 1 / 115200, A/B wiring, and that nothing else holds the port |
| `WristFTConnectionError` | The interface is missing or down; run the `ip link` commands above |
| `WristFTTimeoutError` | Sensor powered? Bus at 1 Mbit/s? Correct receive id (`0x10` by default)? |
| Implausible values | Run `probe()` then `reset_id()` |
