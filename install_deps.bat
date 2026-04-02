@echo off
cd /d "D:\TG SYSTEM\telegram-content-platform"
call venv\Scripts\activate.bat
pip install --no-cache-dir -r backend\requirements.txt
echo.
echo === INSTALL COMPLETE ===
