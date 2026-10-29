@echo off
setlocal
cd /d "%~dp0"
wscript.exe "%~dp0start-web.vbs" stop
exit /b
