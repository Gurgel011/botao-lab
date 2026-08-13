#!/usr/bin/env python3
"""UART man-in-the-middle bridge for protocol capture.

Creates a pseudo terminal for host software and forwards traffic to the real
knob display serial port while logging both directions.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import pty
import select
import signal
import sys
import time
from pathlib import Path

import serial


DEFAULT_DEVICE = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
DEFAULT_LINK = "/tmp/botao_uart"
DEFAULT_LOG = "/home/paulo/botao-lab/logs/uart_mitm.log"
DEFAULT_RAW = "/home/paulo/botao-lab/logs/uart_mitm.raw"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--link", default=DEFAULT_LINK)
    parser.add_argument("--log", default=DEFAULT_LOG)
    parser.add_argument("--raw", default=DEFAULT_RAW)
    parser.add_argument("--duration", type=float, default=0, help="segundos; 0 fica rodando ate Ctrl+C")
    parser.add_argument("--truncate", action="store_true", help="limpa os logs antes de capturar")
    return parser.parse_args()


def printable(data: bytes) -> str:
    return "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in data)


def log_packet(log_path: Path, direction: str, data: bytes) -> None:
    stamp = dt.datetime.now().isoformat(timespec="milliseconds")
    line = f"{stamp} {direction} len={len(data)} hex={data.hex(' ')} text={printable(data)}\n"
    with log_path.open("a") as file:
        file.write(line)


def raw_packet(raw_path: Path, direction: bytes, data: bytes) -> None:
    # Direction marker: b'H' host->device, b'D' device->host.
    stamp = int(dt.datetime.now().timestamp() * 1000)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("ab") as file:
        file.write(direction)
        file.write(stamp.to_bytes(8, "little"))
        file.write(len(data).to_bytes(4, "little"))
        file.write(data)


def replace_symlink(target: str, link: Path) -> None:
    try:
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(target)
    except OSError as exc:
        raise SystemExit(f"nao consegui criar symlink {link}: {exc}") from exc


def main() -> int:
    args = parse_args()
    log_path = Path(args.log)
    raw_path = Path(args.raw)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if args.truncate:
        log_path.write_text("")
        raw_path.write_bytes(b"")

    master_fd, slave_fd = pty.openpty()
    slave_name = os.ttyname(slave_fd)
    os.close(slave_fd)
    replace_symlink(slave_name, Path(args.link))

    stop = False

    def handle_signal(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print(f"porta virtual para o app/host: {args.link} -> {slave_name}")
    print(f"porta real do aparelho: {args.device} @ {args.baud}")
    print(f"log texto: {log_path}")
    print(f"log bruto: {raw_path}")
    if args.duration:
        print(f"duracao: {args.duration:g}s")

    started = time.monotonic()
    with serial.Serial(args.device, args.baud, timeout=0, write_timeout=1) as device:
        while not stop:
            if args.duration and time.monotonic() - started >= args.duration:
                break

            readable, _, _ = select.select([master_fd, device.fileno()], [], [], 0.1)

            if master_fd in readable:
                try:
                    data = os.read(master_fd, 4096)
                except OSError:
                    break
                if data:
                    device.write(data)
                    device.flush()
                    log_packet(log_path, "HOST_TO_DEVICE", data)
                    raw_packet(raw_path, b"H", data)

            if device.fileno() in readable:
                data = device.read(4096)
                if data:
                    os.write(master_fd, data)
                    log_packet(log_path, "DEVICE_TO_HOST", data)
                    raw_packet(raw_path, b"D", data)

    try:
        os.close(master_fd)
    except OSError:
        pass

    print("ponte UART encerrada")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
