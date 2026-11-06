#requires -Version 5.1
param([switch]$Force)
$ErrorActionPreference = "Stop"
$runtime = if ($env:RT_RUNTIME) { $env:RT_RUNTIME } else { Join-Path $HOME "ResearchThread" }
$resolved = [System.IO.Path]::GetFullPath($runtime)
$leaf = Split-Path $resolved -Leaf
if ($leaf -notin @("ResearchThread", "runtime")) {
    throw "拒绝删除非预期目录：$resolved（目录名应为 ResearchThread 或 runtime）"
}
Write-Host "将删除运行时数据：$resolved"
Write-Host "这会清空 seekdb 文献/证据、PowerContext 记忆和本地 scope；代码与示例数据不受影响。"
if (-not $Force) {
    $answer = Read-Host "输入 DELETE 继续"
    if ($answer -ne "DELETE") { Write-Host "已取消"; exit 0 }
}
if (Test-Path $resolved) {
    Remove-Item -Recurse -Force $resolved
    Write-Host "已删除。下次启动会重新播种示例数据。"
} else {
    Write-Host "目录不存在，无需清理。"
}
