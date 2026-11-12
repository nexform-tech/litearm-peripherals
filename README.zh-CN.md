litearm-peripherals 是一个 Python SDK，用一个包同时驱动 Handsfree Quick Link 快换装置和蓝点触控 WRJST 六维力/力矩传感器。

# litearm-peripherals

[English](README.md) | [简体中文](README.zh-CN.md)

两个机器人外设的 Python SDK：

| 设备 | 传输 | 类 |
|---|---|---|
| Handsfree Quick Link 快换装置 | Modbus RTU over USB-RS485 | `QuickLink` |
| 蓝点触控 WRJST 六维力/力矩传感器 | 原生 Linux SocketCAN，1 Mbit/s | `WristFT` |

可选的 `PeripheralHub` 门面统一管理两个设备的生命周期。

- 类型化异常层次与上下文管理器支持
- 可离线运行：协议逻辑用假的串口/CAN 传输层测试
- 除 `pyserial` 外无运行时依赖；CAN 侧只用标准库
- Python 3.9+

初次使用请看 [QUICKSTART.zh-CN.md](QUICKSTART.zh-CN.md)。安装与架构说明见[文档索引](docs/index.md)。

## 安装

```bash
git clone <repository-url>
cd litearm-peripherals
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"        # 只要运行时依赖可去掉 [dev]
```

## 硬件准备

### Quick Link（USB-RS485）

快换装置使用 Modbus RTU：默认 **115200 波特率、从站 1**。
接上适配器后确认设备节点：

```bash
ls -l /dev/ttyUSB* /dev/HFRobotQuickLink
```

官方 udev 规则会创建 `/dev/HFRobotQuickLink`。普通的 CH340
USB-RS485 适配器显示为 `/dev/ttyUSB0`，两者都可使用。

省略 `port` 时的端口探测顺序：

1. `$LITEARM_QUICKLINK_PORT`
2. `/dev/HFRobotQuickLink`
3. `/dev/serial/by-id/*HandsFree*` 或 `*QuickLink*`
4. pyserial 端口元数据中包含 HandsFree/QuickLink
5. 唯一的 `/dev/ttyUSB*` / `/dev/ttyACM*` 作为回退（会记录一条警告）

如果仍有多个候选，请显式设置 `LITEARM_QUICKLINK_PORT`。

### 六维力传感器（CAN）

传感器使用标准 11 位帧，速率 **1 Mbit/s**，并且在收到启动帧之前
**不会主动上传**。先把接口拉起来：

```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
```

对于 slcan 适配器（CANable2、部分 CH340 板卡）：

```bash
sudo slcand -o -c -f -s8 /dev/ttyACM0 can0
sudo ip link set can0 up
```

## 快速开始

### 快换装置

```python
from litearm_peripherals import QuickLink

with QuickLink(port="/dev/ttyUSB0") as tool:
    status = tool.read_status(include_firmware=True)
    print(status.lock, status.power, status.temperature_c, status.firmware)

    tool.lock()      # 锁定工具并上电
    tool.unlock()    # 解锁工具并下电
```

### 六维力传感器

```python
from litearm_peripherals import WristFT

with WristFT(iface="can0") as ft:
    ft.start(10)                       # 100 Hz 上传
    sample = ft.read(timeout=1.0)
    print(sample.fx, sample.fy, sample.fz,
          sample.mx, sample.my, sample.mz)
```

连续采集：

```python
import contextlib

with WristFT(iface="can0") as ft:
    with contextlib.closing(ft.stream(10)) as samples:
        for sample in samples:
            print(sample.force_magnitude)
```

### 两个设备

```python
from litearm_peripherals import PeripheralHub

with PeripheralHub.open(quicklink_port="/dev/ttyUSB0", iface="can0") as hub:
    status = hub.read_status()
    print(status.quicklink)
    print(status.wrist_ft)
```

## API 参考

### `QuickLink`

| 成员 | 说明 |
|---|---|
| `QuickLink(port=None, baudrate=115200, slave_addr=1, timeout=0.5, retries=2, tx_guard=0.002, retry_backoff=0.05)` | 配置驱动；`port=None` 启用自动探测 |
| `open()` / `close()` / `with` | 打开或关闭串口；`close()` 永不写线圈 |
| `read_status(include_firmware=False)` | `QuickLinkStatus(lock, power, temperature_c, firmware)` |
| `read_lock_state()` / `read_power_state()` | `LockState` / `PowerState` |
| `read_temperature()` | 有符号温度（°C） |
| `read_firmware()` | `"major.minor"` |
| `lock()` / `unlock()` | 写锁定线圈并校验锁定/电源联动 |
| `power_on()` / `power_off()` | 写电源线圈，用于诊断 |

