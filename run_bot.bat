@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem .venv yo'q yoki boshqa kompyuterdan ko'chirilgan bo'lsa (Python yo'li mos emas) - qayta yaratamiz
".venv\Scripts\python.exe" -c "import telegram, dotenv" >nul 2>&1
if errorlevel 1 (
  echo .venv ishlamayapti, qayta yaratilmoqda...
  if exist .venv rmdir /s /q .venv
  py -3.12 -m venv .venv 2>nul || py -3.11 -m venv .venv 2>nul || py -3 -m venv .venv 2>nul || python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || (echo Kutubxonalarni o'rnatib bo'lmadi & pause & exit /b 1)
)
".venv\Scripts\python.exe" bot.py
pause
