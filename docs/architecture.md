This document describes the architecture of the LiteArm peripherals SDK for
robotics application developers.

# Architecture

## Context

The SDK talks to two independent peripherals:

- a Handsfree Quick Link tool changer over Modbus RTU on a USB-RS485 adapter;
- a WRJST six-axis force/torque sensor over raw Linux SocketCAN.

It exposes synchronous, blocking drivers. It does not schedule motion, decide
when a tool change is safe, or automate unlock → move → lock sequences. Those
decisions belong to the application.

## Components

| Component | Responsibility | Depends on |
|---|---|---|
| `quicklink.QuickLink` | Modbus transactions, port detection, lock/power interlock checks | `_modbus`, `_serial` |
| `wrist_ft.WristFT` | Start/stop upload, sample decode, id management, probing | `_can`, `wrist_ft` protocol helpers |
| `facade.PeripheralHub` | Group both device lifecycles | `QuickLink`, `WristFT` |
| `errors` | Typed exception hierarchy with structured context | — |
| `_modbus` | CRC16, frame packing/parsing, function-code helpers | — |
| `_serial` | Serial transport protocol, lazy `pyserial` import, port registry | `pyserial` |
| `_can` | CAN frame type, transport protocol, `SocketCanTransport` | Python standard library |

## Data flow

A read follows the same shape on both devices:

1. The caller opens the device (or enters its context manager).
2. The driver builds a request: a Modbus frame for `QuickLink`, a start or
   data frame for `WristFT`.
3. The transport sends it and waits until a deadline.
4. The driver validates the response and either returns a typed value
   (`QuickLinkStatus`, `Sample`) or raises a typed exception.

Automated tests replace the transport with `tests/fake_serial.py` and
`tests/fake_can.py`, so protocol behavior is exercised without hardware.

## Boundaries

- This repository owns the device protocols, the public Python API, examples,
  and offline tests.
- Robot motion, tool-change sequencing, and safety interlocks beyond the
  device's own lock/power interlock belong to the consuming application.
- Vendor ROS drivers and bespoke lab scripts stay outside this repository.

## Decisions

- **Blocking API.** Robot code usually calls these drivers from a worker
  thread; a synchronous API keeps the protocol logic simple and testable.
- **Injectable transports.** `serial_factory=` and `transport=` let CI run the
  full protocol without hardware.
- **No implicit unlock.** `close()` never writes a coil, so ending a process
  cannot move the physical tool.
- **Endianness by plausibility.** The sensor manual says big-endian, but real
  payloads are little-endian; the driver detects the byte order from plausible
  force/torque ranges and caches the result.
- **Vendored sensor protocol.** The WRJST protocol lives in this package rather
  than depending on the original lab repository, so the SDK is standalone.