`LockState` 为 `UNLOCKED`/`LOCKED`；`PowerState` 为 `OFF`/`ON`。

### `WristFT`

| 成员 | 说明 |
|---|---|
| `WristFT(iface="can0", base=0x15, recv=0x10, endian="auto", timeout=0.5, transport=None, auto_start=True, interval_ms=10)` | 配置驱动；`transport` 用于测试注入 |
| `open()` / `close()` / `with` | 打开或关闭 CAN 接口 |
| `start(interval_ms=10)` / `stop()` | 开始或停止传感器上传 |
| `read(timeout=None)` | 读取一个 `Sample`，超时抛 `WristFTTimeoutError` |
| `stream(interval_ms=10)` | 样本迭代器；若由它启动上传则在退出时停止 |
| `probe(duration=3.0, start_ms=None)` | 返回 `Candidate` 三 ID 组列表 |
| `set_id(new_recv, new_send)` / `reset_id()` | 修改或恢复 flash 存储的 ID |
| `read_raw(timeout=None)` | `(can_id, dlc, data)` 或 `None` |
| `endian` | 解析出的字节序（`"little"` 或 `"big"`） |

`Sample` 暴露 `fx/fy/fz`（N）、`mx/my/mz`（Nm）、`as_tuple()`、
`force_magnitude` 和 `torque_magnitude`。

### `PeripheralHub`

| 成员 | 说明 |
|---|---|
| `PeripheralHub.open(quicklink_port=None, iface="can0", with_quicklink=True, with_wrist_ft=True, quicklink_kwargs=None, wrist_ft_kwargs=None)` | 打开指定设备 |
| `quicklink` / `wrist_ft` | 底层设备，或 `None` |
| `read_status()` | `HubStatus(quicklink, wrist_ft)` |
| `close()` | 关闭两个设备；永不解锁工具 |

## 异常

所有错误都继承自 `PeripheralsError`。

| 分支 | 类 |
|---|---|
| 快换装置 | `QuickLinkError`、`QuickLinkConnectionError`、`QuickLinkTimeoutError`、`QuickLinkProtocolError`、`QuickLinkStateError` |
| 六维力传感器 | `WristFTError`、`WristFTConnectionError`、`WristFTTimeoutError`、`WristFTProtocolError`、`WristFTIdChangeError` |

```python
from litearm_peripherals import PeripheralsError

try:
    tool.lock()
except PeripheralsError as error:
    print(error)
```

## 安全注意事项

- **`QuickLink.close()` 永不执行解锁。** 关闭进程不会移动物理工具。
- 锁定隐含上电，解锁隐含下电。`lock()` 与 `unlock()` 会校验联动关系，
  状态不一致时抛出 `QuickLinkStateError`，而不是静默纠正。
- 换刀流程（解锁 → 移动 → 锁定）由应用层负责，本 SDK 从不自动执行。
- 六维力传感器只在收到启动帧后上传。`set_id()` 写入的 ID 保存在 flash
  中并跨上电保留；用 `reset_id()` 恢复 `0x10`/`0x15`。
- 浮点载荷实际为小端，尽管厂商手册写的是大端。驱动会根据合理性判断字节序。
- 若无法验证新的上传，`set_id()` / `reset_id()` 会抛出
  `WristFTIdChangeError`，本地 ID 保持不变。请运行 `probe()` 重新发现传感器。

## 开发

```bash
./test.sh              # ruff + 离线 pytest
python -m build        # wheel + sdist
```

硬件测试需显式开启：

```bash
LITEARM_LIVE=1 pytest tests/test_live.py
LITEARM_LIVE=1 LITEARM_LIVE_WRITES=1 pytest tests/test_live.py   # 含运动/写入的测试
```

用 `LITEARM_LIVE_QUICKLINK_PORT` 和 `LITEARM_LIVE_CAN_IFACE` 指向非默认的
端口/接口。

## 排障

| 现象 | 检查 |
|---|---|
| `QuickLinkConnectionError: No serial port found` | 适配器插好了吗？设置 `port=` 或 `LITEARM_QUICKLINK_PORT` |
| Modbus 超时 | 从站地址与波特率（默认 1 / 115200）、A/B 接线、是否有其他进程占用串口 |
| `lock` 后出现 `QuickLinkStateError` | 电源联动状态不一致；检查工具后再重试 |
| `WristFTConnectionError` | 接口不存在或未 up；参见错误中打印的配置命令 |
| `WristFTTimeoutError` | 传感器上电？发过启动帧？总线是 1 Mbit/s？接收 ID 正确？ |
| 力/力矩值不合理 | base ID 或字节序错误；运行 `probe()` 和 `reset_id()` |

## 许可证

Apache-2.0。见 [LICENSE](LICENSE)。
