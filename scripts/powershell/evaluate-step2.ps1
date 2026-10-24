[CmdletBinding()]
param([switch]$CheckOnly, [ValidateSet('v3','v4','v5')][string]$Driver = 'v3', [double]$GoalX = 3.0, [double]$GoalY = 1.0)
. (Join-Path $PSScriptRoot 'Project.Common.ps1')
$projectRoot = Get-PhysicalAiProjectRoot
$world = [xml](Get-Content -LiteralPath (Join-Path $projectRoot 'simulation/worlds/practice.sdf') -Raw)
if ($null -eq $world.SelectSingleNode('/sdf/world/model[@name="practice_robot"]/plugin[@name="gz::sim::systems::PosePublisher"]')) { throw 'Ground-truth pose publisher is missing' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "scripts/drive_to_goal_$Driver.py"))) { throw "Driver file missing: $Driver" }
if ($CheckOnly) { Write-Host "CHECK PASSED: world-position evaluation configured for $Driver. No simulation was started."; return }
Assert-PhysicalAiIdle
$runId = $Driver+'-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,6)
$outputDir = Join-Path $projectRoot "outputs/step2-evaluation/$runId"
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
Push-Location $projectRoot
try {
    docker compose up -d --no-build simulator
    if ($LASTEXITCODE -ne 0) { throw 'Cannot start simulator' }
    docker compose restart simulator
    if ($LASTEXITCODE -ne 0) { throw 'Cannot restart simulator' }
    docker compose exec -T simulator /ros_entrypoint.sh python3 -u /workspace/scripts/wait_step2_ready.py 2>&1 | Tee-Object -FilePath (Join-Path $outputDir 'readiness.log')
    if ($LASTEXITCODE -ne 0) { throw 'ROS topics not ready' }
    docker compose exec -T simulator /ros_entrypoint.sh python3 -u /workspace/scripts/evaluate_step2.py --driver $Driver --goal-x $GoalX --goal-y $GoalY --output-dir "/workspace/outputs/step2-evaluation/$runId" 2>&1 | Tee-Object -FilePath (Join-Path $outputDir 'evaluation.log')
    $evaluationExit = $LASTEXITCODE
    if ($evaluationExit -eq 2) {
        Write-Warning 'Measurement finished: the world-position goal or contact criteria were not met. This is an evaluation result, not a PowerShell error.'
    } elseif ($evaluationExit -ne 0) {
        throw 'World evaluation could not complete; inspect evaluation.log and evaluation.json'
    }
} finally {
    Write-Host "Results: $outputDir"
    Pop-Location
}


