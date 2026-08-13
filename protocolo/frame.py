#!/usr/bin/env python3
"""Build and decode known 13-byte Wisecoco knob UART frames."""

from __future__ import annotations

import argparse


HEADER = bytes.fromhex("a5 3c 00 08 00")
PACKET_SIZE = 13
TOUCH_CODES = {0x05, 0x07, 0x09, 0x0A}


def checksum(payload7: bytes) -> int:
    if len(payload7) != 7:
        raise ValueError("payload must have 7 bytes")
    return (0xBB - (sum(payload7) & 0xFF)) & 0xFF


def build_frame(code: int, flag: int = 0, x: int = 0, y: int = 0, tail: int = 0) -> bytes:
    payload = bytes(
        [
            code & 0xFF,
            flag & 0xFF,
            x & 0xFF,
            (x >> 8) & 0xFF,
            y & 0xFF,
            (y >> 8) & 0xFF,
            tail & 0xFF,
        ]
    )
    return HEADER + payload + bytes([checksum(payload)])


def parse_frame(frame: bytes) -> dict[str, int | bool]:
    if len(frame) != PACKET_SIZE:
        raise ValueError("frame must have 13 bytes")
    if not frame.startswith(HEADER):
        raise ValueError("invalid frame header")

    payload = frame[5:12]
    return {
        "code": payload[0],
        "flag": payload[1],
        "x": payload[2] | (payload[3] << 8),
        "y": payload[4] | (payload[5] << 8),
        "tail": payload[6],
        "checksum": frame[12],
        "checksum_ok": frame[12] == checksum(payload),
    }


def iter_packets(buffer: bytearray, data: bytes) -> list[bytes]:
    """Split a raw serial byte stream into complete 13-byte frames."""
    packets: list[bytes] = []
    buffer.extend(data)

    while True:
        header_at = buffer.find(HEADER)
        if header_at == -1:
            buffer.clear()
            return packets

        if header_at > 0:
            del buffer[:header_at]

        if len(buffer) < PACKET_SIZE:
            return packets

        packets.append(bytes(buffer[:PACKET_SIZE]))
        del buffer[:PACKET_SIZE]


def parse_touch(packet: bytes) -> dict[str, int] | None:
    """Decode a frame as a touch event, or return None if it isn't one."""
    if len(packet) != PACKET_SIZE or not packet.startswith(HEADER):
        return None

    code = packet[5]
    if code not in TOUCH_CODES:
        return None

    return {
        "code": code,
        "flag": packet[6],
        "x": int.from_bytes(packet[7:9], "little"),
        "y": int.from_bytes(packet[9:11], "little"),
        "tail": packet[11],
        "checksum": packet[12],
    }


def find_zone(zones: list[dict[str, object]], x: int, y: int) -> dict[str, object] | None:
    """Return the configured zone containing (x, y), or None."""
    for zone in zones:
        if (
            int(zone["x_min"]) <= x <= int(zone["x_max"])
            and int(zone["y_min"]) <= y <= int(zone["y_max"])
        ):
            return zone
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--flag", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--x", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--y", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--tail", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--parse")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.parse:
        frame = bytes.fromhex(args.parse)
        print(parse_frame(frame))
        return 0

    frame = build_frame(args.code, args.flag, args.x, args.y, args.tail)
    print(frame.hex(" "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

