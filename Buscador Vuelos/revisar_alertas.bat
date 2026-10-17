@echo off
REM Revisa las alertas de precio. La app crea su propia version con la ruta exacta de Python.
cd /d "%~dp0"
python alertas.py >> alertas.log 2>&1
