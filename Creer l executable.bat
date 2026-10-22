@echo off
setlocal
cd /d "%~dp0"
title Sonotheque - creation de l'executable

if not exist ".venv\Scripts\python.exe" (
  echo Lancez d'abord "Lancer Sonotheque.bat" une fois pour installer les dependances.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install pyinstaller
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed ^
  --name Sonotheque --icon assets\icon.ico --add-data "assets;assets" main.py
if errorlevel 1 (echo Echec du build & pause & exit /b 1)
echo.
echo Termine : dist\Sonotheque\Sonotheque.exe
echo Vous pouvez copier le dossier dist\Sonotheque ou vous voulez et creer un raccourci.
explorer dist\Sonotheque
pause
