[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'Project.Common.ps1')
$projectRoot = Get-PhysicalAiProjectRoot
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding
$env:PYTHONUTF8 = '1'
$runId = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6)
$logDir = Join-Path $projectRoot 'outputs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logPath = Join-Path $logDir "step3-full-check-$runId.log"
$latestLog = Join-Path $logDir 'step3-full-check.log'
Push-Location $projectRoot
try {
    try {
        $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3
    } catch {
        throw 'Ollama is unavailable. In another PowerShell run: ollama serve. Keep that window open, then retry this script.'
    }
    Write-Host 'Using installed qwen3:1.7b. Valid driving and AI evidence will be reused.'
    $ErrorActionPreference = 'Continue'
    python -u scripts/complete_step3.py --model qwen3:1.7b 2>&1 | Tee-Object -FilePath $logPath
    $result = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($result -ne 0) { throw "Runtime checks did not pass (exit $result). Results: $logPath" }
    Write-Host 'All runtime checks passed.'
} catch {
    $errorText = $_.Exception.Message
    Add-Content -LiteralPath $logPath -Value "VERIFICATION INCOMPLETE: $errorText" -Encoding UTF8
    Write-Host "VERIFICATION INCOMPLETE: $errorText"
    throw $errorText
} finally {
    if (Test-Path -LiteralPath $logPath) { Copy-Item -LiteralPath $logPath -Destination $latestLog -Force }
    Write-Host "Log: $latestLog"
    Pop-Location
}
