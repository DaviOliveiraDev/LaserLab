@echo off
echo ====================================================================
echo    INICIANDO SISTEMA INDUSTRIAL DE GRAVACAO LASER EM LENTES
echo ====================================================================

:: Start backend in a new window with correct Uvicorn reload exclusions
echo [1/2] Iniciando backend FastAPI com exclusoes de reload...
start "FastAPI Backend" cmd /k ".\venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload --reload-dir backend"

:: Start frontend in the current window
echo [2/2] Iniciando frontend Vite React...
cd frontend
npm run dev

pause
