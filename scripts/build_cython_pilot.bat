@echo off
REM Wrapper Lot 5 : charge l'environnement MSVC x64 puis lance le build Cython.
REM Necessaire car setuptools ne localise pas toujours seul MS C++ Build Tools.
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 (
  echo ERREUR: impossible de charger vcvars64.bat
  exit /b 1
)
REM setuptools 80.x ne localise pas seul le BuildTools via vswhere : on lui dit
REM d'utiliser l'environnement MSVC deja charge ci-dessus (Developer prompt).
set DISTUTILS_USE_SDK=1
set MSSdk=1
cd /d "%~dp0.."
".venv\Scripts\python.exe" scripts\build_cython_pilot.py %*
