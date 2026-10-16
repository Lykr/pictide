@echo off
setlocal
title Pictide
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
set "appExitCode=%errorlevel%"
if not "%appExitCode%"=="0" pause
exit /b %appExitCode%
