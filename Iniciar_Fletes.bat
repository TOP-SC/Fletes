@echo off
chcp 65001 >nul
title Control de Fletes
cd /d "%~dp0"

echo ========================================
echo   Control de Fletes - Iniciando...
echo ========================================
echo.

set "PYTHONPATH=%~dp0backend"
set "FLETES_API_URL=http://127.0.0.1:8000/api/v1"

echo [1/4] Cerrando API anterior (puerto 8000)...
python "%~dp0scripts\kill_api_port.py"
timeout /t 2 /nobreak >nul

echo [2/4] Iniciando servidor API (segundo plano)...
start "Fletes-API" /min cmd /c "cd /d "%~dp0backend" && set PYTHONPATH=%~dp0backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo [3/4] Esperando API...
python "%~dp0scripts\wait_api.py"

echo [4/4] Abriendo interfaz web...
cd /d "%~dp0frontend"
set "FLETES_API_URL=%FLETES_API_URL%"

start "" http://localhost:8501
python -m streamlit run streamlit_app.py --server.headless true

echo.
echo La aplicacion se cerro. La API puede seguir en segundo plano (ventana minimizada).
pause
