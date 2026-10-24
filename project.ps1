[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('Help', 'Start', 'Stop', 'Status', 'Check', 'Demo', 'Workshop', 'Shell', 'Logs', 'Build', 'Validate', 'RunStep2', 'Evaluate', 'Verify', 'Cases', 'Test')]
    [string]$Action = 'Help',
    [ValidateSet('v3', 'v4', 'v5')]
    [string]$Driver = 'v5',
    [double]$GoalX = 3.0,
    [double]$GoalY = 1.0,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$commands = Join-Path $PSScriptRoot 'scripts/powershell'
if ($CheckOnly -and $Action -notin @('Evaluate', 'Cases')) {
    throw '-CheckOnly is supported only for Evaluate and Cases. No action was started.'
}
switch ($Action) {
    'Help' {
        Write-Output @"
Physical AI project commands (run from this project folder):
  .\project.ps1 Start       Start/build the simulator
  .\project.ps1 Status      Show simulator/workshop status
  .\project.ps1 Logs        Show recent simulator logs
  .\project.ps1 Stop        Stop simulator/workshop containers
  .\project.ps1 Verify      Verify real AI and language-to-navigation
  .\project.ps1 Test        Run Python and PowerShell offline checks (no robot movement)
  .\project.ps1 Evaluate -GoalX 3 -GoalY 1 -Driver v5
  .\project.ps1 Evaluate -CheckOnly
  .\project.ps1 Cases -CheckOnly

Other actions: Check, Demo, Workshop, Shell, Build, Validate, RunStep2.
Check, Demo and RunStep2 move the simulated robot.
Verify/Evaluate restart the simulator and reset its position.
Cases temporarily changes obstacle positions and restores them afterwards.
PowerShell implementations: scripts/powershell/.
"@
    }
    'Verify' { & (Join-Path $commands 'verify-step3.ps1') }
    'Evaluate' { & (Join-Path $commands 'evaluate-step2.ps1') -Driver $Driver -GoalX $GoalX -GoalY $GoalY -CheckOnly:$CheckOnly }
    'Cases' { & (Join-Path $commands 'test-step2-cases.ps1') -CheckOnly:$CheckOnly }
    'RunStep2' { & (Join-Path $commands 'run-step2.ps1') }
    'Test' {
        & python (Join-Path $PSScriptRoot 'scripts/run_offline_checks.py')
        if ($LASTEXITCODE -ne 0) { throw "Offline checks failed (exit $LASTEXITCODE)." }
        $powerShell = @('pwsh', 'pwsh.exe', 'powershell.exe') | ForEach-Object { Join-Path $PSHOME $_ } | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
        if (-not $powerShell) { throw 'Cannot locate the current PowerShell installation for isolated tests.' }
        & $powerShell -NoProfile -File (Join-Path $commands 'tests/Test-ProjectScripts.ps1')
        if ($LASTEXITCODE -ne 0) { throw "PowerShell checks failed (exit $LASTEXITCODE)." }
    }
    default { & (Join-Path $commands 'manage.ps1') -Action $Action }
}
