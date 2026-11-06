#requires -Version 5.1
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

$python = $null
foreach ($candidate in @("python", "python3", "py")) {
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($command) {
        try {
            $version = & $command.Source --version 2>&1
            if ($version -match "3\.(1[1-4])") { $python = $command.Source; break }
        } catch { }
    }
}
if (-not $python) {
    throw "未找到 Python 3.11+。请先安装 Python 3.12，并确保 python 在 PATH 中。"
}

Write-Host "使用 Python: $python"
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "创建虚拟环境 .venv ..."
    & $python -m venv .venv
}

Write-Host "安装依赖（首次约 1-2 分钟，取决于网络）..."
& .venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host ""
Write-Host "安装完成。运行："
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\run.ps1"
