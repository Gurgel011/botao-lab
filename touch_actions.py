#!/usr/bin/env python3
"""Classify touch packets into configured zones and actions."""

from __future__ import annotations

import argparse
import json
import select
import time
from pathlib import Path

import serial

from protocolo.frame import find_zone, iter_packets, parse_touch


DEFAULT_DEVICE = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
DEFAULT_ZONES = "/home/paulo/botao-lab/protocolo/touch_zones.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--zones", default=DEFAULT_ZONES)
    parser.add_argument("--duration", type=float)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = json.loads(Path(args.zones).read_text())
    zones = config["zones"]
    started = time.monotonic()
    buffer = bytearray()

    with serial.Serial(args.device, baudrate=args.baud, timeout=0, write_timeout=1) as port:
        print(f"touch_actions ouvindo {args.device} a {args.baud} baud")
        while True:
            if args.duration is not None and time.monotonic() - started >= args.duration:
                break

            readable, _, _ = select.select([port.fileno()], [], [], 0.1)
            if not readable:
                continue

            data = port.read(4096)
            for packet in iter_packets(buffer, data):
                touch = parse_touch(packet)
                if not touch:
                    continue

                zone = find_zone(zones, touch["x"], touch["y"])
                zone_name = zone["name"] if zone else "fora_zona"
                action = zone["action"] if zone else "touch_unknown"
                print(
                    f"touch x={touch['x']} y={touch['y']} code={touch['code']:02x} "
                    f"flag={touch['flag']:02x} zone={zone_name} action={action}"
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
