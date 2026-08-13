#!/usr/bin/env python3
"""Safe UART protocol discovery for the Wisecoco knob display.

Only sends read-only/identity-style probes. It avoids dangerous words such as
erase, flash, write, reset, reboot and update.
"""

from __future__ import annotations

import argparse
import datetime as dt
import time
from pathlib import Path

import serial


DEFAULT_DEVICE = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
DEFAULT_LOG = "/home/paulo/botao-lab/logs/uart_protocol_probe.log"
DEFAULT_BAUDS = [115200, 9600, 57600, 38400, 19200, 230400, 460800, 921600]
SAFE_COMMANDS = [
    "AT",
    "AT?",
    "ATI",
    "AT+GMR",
    "AT+VER?",
    "AT+INFO?",
    "AT+HELP?",
    "HELP",
    "help",
    "?",
    "VERSION",
    "version",
    "VER?",
    "INFO",
    "info",
    "STATUS",
    "status",
    "PING",
    "ping",
]
LINE_ENDINGS = ["\r\n", "\n", "\r", ""]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--baud", type=int, action="append")
    parser.add_argument("--log", default=DEFAULT_LOG)
    parser.add_argument("--listen-first", type=float, default=2.0)
    parser.add_argument("--response-window", type=float, default=0.45)
    parser.add_argument("--settle", type=float, default=0.08)
    return parser.parse_args()


def printable(data: bytes) -> str:
    return "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in data)


def read_for(port: serial.Serial, seconds: float) -> bytes:
    deadline = time.monotonic() + seconds
    chunks = bytearray()
    while time.monotonic() < deadline:
        waiting = port.in_waiting
        if waiting:
            chunks.extend(port.read(waiting))
        else:
            time.sleep(0.02)
    return bytes(chunks)


def log_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as file:
        file.write(line + "\n")


def describe(data: bytes) -> str:
    if not data:
        return "0 bytes"
    return f"{len(data)} bytes hex={data.hex(' ')} text={printable(data)}"


def main() -> int:
    args = parse_args()
    bauds = args.baud or DEFAULT_BAUDS
    log_path = Path(args.log)
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    log_line(log_path, f"=== probe {stamp} device={args.device} bauds={bauds} ===")

    for baud in bauds:
        print(f"baud {baud}: abrindo {args.device}")
        try:
            with serial.Serial(args.device, baudrate=baud, timeout=0, write_timeout=1) as port:
                port.dtr = False
                port.rts = False
                time.sleep(args.settle)

                initial = read_for(port, args.listen_first)
                line = f"baud={baud} initial {describe(initial)}"
                print(line)
                log_line(log_path, line)

                for command in SAFE_COMMANDS:
                    for ending in LINE_ENDINGS:
                        payload = (command + ending).encode()
                        port.reset_input_buffer()
                        port.write(payload)
                        port.flush()
                        response = read_for(port, args.response_window)
                        if response:
                            ending_name = ending.encode().hex() or "none"
                            line = (
                                f"baud={baud} command={command!r} ending={ending_name} "
                                f"response {describe(response)}"
                            )
                            print(line)
                            log_line(log_path, line)
        except serial.SerialException as exc:
            line = f"baud={baud} erro={exc}"
            print(line)
            log_line(log_path, line)

    print(f"log salvo em {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

