#!/usr/bin/env python3
"""Run a guided UART protocol capture and analyze the result."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path("/home/paulo/botao-lab")
DEFAULT_DEVICE = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
DEFAULT_LINK = "/tmp/botao_uart"
DEFAULT_LOG = ROOT / "logs" / "uart_mitm.log"
DEFAULT_RAW = ROOT / "logs" / "uart_mitm.raw"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--link", default=DEFAULT_LINK)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--append", action="store_true", help="nao limpa logs antes da captura")
    parser.add_argument("--json", action="store_true", help="tambem salva analise JSON")
    return parser.parse_args()


def run(command: list[str]) -> int:
    return subprocess.run(command, check=False).returncode


def main() -> int:
    args = parse_args()
    DEFAULT_LOG.parent.mkdir(parents=True, exist_ok=True)

    print("captura UART guiada", flush=True)
    print(f"porta real: {args.device}", flush=True)
    print(f"porta virtual para app/demo: {args.link}", flush=True)
    print(f"baud: {args.baud}", flush=True)
    print(f"duracao: {args.seconds:g}s", flush=True)
    print(flush=True)
    print("Durante a captura, abra o software/demo oficial apontando para:", flush=True)
    print(args.link, flush=True)
    print(flush=True)

    mitm_command = [
        str(ROOT / "uart_mitm.py"),
        "--device",
        args.device,
        "--baud",
        str(args.baud),
        "--link",
        args.link,
        "--log",
        str(DEFAULT_LOG),
        "--raw",
        str(DEFAULT_RAW),
        "--duration",
        str(args.seconds),
    ]
    if not args.append:
        mitm_command.append("--truncate")

    status = run(mitm_command)
    if status != 0:
        return status

    if not DEFAULT_RAW.exists() or DEFAULT_RAW.stat().st_size == 0:
        print(flush=True)
        print("captura terminou sem bytes no log bruto.", flush=True)
        print("Isso normalmente significa que nenhum app/demo abriu a porta virtual durante a janela.", flush=True)
        return 2

    print(flush=True)
    print("analise:", flush=True)
    status = run([str(ROOT / "analyze_uart.py"), str(DEFAULT_RAW), "--format", "mitm"])
    if status != 0:
        return status

    if args.json:
        json_path = ROOT / "logs" / "uart_mitm.analysis.json"
        with json_path.open("w") as file:
            json_status = subprocess.run(
                [str(ROOT / "analyze_uart.py"), str(DEFAULT_RAW), "--format", "mitm", "--json"],
                check=False,
                stdout=file,
            ).returncode
        if json_status != 0:
            return json_status
        print(flush=True)
        print(f"relatorio JSON: {json_path}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
