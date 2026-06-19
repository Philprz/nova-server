@echo off
REM Sonde FastAPI + future-annotations + Cython (Lot 5 phase 2).
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 (
  echo ERREUR: impossible de charger vcvars64.bat
  exit /b 1
)
set DISTUTILS_USE_SDK=1
set MSSdk=1
cd /d "%~dp0.."
".venv\Scripts\python.exe" scripts\probe_fastapi_future.py %*
