# Examples

Run these after `pip install -e .` from the repository root.

| Script | Hardware | Writes | Purpose |
|---|---|---|---|
| `01_quicklink_status.py` | Quick Link | no | Read lock, power, temperature and firmware |
| `02_quicklink_lock_cycle.py` | Quick Link | yes | Lock, wait, unlock (requires `--yes`) |
| `03_wrist_ft_read.py` | F/T sensor + CAN | no | Start upload and print one sample |
| `04_wrist_ft_stream.py` | F/T sensor + CAN | no | Print a stream of samples |
| `05_wrist_ft_probe.py` | F/T sensor + CAN | maybe (`--start`) | Scan for the three consecutive ids |
| `06_peripheral_hub.py` | both | no | Read both devices through `PeripheralHub` |
| `07_offline_decode.py` | none | no | Decode recorded frames offline |

Common options:

```bash
python examples/01_quicklink_status.py --port /dev/ttyUSB0
python examples/03_wrist_ft_read.py --iface can0
python examples/05_wrist_ft_probe.py --iface can0 --duration 3
```

`02_quicklink_lock_cycle.py` moves the tool. It refuses to run without
`--yes` and unlocks in its `finally` block.

Before the CAN examples, bring the interface up at 1 Mbit/s:

```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
```
