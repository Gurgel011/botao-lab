#!/usr/bin/env python3
"""Touch-driven function engine for the knob display.

This is the safe autonomy layer: touch zones call named user functions from a
JSON file. Firmware flashing is not required.
"""

from __future__ import annotations

import argparse
import ast
import json
import select
import subprocess
import sys
import time
from pathlib import Path

import serial

from protocolo.frame import find_zone as _find_zone_obj
from protocolo.frame import iter_packets, parse_touch


DEFAULT_DEVICE = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
DEFAULT_ZONES = "/home/paulo/botao-lab/protocolo/touch_zones.json"
DEFAULT_CONFIG = "/home/paulo/botao-lab/config/user_functions.json"
DEFAULT_LOG = "/home/paulo/botao-lab/logs/user_functions.log"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--zones", default=DEFAULT_ZONES)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--log", default=DEFAULT_LOG)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--debounce", type=float, default=0.35)
    parser.add_argument("--allow-shell", action="store_true")
    parser.add_argument("--allow-serial-write", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def find_zone(zones: list[dict[str, object]], x: int, y: int) -> str:
    zone = _find_zone_obj(zones, x, y)
    return str(zone["name"]) if zone else "fora_zona"


def run_gdbus(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gdbus", *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def list_mpris_players() -> list[str]:
    result = run_gdbus(
        [
            "call",
            "--session",
            "--dest",
            "org.freedesktop.DBus",
            "--object-path",
            "/org/freedesktop/DBus",
            "--method",
            "org.freedesktop.DBus.ListNames",
        ]
    )
    if result.returncode != 0:
        return []

    try:
        names = ast.literal_eval(result.stdout.strip())[0]
    except (SyntaxError, ValueError, IndexError):
        return []
    return sorted(name for name in names if name.startswith("org.mpris.MediaPlayer2."))


def media_method(command: str) -> str | None:
    return {
        "toggle": "PlayPause",
        "play": "Play",
        "pause": "Pause",
        "next": "Next",
        "previous": "Previous",
    }.get(command)


def execute_media(command: str) -> tuple[bool, str]:
    method = media_method(command)
    if method is None:
        return False, f"media command invalido: {command}"

    for player in list_mpris_players():
        result = run_gdbus(
            [
                "call",
                "--session",
                "--dest",
                player,
                "--object-path",
                "/org/mpris/MediaPlayer2",
                "--method",
                f"org.mpris.MediaPlayer2.Player.{method}",
            ]
        )
        if result.returncode == 0:
            return True, player.replace("org.mpris.MediaPlayer2.", "")
    return False, "sem-player"


def log_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as file:
        file.write(line + "\n")


def execute_function(
    *,
    function_name: str,
    function_config: dict[str, object],
    touch: dict[str, int],
    zone: str,
    port: serial.Serial,
    args: argparse.Namespace,
) -> tuple[bool, str]:
    function_type = str(function_config.get("type", "log"))

    if function_type == "media":
        return execute_media(str(function_config.get("command", "toggle")))

    if function_type == "log":
        message = str(function_config.get("message", function_name))
        return True, message

    if function_type == "shell":
        if not args.allow_shell:
            return False, "shell bloqueado; use --allow-shell"
        command = function_config.get("command")
        if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
            return False, "shell command invalido"
        result = subprocess.run(command, check=False)
        return result.returncode == 0, f"shell exit={result.returncode}"

    if function_type == "serial_write":
        if not args.allow_serial_write:
            return False, "serial_write bloqueado; use --allow-serial-write"
        data = function_config.get("hex")
        if isinstance(data, str):
            payload = bytes.fromhex(data)
        else:
            text = str(function_config.get("text", ""))
            payload = text.encode()
        port.write(payload)
        port.flush()
        return True, f"serial_write {len(payload)} bytes"

    return False, f"tipo desconhecido: {function_type}"


def main() -> int:
    args = parse_args()
    zone_data = load_json(Path(args.zones))
    zones = list(zone_data.get("zones", []))
    config = load_json(Path(args.config))
    zone_map = dict(config.get("zones", {}))
    functions = dict(config.get("functions", {}))

    print(f"botao_functions ouvindo {args.device} a {args.baud} baud")
    print(f"config: {args.config}")
    print("zonas:", ", ".join(zone_map.keys()))

    started = time.monotonic()
    last_event = 0.0
    buffer = bytearray()
    log_path = Path(args.log)

    with serial.Serial(args.device, args.baud, timeout=0, write_timeout=1) as port:
        while True:
            if args.duration is not None and time.monotonic() - started >= args.duration:
                break

            readable, _, _ = select.select([port.fileno()], [], [], 0.1)
            if not readable:
                continue

            data = port.read(4096)
            for packet in iter_packets(buffer, data):
                touch = parse_touch(packet)
                if touch is None:
                    continue

                now = time.monotonic()
                if now - last_event < args.debounce:
                    continue
                last_event = now

                zone = find_zone(zones, touch["x"], touch["y"])
                function_name = str(zone_map.get(zone, zone_map.get("fora_zona", "log_touch")))
                function_config = functions.get(function_name)
                if not isinstance(function_config, dict):
                    function_config = {"type": "log", "message": "funcao nao encontrada"}

                ok, detail = execute_function(
                    function_name=function_name,
                    function_config=function_config,
                    touch=touch,
                    zone=zone,
                    port=port,
                    args=args,
                )

                line = (
                    f"{time.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"zone={zone} function={function_name} ok={ok} "
                    f"x={touch['x']} y={touch['y']} code={touch['code']:02x} detail={detail}"
                )
                print(line)
                log_line(log_path, line)
                sys.stdout.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

