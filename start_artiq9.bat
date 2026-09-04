@echo off
chcp 65001 >nul
start "ARTIQ MonInj Proxy" /min cmd /K "E:\msys64\clang64\bin\aqctl_moninj_proxy.exe --port-proxy 1383 --port-control 1384 --bind ::1 192.168.1.45"

start "ARTIQ Analyzer Proxy" /min cmd /K "E:\msys64\clang64\bin\aqctl_analyzer_proxy.exe --port-proxy 1381 --port-control 1382 --bind ::1"

start "ARTIQ Master" /min cmd /K "cd /d E:\文档\Artiq-Rice && E:\msys64\clang64\bin\artiq_master.exe"

timeout /t 2 /nobreak >nul

start "ARTIQ Dashboard" /min cmd /K "cd /d E:\文档\Artiq-Rice && E:\msys64\clang64\bin\artiq_dashboard.exe -p ndscan.dashboard_plugin"

