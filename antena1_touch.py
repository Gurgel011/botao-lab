#!/usr/bin/env python3
"""Antena 1 touch controller.

Shows the Antena 1 logo and toggles play/pause when the device touch is used.
"""

from __future__ import annotations

import argparse
import ast
import json
import select
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import os

import serial
from PIL import Image, ImageTk

ROOT = Path(__file__).resolve().parent

# Descubra o seu com: ls /dev/serial/by-id/
DEFAULT_DEVICE = os.environ.get("BOTAO_DEVICE", "/dev/ttyUSB0")
DEFAULT_LOGO = str(ROOT / "assets" / "antena1_logo.png")
DEFAULT_CONFIG = str(ROOT / "config" / "play_pause.json")
PACKET_HEADER = bytes.fromhex("a5 3c 00 08 00")
PACKET_SIZE = 13
TOUCH_CODES = {0x05, 0x07, 0x09, 0x0A}

ACTION_LABELS = {
    "toggle": "Alternar Play/Pause",
    "play": "Sempre Play",
    "pause": "Sempre Pause",
    "visual": "Somente visual",
}
ACTION_BY_LABEL = {label: action for action, label in ACTION_LABELS.items()}
DEFAULT_SETTINGS = {
    "touch_action": "toggle",
    "send_media": True,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--logo", default=DEFAULT_LOGO)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--debounce", type=float, default=0.8)
    parser.add_argument(
        "--no-media",
        action="store_true",
        help="Only update the UI, without sending play/pause to media players.",
    )
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
        "checksum": packet[12],
    }


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


def toggle_media() -> tuple[bool, str]:
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
                "org.mpris.MediaPlayer2.Player.PlayPause",
            ]
        )
        if result.returncode == 0:
            return True, player.replace("org.mpris.MediaPlayer2.", "")

    result = run_gdbus(
        [
            "call",
            "--session",
            "--dest",
            "org.gnome.SettingsDaemon.MediaKeys",
            "--object-path",
            "/org/gnome/SettingsDaemon/MediaKeys",
            "--method",
            "org.gnome.SettingsDaemon.MediaKeys.MediaPlayerKeyPressed",
            "antena1-touch",
            "Play",
        ]
    )
    if result.returncode == 0:
        return True, "media-key"

    return False, "sem-player"


def media_command(method: str) -> tuple[bool, str]:
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

    result = run_gdbus(
        [
            "call",
            "--session",
            "--dest",
            "org.gnome.SettingsDaemon.MediaKeys",
            "--object-path",
            "/org/gnome/SettingsDaemon/MediaKeys",
            "--method",
            "org.gnome.SettingsDaemon.MediaKeys.MediaPlayerKeyPressed",
            "antena1-touch",
            "Play" if method == "Play" else "Pause",
        ]
    )
    if result.returncode == 0:
        return True, "media-key"

    return False, "sem-player"


def load_settings(path: Path) -> dict[str, object]:
    settings = dict(DEFAULT_SETTINGS)
    if not path.exists():
        return settings

    try:
        loaded = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return settings

    if loaded.get("touch_action") in ACTION_LABELS:
        settings["touch_action"] = loaded["touch_action"]
    if isinstance(loaded.get("send_media"), bool):
        settings["send_media"] = loaded["send_media"]
    return settings


