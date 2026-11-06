#requires -Version 5.1
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "尚未安装依赖。先运行：powershell -ExecutionPolicy Bypass -File scripts\setup.ps1"
}

if (-not $env:RT_RUNTIME) {
    $env:RT_RUNTIME = Join-Path $HOME "ResearchThread"
}
if (-not $env:RT_PORT) { $env:RT_PORT = "8787" }
if (-not $env:RT_SEEKDB_PORT) { $env:RT_SEEKDB_PORT = "18881" }
if (-not $env:RT_PC_PORT) { $env:RT_PC_PORT = "18765" }

Write-Host "研脉 ResearchThread"
Write-Host "  runtime:       $env:RT_RUNTIME"
Write-Host "  web:           http://127.0.0.1:$env:RT_PORT"
Write-Host "  seekdb port:   $env:RT_SEEKDB_PORT"
Write-Host "  PowerContext:  http://127.0.0.1:$env:RT_PC_PORT"
Write-Host ""
Write-Host "首次启动会初始化 seekdb（约 2G 稀疏数据文件）和 508 篇示例文献，请稍候。"
Write-Host "按 Ctrl+C 停止；seekdb / PowerContext 由本进程管理。"
Write-Host ""

& .venv\Scripts\python.exe -m app
