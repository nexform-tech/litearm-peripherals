# 快速开始

大约五分钟从每个设备各读一次数据。安装和运行测试都不需要硬件。

## 1. 安装

```bash
git clone <repository-url>
cd litearm-peripherals
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

`[dev]` 会额外安装 pytest、ruff 和 build；只要运行时依赖可去掉。

## 2. USB-RS485 连接快换装置

把适配器接到快换装置并插上 USB。

```bash
ls -l /dev/ttyUSB* /dev/HFRobotQuickLink
```

读取一次状态：

```bash
python examples/01_quicklink_status.py --port /dev/ttyUSB0
```

输出类似：

```
lock=UNLOCKED power=OFF temperature=31 C firmware=1.11
```

省略 `--port` 会启用自动探测。失败时显式指定端口：

```bash
export LITEARM_QUICKLINK_PORT=/dev/ttyUSB0
```

锁定与解锁（会移动工具）：

```bash
python examples/02_quicklink_lock_cycle.py --port /dev/ttyUSB0 --yes
```

脚本会在 `finally` 块中解锁。锁定隐含上电，解锁隐含下电。

## 3. CAN 连接六维力传感器

在打开接口**之前**把总线拉到 1 Mbit/s。传感器在收到启动帧之前不会上传。

原生 CAN 适配器：

```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
```

slcan 适配器（CANable2、部分 CH340 板卡）：

```bash
sudo slcand -o -c -f -s8 /dev/ttyACM0 can0
sudo ip link set can0 up
```

读取一个样本：

```bash
python examples/03_wrist_ft_read.py --iface can0
```

连续读取：

```bash
python examples/04_wrist_ft_stream.py --iface can0
```

如果读不到数据，扫描传感器连续三个 ID：

```bash
python examples/05_wrist_ft_probe.py --iface can0 --duration 3
```

## 4. 两个设备一起

```bash
python examples/06_peripheral_hub.py --port /dev/ttyUSB0 --iface can0
```

## 5. 离线验证

无需硬件解码录制的帧：

```bash
python examples/07_offline_decode.py
```

运行完整的离线测试：

```bash
./test.sh
```

## 常见错误

| 错误 | 处理 |
|---|---|
| `QuickLinkConnectionError: No serial port found` | 设置 `--port` 或 `LITEARM_QUICKLINK_PORT` |
| Modbus 超时 | 确认从站 1 / 115200、A/B 接线，且没有其他进程占用串口 |
| `WristFTConnectionError` | 接口不存在或未 up；执行上面的 `ip link` 命令 |
| `WristFTTimeoutError` | 传感器上电？总线 1 Mbit/s？接收 ID（默认 `0x10`）正确？ |
| 数值不合理 | 运行 `probe()` 再 `reset_id()` |
