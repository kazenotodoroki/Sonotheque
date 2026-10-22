@echo off
setlocal
cd /d "%~dp0"
title Sonotheque

if exist ".venv\Scripts\pythonw.exe" goto run

echo Premiere installation de Sonotheque (1 a 2 minutes)...
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python n'est pas installe.
  echo Installez-le depuis https://www.python.org/downloads/  ^(cochez "Add python.exe to PATH"^)
  echo puis relancez ce fichier.
  pause
  exit /b 1
)
%PY% -m venv .venv || (echo Echec de creation de l'environnement & pause & exit /b 1)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt || (echo Echec de l'installation & pause & exit /b 1)

:run
start "" ".venv\Scripts\pythonw.exe" main.py