def save_settings(path: Path, settings: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")


class AntenaTouchApp:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.config_path = Path(args.config)
        self.settings = load_settings(self.config_path)
        self.playing = False
        self.last_touch = 0.0
        self.stop_event = threading.Event()

        self.root = tk.Tk()
        self.root.title("Antena 1 Touch")
        self.root.geometry("760x420")
        self.root.minsize(520, 320)
        self.root.configure(bg="#f4f4f1")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.status_var = tk.StringVar(value="Pronto para tocar")
        self.detail_var = tk.StringVar(value="Touch aguardando escolha")
        self.action_var = tk.StringVar(
            value=ACTION_LABELS[str(self.settings["touch_action"])]
        )
        self.send_media_var = tk.BooleanVar(value=bool(self.settings["send_media"]))

        self.logo_image = self.load_logo(Path(args.logo), max_width=680, max_height=210)
        logo_label = tk.Label(self.root, image=self.logo_image, bg="#f4f4f1")
        logo_label.pack(side=tk.TOP, pady=(24, 18))

        self.state_label = tk.Label(
            self.root,
            textvariable=self.status_var,
            bg="#f4f4f1",
            fg="#143f75",
            font=("Arial", 34, "bold"),
        )
        self.state_label.pack(pady=(8, 4))

        detail = tk.Label(
            self.root,
            textvariable=self.detail_var,
            bg="#f4f4f1",
            fg="#333333",
            font=("Arial", 13),
        )
        detail.pack(pady=(0, 18))

        controls = ttk.Frame(self.root)
        controls.pack(pady=(0, 12))

        ttk.Label(controls, text="Ação do touch").grid(row=0, column=0, padx=(0, 8))
        self.action_combo = ttk.Combobox(
            controls,
            textvariable=self.action_var,
            values=list(ACTION_LABELS.values()),
            state="readonly",
            width=22,
        )
        self.action_combo.grid(row=0, column=1, padx=(0, 12))
        self.action_combo.bind("<<ComboboxSelected>>", lambda _event: self.save_ui_settings())

        self.media_check = ttk.Checkbutton(
            controls,
            text="Enviar ao player",
            variable=self.send_media_var,
            command=self.save_ui_settings,
        )
        self.media_check.grid(row=0, column=2)

        buttons = ttk.Frame(self.root)
        buttons.pack(pady=(0, 12))

        self.toggle_button = ttk.Button(
            buttons,
            text="Alternar agora",
            command=lambda: self.execute_action(
                "toggle", {"x": 0, "y": 0, "code": 0, "flag": 0, "checksum": 0}
            ),
        )
        self.toggle_button.grid(row=0, column=0, padx=8)

        self.play_button = ttk.Button(
            buttons,
            text="Play",
            command=lambda: self.execute_action(
                "play", {"x": 0, "y": 0, "code": 0, "flag": 0, "checksum": 0}
            ),
        )
        self.play_button.grid(row=0, column=1, padx=8)

        self.pause_button = ttk.Button(
            buttons,
            text="Pause",
            command=lambda: self.execute_action(
                "pause", {"x": 0, "y": 0, "code": 0, "flag": 0, "checksum": 0}
            ),
        )
        self.pause_button.grid(row=0, column=2, padx=8)

        self.save_ui_settings()

    def load_logo(self, path: Path, max_width: int, max_height: int) -> ImageTk.PhotoImage:
        if not path.exists():
            raise FileNotFoundError(
                f"Logo nao encontrado em {path}. Coloque uma imagem ali ou "
                "informe outra com --logo <caminho>."
            )
        image = Image.open(path).convert("RGBA")
        image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(image)

    def set_status(self, text: str, detail: str) -> None:
        self.status_var.set(text)
        self.detail_var.set(detail)

    def selected_action(self) -> str:
        return ACTION_BY_LABEL.get(self.action_var.get(), "toggle")

    def save_ui_settings(self) -> None:
        self.settings = {
            "touch_action": self.selected_action(),
            "send_media": self.send_media_var.get(),
        }
        try:
            save_settings(self.config_path, self.settings)
        except OSError as exc:
            messagebox.showerror("Erro ao salvar", str(exc))

    def handle_touch(self, touch: dict[str, int]) -> None:
        now = time.monotonic()
        if now - self.last_touch < self.args.debounce:
            return

        self.last_touch = now
        self.execute_action(self.selected_action(), touch)

    def execute_action(self, action: str, touch: dict[str, int]) -> None:
        if action == "visual":
            self.set_status(
                "TOUCH",
                f"x={touch['x']} y={touch['y']} code={touch['code']:02x} - somente visual",
            )
            return

        if action == "toggle":
            self.playing = not self.playing
            display = "PLAY" if self.playing else "PAUSE"
            media_call = toggle_media
        elif action == "play":
            self.playing = True
            display = "PLAY"
            media_call = lambda: media_command("Play")
        elif action == "pause":
            self.playing = False
            display = "PAUSE"
            media_call = lambda: media_command("Pause")
        else:
            return

        media_ok = False
        media_target = "visual"
        if not self.args.no_media and self.send_media_var.get():
            media_ok, media_target = media_call()

        suffix = "enviado" if media_ok else "visual"
        self.set_status(
            display,
            f"x={touch['x']} y={touch['y']} code={touch['code']:02x} - {suffix}: {media_target}",
        )

    def serial_loop(self) -> None:
        buffer = bytearray()
        try:
            with serial.Serial(
                self.args.device,
                baudrate=self.args.baud,
                timeout=0,
                write_timeout=1,
            ) as port:
                self.root.after(0, self.set_status, "Pronto", "Toque no aparelho para Play/Pause")
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
            self.root.after(0, self.set_status, "Porta indisponível", str(exc))

    def run(self) -> None:
        thread = threading.Thread(target=self.serial_loop, daemon=True)
        thread.start()
        self.root.mainloop()
        self.stop_event.set()

    def close(self) -> None:
        self.stop_event.set()
        self.root.destroy()


def main() -> int:
    args = parse_args()
    app = AntenaTouchApp(args)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
