#!/usr/bin/env python3
"""Analyze knob UART captures from raw serial logs or MITM logs."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import Counter
from pathlib import Path
from typing import Iterable, NamedTuple

from protocolo.frame import HEADER, PACKET_SIZE, parse_frame


class Chunk(NamedTuple):
    direction: str
    timestamp_ms: int | None
    data: bytes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", help="arquivo .bin/.raw para analisar")
    parser.add_argument(
        "--format",
        choices=("auto", "mitm", "raw"),
        default="auto",
        help="mitm = log bruto do uart_mitm.py; raw = bytes seriais puros",
    )
    parser.add_argument("--json", action="store_true", help="imprime resultado em JSON")
    return parser.parse_args()


def looks_like_mitm(data: bytes) -> bool:
    if len(data) < 13:
        return False
    if data[:1] not in (b"H", b"D"):
        return False
    length = int.from_bytes(data[9:13], "little")
    return 0 <= length <= len(data) - 13


def read_mitm(data: bytes) -> list[Chunk]:
    chunks: list[Chunk] = []
    offset = 0
    while offset < len(data):
        if offset + 13 > len(data):
            raise ValueError(f"registro MITM truncado no offset {offset}")

        marker = data[offset : offset + 1]
        if marker not in (b"H", b"D"):
            raise ValueError(f"marcador MITM invalido no offset {offset}: {marker!r}")

        timestamp_ms = int.from_bytes(data[offset + 1 : offset + 9], "little")
        length = int.from_bytes(data[offset + 9 : offset + 13], "little")
        start = offset + 13
        end = start + length
        if end > len(data):
            raise ValueError(f"payload MITM truncado no offset {offset}")

        direction = "HOST_TO_DEVICE" if marker == b"H" else "DEVICE_TO_HOST"
        chunks.append(Chunk(direction, timestamp_ms, data[start:end]))
        offset = end
    return chunks


def read_raw(data: bytes) -> list[Chunk]:
    return [Chunk("RAW", None, data)]


def find_known_frames(data: bytes) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    search_from = 0
    while True:
        offset = data.find(HEADER, search_from)
        if offset < 0:
            break
        packet = data[offset : offset + PACKET_SIZE]
        if len(packet) < PACKET_SIZE:
            frames.append(
                {
                    "offset": offset,
                    "complete": False,
                    "raw": packet.hex(" "),
                }
            )
            break

        parsed = parse_frame(packet)
        frames.append(
            {
                "offset": offset,
                "complete": True,
                "raw": packet.hex(" "),
                **parsed,
            }
        )
        search_from = offset + 1
    return frames


def hex_preview(data: bytes, limit: int = 64) -> str:
    preview = data[:limit].hex(" ")
    if len(data) > limit:
        return f"{preview} ..."
    return preview


def summarize(chunks: Iterable[Chunk]) -> dict[str, object]:
    chunk_list = list(chunks)
    direction_bytes = Counter()
    all_frames: list[dict[str, object]] = []
    unknown_chunks: list[dict[str, object]] = []

    for index, chunk in enumerate(chunk_list):
        direction_bytes[chunk.direction] += len(chunk.data)
        frames = find_known_frames(chunk.data)
        for frame in frames:
            frame["chunk"] = index
            frame["direction"] = chunk.direction
            frame["timestamp_ms"] = chunk.timestamp_ms
            all_frames.append(frame)

        covered = len(frames) * PACKET_SIZE
        if not frames or covered != len(chunk.data):
            unknown_chunks.append(
                {
                    "chunk": index,
                    "direction": chunk.direction,
                    "timestamp_ms": chunk.timestamp_ms,
                    "len": len(chunk.data),
                    "preview": hex_preview(chunk.data),
                    "known_frames_found": len(frames),
                }
            )

    code_counts = Counter()
    checksum_bad = 0
    x_values: list[int] = []
    y_values: list[int] = []
    for frame in all_frames:
        if not frame.get("complete"):
            continue
        code_counts[f"0x{int(frame['code']):02x}"] += 1
        if not frame.get("checksum_ok"):
            checksum_bad += 1
        x_values.append(int(frame["x"]))
        y_values.append(int(frame["y"]))

    coordinates = None
    if x_values and y_values:
        coordinates = {
            "x_min": min(x_values),
            "x_max": max(x_values),
            "y_min": min(y_values),
            "y_max": max(y_values),
        }

    return {
        "chunks": len(chunk_list),
        "bytes_by_direction": dict(direction_bytes),
        "known_frames": len(all_frames),
        "codes": dict(sorted(code_counts.items())),
        "checksum_bad": checksum_bad,
        "coordinates": coordinates,
        "unknown_chunks": unknown_chunks,
        "frames": all_frames,
    }


def print_human(summary: dict[str, object]) -> None:
    print(f"chunks: {summary['chunks']}")
    print(f"bytes_by_direction: {summary['bytes_by_direction']}")
    print(f"known_frames: {summary['known_frames']}")
    print(f"codes: {summary['codes']}")
    print(f"checksum_bad: {summary['checksum_bad']}")
    print(f"coordinates: {summary['coordinates']}")

    unknown_chunks = summary["unknown_chunks"]
    if unknown_chunks:
        print("\nunknown_or_mixed_chunks:")
        for chunk in unknown_chunks:
            stamp = chunk["timestamp_ms"]
            if stamp is not None:
                stamp_text = dt.datetime.fromtimestamp(stamp / 1000).isoformat(timespec="milliseconds")
            else:
                stamp_text = "-"
            print(
                f"- chunk={chunk['chunk']} dir={chunk['direction']} time={stamp_text} "
                f"len={chunk['len']} frames={chunk['known_frames_found']} "
                f"hex={chunk['preview']}"
            )

    print("\nframes:")
    for frame in summary["frames"]:
        if not frame.get("complete"):
            print(f"- chunk={frame['chunk']} off={frame['offset']} incomplete raw={frame['raw']}")
            continue
        print(
            f"- chunk={frame['chunk']} dir={frame['direction']} off={frame['offset']} "
            f"code=0x{int(frame['code']):02x} flag=0x{int(frame['flag']):02x} "
            f"x={frame['x']} y={frame['y']} tail=0x{int(frame['tail']):02x} "
            f"checksum_ok={frame['checksum_ok']} raw={frame['raw']}"
        )


def main() -> int:
    args = parse_args()
    data = Path(args.capture).read_bytes()
    capture_format = args.format
    if capture_format == "auto":
        capture_format = "mitm" if looks_like_mitm(data) else "raw"

    chunks = read_mitm(data) if capture_format == "mitm" else read_raw(data)
    summary = summarize(chunks)

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print_human(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
