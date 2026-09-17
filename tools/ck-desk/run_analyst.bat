@echo off
title CK Analyst
cd /d C:\Users\Patrick\Desktop\campus-kings\campus-kings
:loop
python tools\ck-desk\bot.py
echo.
echo [%date% %time%] Analyst stopped -- restarting in 30 seconds (Ctrl+C twice to quit for real)
timeout /t 30 /nobreak >nul
goto loop
