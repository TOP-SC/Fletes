"""Cierra el proceso que escucha en el puerto de la API (evita código viejo en segundo plano)."""
from __future__ import annotations

import subprocess
import sys

PORT = 8000


def main() -> int:
    if sys.platform != "win32":
        print("kill_api_port: solo Windows en este proyecto")
        return 0

    out = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True,
        text=True,
        check=False,
    )
    pids: set[str] = set()
    for line in out.stdout.splitlines():
        if f":{PORT}" not in line or "LISTENING" not in line.upper():
            continue
        parts = line.split()
        if parts:
            pids.add(parts[-1])

    if not pids:
        print(f"Puerto {PORT}: libre")
        return 0

    for pid in pids:
        if pid.isdigit() and int(pid) > 0:
            subprocess.run(["taskkill", "/F", "/PID", pid], check=False)
            print(f"Puerto {PORT}: proceso {pid} finalizado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
