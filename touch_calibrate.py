#!/usr/bin/env python3
"""Guided touch calibration for the button device."""

from __future__ import annotations

import argparse
import csv
import json
import select
import statistics
import time
from pathlib import Path

import serial


DEFAULT_DEVICE = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
DEFAULT_OUTPUT = "/home/paulo/botao-lab/logs/touch_calibration.csv"
DEFAULT_ZONES = "/home/paulo/botao-lab/protocolo/touch_zones_calibrated.json"
PACKET_HEADER = bytes.fromhex("a5 3c 00 08 00")
PACKET_SIZE = 13
TOUCH_CODES = {0x05, 0x07, 0x09, 0x0A}
DEFAULT_LABELS = [
    "centro",
    "cima",
    "baixo",
    "esquerda",
    "direita",
    "canto_superior_esquerdo",
    "canto_superior_direito",
    "canto_inferior_esquerdo",
    "canto_inferior_direito",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--zones-output", default=DEFAULT_ZONES)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=12)
    parser.add_argument("--labels", nargs="*", default=DEFAULT_LABELS)
    return parser.parse_args()


def iter_packets(buffer: bytearray, data: bytes) -> list[bytes]:
    packets: list[bytes] = []
    buffer.extend(data)

    while True:
        header_at = buffer.find(PACKET_HEADER)
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
    if len(packet) != PACKET_SIZE or not packet.startswith(PACKET_HEADER):
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


def capture_touch(port: serial.Serial, timeout: float) -> dict[str, int] | None:
    started = time.monotonic()
    buffer = bytearray()

    while time.monotonic() - started < timeout:
        readable, _, _ = select.select([port.fileno()], [], [], 0.1)
        if not readable:
            continue

        data = port.read(4096)
        for packet in iter_packets(buffer, data):
            touch = parse_touch(packet)
            if touch:
                return touch

    return None


def write_zones(rows: list[dict[str, object]], path: Path) -> None:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row["label"]), []).append(row)

    centers = {}
    for label, points in grouped.items():
        centers[label] = {
            "x": round(statistics.mean(int(point["x"]) for point in points)),
            "y": round(statistics.mean(int(point["y"]) for point in points)),
        }

    config = {
        "centers": centers,
        "samples": rows,
        "note": "Use esses centros para ajustar touch_zones.json conforme o formato fisico real.",
    }
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    zones_output = Path(args.zones_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    zones_output.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []

    with serial.Serial(args.device, baudrate=args.baud, timeout=0, write_timeout=1) as port:
        print(f"Calibrando touch em {args.device} a {args.baud} baud")
        print("Pressione Enter antes de cada etapa, toque no ponto indicado e aguarde a captura.")

        for label in args.labels:
            for sample in range(1, args.samples + 1):
                input(f"{label} amostra {sample}/{args.samples}: Enter para capturar...")
                touch = capture_touch(port, args.timeout)
                if not touch:
                    print("timeout sem touch")
                    continue

                row = {
                    "label": label,
                    "sample": sample,
                    "code": f"{touch['code']:02x}",
                    "flag": f"{touch['flag']:02x}",
                    "x": touch["x"],
                    "y": touch["y"],
                    "tail": f"{touch['tail']:02x}",
                    "checksum": f"{touch['checksum']:02x}",
                }
                rows.append(row)
                print(f"capturado {label}: x={touch['x']} y={touch['y']}")

    with output.open("w", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["label", "sample", "code", "flag", "x", "y", "tail", "checksum"],
        )
        writer.writeheader()
        writer.writerows(rows)

    write_zones(rows, zones_output)
    print(f"CSV salvo em {output}")
    print(f"Resumo salvo em {zones_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
