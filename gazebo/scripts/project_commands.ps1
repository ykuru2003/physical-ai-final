# Host command implementations. Dot-sourced by the root project.ps1.
# Shared simulator paths and Compose options live here, not in another launcher.
function Get-GazeboRoot {
    return Join-Path $script:RepositoryRoot 'gazebo'
}

function Assert-GazeboIdle {
    $root = Get-GazeboRoot
    foreach ($name in @('navigation.lock')) {
        if (Test-Path -LiteralPath (Join-Path $root "outputs/$name")) {
            throw "Navigation or automatic test pending/running: $name"
        }
    }
}

function Invoke-GazeboCompose {
    $arguments = @($args)
    $root = Get-GazeboRoot
    $options = @('--file', (Join-Path $root 'compose.yaml'))
    $environmentFile = Join-Path $script:RepositoryRoot '.env'
    if (Test-Path -LiteralPath $environmentFile -PathType Leaf) {
        $options += @('--env-file', $environmentFile)
    }
    Push-Location $root
    try { & docker compose @options @arguments } finally { Pop-Location }
}

function Invoke-GazeboManagement {
    param([string]$Action)
    $projectRoot = Get-GazeboRoot
    Push-Location $projectRoot
    try {
        if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
            throw 'Docker Desktop is required. Install it and enable Linux containers.'
        }
        Invoke-GazeboCompose config --quiet
        if ($LASTEXITCODE -ne 0) { throw 'Invalid Docker Compose configuration.' }
        if ($Action -eq 'Validate') { Write-Host 'Compose configuration: PASS'; return }

        $engine = & docker info --format '{{.OSType}}' 2>$null
        if ($LASTEXITCODE -ne 0 -or $engine -ne 'linux') {
            throw 'Start Docker Desktop, wait until Engine running, and use Linux containers. Then retry.'
        }
        switch ($Action) {
            'Start' { Invoke-GazeboCompose up -d --build simulator }
            'Stop' { Invoke-GazeboCompose down }
            'Status' { Invoke-GazeboCompose ps }
            'Build' { Invoke-GazeboCompose build simulator }
            'Shell' { Invoke-GazeboCompose exec simulator /ros_entrypoint.sh bash }
            'Logs' { Invoke-GazeboCompose logs --tail 100 simulator }
        }
        if ($LASTEXITCODE -ne 0) { throw "Docker action failed: $Action" }
        if ($Action -eq 'Start') {
            $config = (Invoke-GazeboCompose config --format json | Out-String) | ConvertFrom-Json
            $port = ($config.services.simulator.ports | Where-Object target -eq 6080).published
            Write-Host "Gazebo: http://localhost:$port/vnc.html?autoconnect=true&resize=scale"
            Write-Host 'Wait for the desktop, then run: .\project.ps1 SubmissionCheck'
        }

    }
    finally { Pop-Location }
}

function Restart-GazeboSimulation {
    param([string]$ReadinessLog, [string]$DiagnosticsLog = '')
    Invoke-GazeboCompose up -d --no-build simulator
    if ($LASTEXITCODE -ne 0) { throw 'Cannot start existing simulator image' }
    Invoke-GazeboCompose restart simulator
    if ($LASTEXITCODE -ne 0) { throw 'Cannot restart simulator' }
    Invoke-GazeboCompose exec -T simulator /ros_entrypoint.sh python3 -u /workspace/scripts/wait_for_sensors.py 2>&1 | Tee-Object -FilePath $ReadinessLog
    if ($LASTEXITCODE -ne 0) {
        if ($DiagnosticsLog) {
            Invoke-GazeboCompose ps 2>&1 | Tee-Object -FilePath $DiagnosticsLog
            Invoke-GazeboCompose logs --tail 150 simulator 2>&1 | Tee-Object -FilePath $DiagnosticsLog -Append
            throw "ROS startup failed. See $ReadinessLog and $DiagnosticsLog"
        }
        throw "ROS topics not ready. See $ReadinessLog"
    }
}

