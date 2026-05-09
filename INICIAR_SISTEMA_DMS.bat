@echo off
cd /d "%~dp0"
title DMS Sublimaciones - Sistema PRO V10 Inventario Categorias
python -m pip install -r requirements.txt
python app.py
pause
