"""Espera a que la API responda (usado por Iniciar_Fletes.bat)."""
import sys
import time
import urllib.request

URL = "http://127.0.0.1:8000/health"
for i in range(45):
    try:
        urllib.request.urlopen(URL, timeout=1)
        print("API lista.")
        sys.exit(0)
    except Exception:
        time.sleep(1)
print("AVISO: la API no respondio a tiempo.")
sys.exit(0)