function Invoke-GazeboEvaluation {
    param([switch]$CheckOnly, [double]$GoalX=3.0, [double]$GoalY=1.0)
    $projectRoot = Get-GazeboRoot
    $world = [xml](Get-Content -LiteralPath (Join-Path $projectRoot 'simulation/worlds/practice.sdf') -Raw)
    if ($null -eq $world.SelectSingleNode('/sdf/world/model[@name="practice_robot"]/plugin[@name="gz::sim::systems::PosePublisher"]')) { throw 'Ground-truth pose publisher is missing' }
    $driverScript = 'scripts/navigate_to_goal.py'
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $driverScript))) { throw "Navigation controller file missing: $driverScript" }
    if ($CheckOnly) { Write-Host "CHECK PASSED: world-position evaluation configured for navigation. No simulation was started."; return }
    Assert-GazeboIdle
    $runId = 'navigation-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,6)
    $outputDir = Join-Path $projectRoot "outputs/world-evaluation/$runId"
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
    Push-Location $projectRoot
    try {
        Restart-GazeboSimulation -ReadinessLog (Join-Path $outputDir 'readiness.log')
        Invoke-GazeboCompose exec -T simulator /ros_entrypoint.sh python3 -u /workspace/scripts/evaluate_navigation.py --goal-x $GoalX --goal-y $GoalY --output-dir "/workspace/outputs/world-evaluation/$runId" 2>&1 | Tee-Object -FilePath (Join-Path $outputDir 'evaluation.log')
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
}

function Invoke-GazeboVerification {
    $projectRoot = Get-GazeboRoot
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding
    $env:PYTHONUTF8 = '1'
    $runId = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6)
    $logDir = Join-Path $projectRoot 'outputs'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $logPath = Join-Path $logDir "navigation-verification-$runId.log"
    $latestLog = Join-Path $logDir 'navigation-verification.log'
    Push-Location $projectRoot
    try {
        if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) { throw 'Python 3.12+ is required; check -Python or PHYSICAL_AI_PYTHON.' }
        Write-Host 'Using the configured installed local model. Valid driving and AI evidence will be reused.'
        $ErrorActionPreference = 'Continue'
        $verifyArguments = @('-u','scripts/verify_navigation.py')
        if ($Model) { $verifyArguments += @('--model',$Model) }
        & $Python @verifyArguments 2>&1 | Tee-Object -FilePath $logPath
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
}

function Invoke-OutputCleanup {
    param([switch]$CheckOnly)
    $arguments = @((Join-Path (Get-GazeboRoot) 'scripts/archive_outputs.py'))
    if (-not $CheckOnly) { $arguments += '--apply' }
    & $Python @arguments
    if ($LASTEXITCODE -ne 0) { throw "Output cleanup failed (exit $LASTEXITCODE)." }
}

function Invoke-OfflineTests {
    $root = Get-GazeboRoot
    Push-Location $root
    try {
        & $Python (Join-Path $root 'scripts/run_offline_checks.py')
        if ($LASTEXITCODE -ne 0) { throw "Offline checks failed (exit $LASTEXITCODE)." }
    } finally { Pop-Location }
    & $Python (Join-Path $script:RepositoryRoot 'tests/test_layout.py')
    if ($LASTEXITCODE -ne 0) { throw 'Repository layout checks failed.' }
    $shell = @('pwsh','pwsh.exe','powershell.exe') | ForEach-Object { Join-Path $PSHOME $_ } | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $shell) { throw 'Cannot locate PowerShell for isolated command tests.' }
    & $shell -NoProfile -File (Join-Path $script:RepositoryRoot 'tests/Test-Project.ps1')
    if ($LASTEXITCODE -ne 0) { throw "PowerShell checks failed (exit $LASTEXITCODE)." }
}

function Invoke-TaskScript {
    param([string]$Script, [string[]]$ScriptArguments = @())
    $arguments = @('-u', (Join-Path (Get-GazeboRoot) "scripts/$Script")) + $ScriptArguments
    if ($Model) { $arguments += @('--model',$Model) }
    & $Python @arguments
    if ($LASTEXITCODE -ne 0) { throw "$Script failed (exit $LASTEXITCODE). See the printed evidence directory." }
}

