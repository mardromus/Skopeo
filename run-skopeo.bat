@echo off
rem Skopeo one-click launcher for Windows: updates packages, builds the UI, starts http://127.0.0.1:8000
setlocal
cd /d "%~dp0"
title Skopeo
set "PY=backend\.venv\Scripts\python.exe"

echo.
echo === 1/3  Backend packages ===
if not exist "%PY%" (
  echo Creating backend\.venv ...
  where uv >nul 2>nul && (uv venv backend\.venv) || (py -3 -m venv backend\.venv)
)
where uv >nul 2>nul
if %errorlevel%==0 (
  uv pip install --python "%PY%" -U -r backend\requirements-dev.txt || goto :fail
) else (
  "%PY%" -m pip --version >nul 2>nul || "%PY%" -m ensurepip --upgrade
  "%PY%" -m pip install -U -r backend\requirements-dev.txt || goto :fail
)

echo.
echo === 2/3  Web UI (npm install + build) ===
pushd frontend
call npm install --no-audit --no-fund || (popd & goto :fail)
call npm run build || (popd & goto :fail)
popd

echo.
echo === 3/3  Starting Skopeo on http://127.0.0.1:8000  (close this window to stop) ===
set "SKOPEO_DEMO_STEP_DELAY_MS=120"
set "LOG_JSON=false"
start "" cmd /c "timeout /t 8 >nul & start http://127.0.0.1:8000"
"%PY%" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
goto :eof

:fail
echo.
echo Something failed above - scroll up for the error.
pause
