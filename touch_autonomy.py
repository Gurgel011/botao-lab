#!/usr/bin/env python3
"""User-configurable touch autonomy panel for the knob display."""

from __future__ import annotations

import argparse
import ast
import json
import os
import select
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import serial

from protocolo.frame import find_zone as _find_zone_obj
from protocolo.frame import iter_packets, parse_touch

ROOT = Path(__file__).resolve().parent
# Descubra o seu com: ls /dev/serial/by-id/
DEFAULT_DEVICE = os.environ.get("BOTAO_DEVICE", "/dev/ttyUSB0")
DEFAULT_ZONES = str(ROOT / "protocolo" / "touch_zones.json")
DEFAULT_CONFIG = str(ROOT / "config" / "touch_autonomy.json")

ACTIONS = {
    "toggle": "Alternar Play/Pause",
    "play": "Play",
    "pause": "Pause",
    "visual": "Somente visual",
}
ACTION_BY_LABEL = {label: action for action, label in ACTIONS.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--zones", default=DEFAULT_ZONES)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--debounce", type=float, default=0.35)
    parser.add_argument("--no-media", action="store_true")
    return parser.parse_args()


def load_json(path: Path, fallback: dict) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return fallback


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


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


def send_media(action: str) -> tuple[bool, str]:
    method = {
        "toggle": "PlayPause",
        "play": "Play",
        "pause": "Pause",
    }.get(action)
    if method is None:
        return False, "visual"

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


class TouchAutonomyApp:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.zones_path = Path(args.zones)
        self.config_path = Path(args.config)
        self.zone_config = load_json(self.zones_path, {"zones": []})
        self.zones = list(self.zone_config.get("zones", []))
        self.config = load_json(
            self.config_path,
            {
                "send_media": True,
                "default_action": "toggle",
                "zones": {},
            },
        )
        self.playing = False
        self.last_event = 0.0
        self.stop_event = threading.Event()

        self.root = tk.Tk()
        self.root.title("Autonomia do Touch")
        self.root.geometry("720x430")
        self.root.minsize(620, 360)

        self.status_var = tk.StringVar(value="Aguardando touch")
        self.detail_var = tk.StringVar(value="Configure a ação de cada região")
        self.send_media_var = tk.BooleanVar(value=bool(self.config.get("send_media", True)))
        self.zone_vars: dict[str, tk.StringVar] = {}

        ttk.Label(self.root, text="Autonomia do Touch", font=("Arial", 20, "bold")).pack(pady=(16, 6))
        ttk.Label(self.root, textvariable=self.status_var, font=("Arial", 14)).pack()
        ttk.Label(self.root, textvariable=self.detail_var).pack(pady=(2, 12))

        controls = ttk.Frame(self.root)
        controls.pack(fill=tk.X, padx=24)

        ttk.Checkbutton(
            controls,
            text="Enviar ações para o player",
            variable=self.send_media_var,
            command=self.save_config,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        zone_names = [str(zone["name"]) for zone in self.zones] + ["fora_zona"]
        for row, zone_name in enumerate(zone_names, start=1):
            ttk.Label(controls, text=zone_name).grid(row=row, column=0, sticky="w", pady=4)
            action = self.config.get("zones", {}).get(zone_name, self.config.get("default_action", "toggle"))
            var = tk.StringVar(value=ACTIONS.get(action, ACTIONS["visual"]))
            self.zone_vars[zone_name] = var
            combo = ttk.Combobox(
                controls,
                textvariable=var,
                values=list(ACTIONS.values()),
                state="readonly",
                width=24,
            )
            combo.grid(row=row, column=1, sticky="w", pady=4)
            combo.bind("<<ComboboxSelected>>", lambda _event: self.save_config())

        buttons = ttk.Frame(self.root)
        buttons.pack(pady=16)
        ttk.Button(buttons, text="Salvar", command=self.save_config).grid(row=0, column=0, padx=8)
        ttk.Button(buttons, text="Teste Toggle", command=lambda: self.execute("toggle", "manual", 0, 0)).grid(row=0, column=1, padx=8)
        ttk.Button(buttons, text="Teste Play", command=lambda: self.execute("play", "manual", 0, 0)).grid(row=0, column=2, padx=8)
        ttk.Button(buttons, text="Teste Pause", command=lambda: self.execute("pause", "manual", 0, 0)).grid(row=0, column=3, padx=8)

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.save_config()

    def save_config(self) -> None:
        data = {
            "send_media": self.send_media_var.get(),
            "default_action": "toggle",
            "zones": {
                zone: ACTION_BY_LABEL.get(var.get(), "visual")
                for zone, var in self.zone_vars.items()
            },
        }
        self.config = data
        try:
            save_json(self.config_path, data)
        except OSError as exc:
            messagebox.showerror("Erro ao salvar", str(exc))

    def execute(self, action: str, zone: str, x: int, y: int) -> None:
        if action == "toggle":
            self.playing = not self.playing
            display = "PLAY" if self.playing else "PAUSE"
        elif action == "play":
            self.playing = True
            display = "PLAY"
        elif action == "pause":
            self.playing = False
            display = "PAUSE"
        else:
            display = "TOUCH"

        ok = False
        target = "visual"
        if self.send_media_var.get() and not self.args.no_media and action != "visual":
            ok, target = send_media(action)

        suffix = "enviado" if ok else target
        self.status_var.set(f"{zone}: {display}")
        self.detail_var.set(f"x={x} y={y} action={action} destino={suffix}")

    def handle_touch(self, touch: dict[str, int]) -> None:
        now = time.monotonic()
        if now - self.last_event < self.args.debounce:
            return
        self.last_event = now

        zone = find_zone(self.zones, touch["x"], touch["y"])
        action = self.config.get("zones", {}).get(zone, self.config.get("default_action", "toggle"))
        self.execute(str(action), zone, touch["x"], touch["y"])

    def serial_loop(self) -> None:
        buffer = bytearray()
        try:
            with serial.Serial(self.args.device, self.args.baud, timeout=0, write_timeout=1) as port:
                self.root.after(0, self.detail_var.set, f"Ouvindo {self.args.device}")
                while not self.stop_event.is_set():
                    readable, _, _ = select.select([port.fileno()], [], [], 0.1)
                    if not readable:
                        continue
                    data = port.read(4096)
                    for packet in iter_packets(buffer, data):
                        touch = parse_touch(packet)
                        if touch:
                            self.root.after(0, self.handle_touch, touch)
        except serial.SerialException as exc:
            self.root.after(0, self.status_var.set, "Porta indisponível")
            self.root.after(0, self.detail_var.set, str(exc))

    def run(self) -> None:
        thread = threading.Thread(target=self.serial_loop, daemon=True)
        thread.start()
        self.root.mainloop()
        self.stop_event.set()

    def close(self) -> None:
        self.stop_event.set()
        self.root.destroy()


def main() -> int:
    app = TouchAutonomyApp(parse_args())
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

