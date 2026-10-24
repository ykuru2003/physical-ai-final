# Run from PowerShell; only this project's simulator is restarted.
. (Join-Path $PSScriptRoot 'Project.Common.ps1')
$projectRoot = Get-PhysicalAiProjectRoot
Assert-PhysicalAiIdle
Push-Location $projectRoot
try {
    New-Item -ItemType Directory -Path outputs -Force | Out-Null
    docker compose up -d --no-build simulator
    if ($LASTEXITCODE -ne 0) { throw 'Cannot start existing simulator image' }
    docker compose restart simulator
    if ($LASTEXITCODE -ne 0) { throw 'Cannot restart simulator' }
    # Typed subscriptions wait even before Gazebo has advertised the topics.
    docker compose exec -T simulator /ros_entrypoint.sh python3 -u /workspace/scripts/wait_step2_ready.py 2>&1 | Tee-Object -FilePath outputs/step2-topic-readiness.log
    if ($LASTEXITCODE -ne 0) {
        docker compose ps 2>&1 | Tee-Object -FilePath outputs/step2-startup-diagnostics.log
        docker compose logs --tail 150 simulator 2>&1 | Tee-Object -FilePath outputs/step2-startup-diagnostics.log -Append
        throw 'ROS startup failed. See outputs/step2-topic-readiness.log and outputs/step2-startup-diagnostics.log'
    }
    docker compose exec -T simulator /ros_entrypoint.sh python3 -u /workspace/scripts/drive_to_goal_v3.py 2>&1 | Tee-Object -FilePath outputs/step2-run.log
    if ($LASTEXITCODE -ne 0) {
        $reason = Get-Content outputs/step2-run.log -Tail 1
        throw "STEP 2 failed: $reason (details: outputs/step2-run.log)"
    }
    Write-Host 'Goal reached. Inspect the Gazebo view and trajectory; goal success alone does not prove no contact.'
} finally {
    Pop-Location
}
