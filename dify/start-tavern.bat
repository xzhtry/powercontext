@echo off
chcp 65001 >nul
echo 正在启动记仇客栈...
wsl.exe -d Ubuntu-24.04 -- bash "/mnt/d/oceanbase大赛/pc-eco/dify/scripts/start_all.sh"
echo.
echo 如果上面的服务都就绪，浏览器会自动打开。
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8790"
pause
