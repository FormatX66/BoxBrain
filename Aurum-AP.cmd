@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Aurum.ps1" -UsePiAp
if errorlevel 1 (
  echo.
  echo Aurum AP connection did not complete. Review the message above.
  pause
)
endlocal
