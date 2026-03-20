@echo off
title PoliMirror Quartz Server
cd /d "%~dp0quartz"

:loop
echo [%date% %time%] Starting Quartz server...
call npx quartz build --serve
echo [%date% %time%] Server exited, restarting in 3 seconds...
timeout /t 3 /noq
goto loop
