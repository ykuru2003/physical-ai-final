[CmdletBinding()]
param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$worldPath = Join-Path $PSScriptRoot 'simulation/worlds/practice.sdf'
$originalBytes = [IO.File]::ReadAllBytes($worldPath)
$originalText = [IO.File]::ReadAllText($worldPath)
$cases = @(
    [pscustomobject]@{ Name = '01-current'; Pose = '1.5 0.5 0.4 0 0 0' },
    [pscustomobject]@{ Name = '02-center'; Pose = '1.5 0 0.4 0 0 0' },
    [pscustomobject]@{ Name = '03-goal-side'; Pose = '1.8 0.9 0.4 0 0 0' }
)
$pattern = '(<model\s+name="obstacle"\s*>[\s\S]*?<pose>)[^<]*(</pose>)'
$regex = [regex]::new($pattern)
if ($regex.Matches($originalText).Count -ne 1) { throw 'Expected exactly one obstacle pose; no files changed.' }
foreach ($case in $cases) {
    $candidate = $regex.Replace($originalText, { param($m) $m.Groups[1].Value + $case.Pose + $m.Groups[2].Value })
    $parsed = [xml]$candidate
    if ($parsed.SelectNodes('/sdf/world/model[@name="obstacle"]').Count -ne 1) { throw 'Invalid case world' }
    Write-Host ($case.Name + ': obstacle pose = ' + $case.Pose)
}
if ($CheckOnly) { Write-Host 'CHECK PASSED: 3 valid worlds; no Docker commands or file changes.'; return }
foreach ($name in @('step2-autotest.request', 'step2-autotest.running')) {
    if (Test-Path -LiteralPath (Join-Path $PSScriptRoot "outputs/$name")) { throw "Another automatic test is pending/running: $name" }
}

$session = Join-Path $PSScriptRoot ('outputs/step2-cases/' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6))
$previous = Join-Path $session 'previous'
New-Item -ItemType Directory -Path $previous -Force | Out-Null
[IO.File]::WriteAllBytes((Join-Path $session 'practice.before-tests.sdf'), $originalBytes)
$artifacts = @('step2-run.log','step2-run.json','step2-topic-readiness.log','step2-readiness.json','step2-startup-diagnostics.log')
$results = [System.Collections.Generic.List[object]]::new()
$allPassed = $true
$worldChanged = $false
$cleanupError = $null
Push-Location $PSScriptRoot
try {
    # Preserve the existing verified run; suite results live in their own folders.
    foreach ($name in $artifacts) {
        $source = Join-Path $PSScriptRoot "outputs/$name"
        if (Test-Path -LiteralPath $source) { Move-Item -LiteralPath $source -Destination (Join-Path $previous $name) }
    }
    foreach ($case in $cases) {
        $caseDir = Join-Path $session $case.Name
        New-Item -ItemType Directory -Path $caseDir | Out-Null
        $record = [ordered]@{ name=$case.Name; obstacle_pose=$case.Pose; status='FAIL'; reason=$null }
        try {
            $candidate = $regex.Replace($originalText, { param($m) $m.Groups[1].Value + $case.Pose + $m.Groups[2].Value })
            $worldChanged = $true
            [IO.File]::WriteAllText($worldPath, $candidate, [Text.UTF8Encoding]::new($false))
            [IO.File]::WriteAllText((Join-Path $caseDir 'practice.sdf'), $candidate, [Text.UTF8Encoding]::new($false))
            Write-Host "RUNNING $($case.Name)"
            & (Join-Path $PSScriptRoot 'run-step2.ps1')
            $run = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'outputs/step2-run.json') -Raw | ConvertFrom-Json
            if ($run.result -ne 'GOAL REACHED!') { throw "Driver result: $($run.result)" }
            if (@($run.obstacle_collisions).Count -ne 0) { throw 'Obstacle collision detected' }
            $record.final_odometry = $run.final_pose
            $record.support_contact_count = $run.support_contact_count
            $record.min_lidar_clearance_m = ($run.trace | Measure-Object -Property clearance -Minimum).Minimum
            if ($null -eq $run.support_contact_count -or $run.support_contact_count -le 0) {
                throw 'Goal reached, but contact-monitor operation was not confirmed'
            }
            $record.status = 'PASS'
        } catch {
            $record.reason = $_.Exception.Message
            $allPassed = $false
            Write-Warning "$($case.Name): $($record.reason)"
        } finally {
            foreach ($name in $artifacts) {
                $source = Join-Path $PSScriptRoot "outputs/$name"
                if (Test-Path -LiteralPath $source) { Move-Item -LiteralPath $source -Destination (Join-Path $caseDir $name) }
            }
            $results.Add([pscustomobject]$record)
            $record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $caseDir 'result.json') -Encoding utf8
        }
    }
} finally {
    # Restore exact bytes, including encoding and line endings, even on failure.
    try {
        [IO.File]::WriteAllBytes($worldPath, $originalBytes)
        foreach ($name in $artifacts) {
            $source = Join-Path $previous $name
            if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $PSScriptRoot "outputs/$name") -Force }
        }
        if ($worldChanged) {
            docker compose restart simulator
            if ($LASTEXITCODE -ne 0) { throw 'World file restored, but restarting the simulator failed.' }
        }
    } catch {
        $cleanupError = $_.Exception.Message
        $allPassed = $false
        Write-Warning $cleanupError
    }
    $summary = [ordered]@{ result=$(if ($allPassed -and $results.Count -eq $cases.Count) {'PASS'} else {'FAIL'}); cases=@($results.ToArray()); cleanup_error=$cleanupError; original_world_backup=(Join-Path $session 'practice.before-tests.sdf'); results_directory=$session }
    $summary | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $session 'summary.json') -Encoding utf8
    Write-Host "Results: $session"
    Pop-Location
}
if ($summary.result -ne 'PASS') { throw "Some cases failed or were incomplete. See $session\summary.json" }
Write-Host 'PASS: All 3 cases reached the goal with contact monitoring confirmed; original world restored.'
