@echo off
chcp 65001 >nul
title ARTIQ Debug Launcher

cd /d "%~dp0"

start "ARTIQ Master" cmd /K "call E:\Anaconda3\Scripts\activate.bat artiq-7.8 && artiq_master --device-db device_db.py -r repository"

timeout /t 5 /nobreak >nul

start "ARTIQ Dashboard" cmd /K "call E:\Anaconda3\Scripts\activate.bat artiq-7.8 && artiq_dashboard"

pause