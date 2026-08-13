#!/usr/bin/env python3
"""Decode raw serial captures from the button device."""

from __future__ import annotations

import argparse
from pathlib import Path


PACKET_SIZE = 13
HEADER = bytes.fromhex("a5 3c 00 08 00")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("logfile")
    return parser.parse_args()


def packet_kind(code: int) -> str:
    names = {
        0x00: "idle/release?",
        0x01: "press/init?",
        0x03: "gesture 03",
        0x04: "gesture 04",
        0x05: "touch/point?",
        0x07: "touch/point?",
        0x09: "touch/point?",
        0x0A: "touch/point?",
    }
    return names.get(code, f"unknown {code:02x}")


def packet_checksum(packet: bytes) -> int:
    return (0xBB - (sum(packet[5:12]) & 0xFF)) & 0xFF


def main() -> int:
    args = parse_args()
    data = Path(args.logfile).read_bytes()

    print(
        "idx off valid kind         code flag x_le y_le tail checksum raw",
    )
    print(
        "--- --- ----- ------------ ---- ---- ---- ---- ---- -------- -------------------------",
    )

    for index, offset in enumerate(range(0, len(data), PACKET_SIZE)):
        packet = data[offset : offset + PACKET_SIZE]
        if len(packet) != PACKET_SIZE:
            print(f"{index:03d} {offset:03d} short {packet.hex(' ')}")
            continue

        valid = "yes" if packet.startswith(HEADER) else "no"
        code = packet[5]
        flag = packet[6]
        x = int.from_bytes(packet[7:9], "little")
        y = int.from_bytes(packet[9:11], "little")
        tail = packet[11]
        checksum = packet[12]
        checksum_ok = checksum == packet_checksum(packet)
        print(
            f"{index:03d} {offset:03d} {valid:5} {packet_kind(code):12} "
            f"{code:02x}   {flag:02x}   {x:4d} {y:4d} {tail:02x}   "
            f"{checksum:02x}       {packet.hex(' ')} checksum_ok={checksum_ok}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
