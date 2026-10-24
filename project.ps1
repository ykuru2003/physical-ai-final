[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('Help','Start','Workshop','Stop','Status','Logs','Build','Validate','Shell','Test','TestExtension','Simulator','SimulatorStop','SimulatorStatus','SimulatorLogs','SimulatorShell','Check','Demo','RunStep2','Evaluate','Verify','Cases','Clean')]
    [string]$Action = 'Help',
    [ValidateSet('v3','v4','v5')]
    [string]$Driver = 'v5',
    [double]$GoalX = 3.0,
    [double]$GoalY = 1.0,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$script:RepositoryRoot = $PSScriptRoot

# Shared simulator paths and Compose options live here, not in another launcher.
function Get-GazeboRoot {
    return Join-Path $script:RepositoryRoot 'extensions/gazebo'
}

function Assert-GazeboIdle {
    $root = Get-GazeboRoot
    foreach ($name in @('step2-autotest.request','step2-autotest.running','navigation.lock')) {
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
            'Check' { Invoke-GazeboCompose exec -T simulator /ros_entrypoint.sh python3 /workspace/scripts/check_environment.py }
            'Demo' { Invoke-GazeboCompose exec -T simulator /ros_entrypoint.sh python3 /workspace/scripts/demo_drive.py }
            'Shell' { Invoke-GazeboCompose exec simulator /ros_entrypoint.sh bash }
            'Logs' { Invoke-GazeboCompose logs --tail 100 simulator }
        }
        if ($LASTEXITCODE -ne 0) { throw "Docker action failed: $Action" }
        if ($Action -eq 'Start') {
            $config = (Invoke-GazeboCompose config --format json | Out-String) | ConvertFrom-Json
            $port = ($config.services.simulator.ports | Where-Object target -eq 6080).published
            Write-Host "Gazebo: http://localhost:$port/vnc.html?autoconnect=true&resize=scale"
            Write-Host 'Wait for the desktop, then run: .\project.ps1 Check'
        }

    }
    finally { Pop-Location }
}

function Invoke-GazeboEvaluation {
    param([switch]$CheckOnly, [string]$Driver='v5', [double]$GoalX=3.0, [double]$GoalY=1.0)
    $projectRoot = Get-GazeboRoot
    $world = [xml](Get-Content -LiteralPath (Join-Path $projectRoot 'simulation/worlds/practice.sdf') -Raw)
    if ($null -eq $world.SelectSingleNode('/sdf/world/model[@name="practice_robot"]/plugin[@name="gz::sim::systems::PosePublisher"]')) { throw 'Ground-truth pose publisher is missing' }
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "scripts/drive_to_goal_$Driver.py"))) { throw "Driver file missing: $Driver" }
    if ($CheckOnly) { Write-Host "CHECK PASSED: world-position evaluation configured for $Driver. No simulation was started."; return }
    Assert-GazeboIdle
    $runId = $Driver+'-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,6)
    $outputDir = Join-Path $projectRoot "outputs/step2-evaluation/$runId"
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
    Push-Location $projectRoot
    try {
        Invoke-GazeboCompose up -d --no-build simulator
        if ($LASTEXITCODE -ne 0) { throw 'Cannot start simulator' }
        Invoke-GazeboCompose restart simulator
        if ($LASTEXITCODE -ne 0) { throw 'Cannot restart simulator' }
        Invoke-GazeboCompose exec -T simulator /ros_entrypoint.sh python3 -u /workspace/scripts/wait_step2_ready.py 2>&1 | Tee-Object -FilePath (Join-Path $outputDir 'readiness.log')
        if ($LASTEXITCODE -ne 0) { throw 'ROS topics not ready' }
        Invoke-GazeboCompose exec -T simulator /ros_entrypoint.sh python3 -u /workspace/scripts/evaluate_step2.py --driver $Driver --goal-x $GoalX --goal-y $GoalY --output-dir "/workspace/outputs/step2-evaluation/$runId" 2>&1 | Tee-Object -FilePath (Join-Path $outputDir 'evaluation.log')
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

function Invoke-GazeboDrive {
    $projectRoot = Get-GazeboRoot
    Assert-GazeboIdle
    Push-Location $projectRoot
    try {
        New-Item -ItemType Directory -Path outputs -Force | Out-Null
        Invoke-GazeboCompose up -d --no-build simulator
        if ($LASTEXITCODE -ne 0) { throw 'Cannot start existing simulator image' }
        Invoke-GazeboCompose restart simulator
        if ($LASTEXITCODE -ne 0) { throw 'Cannot restart simulator' }
        # Typed subscriptions wait even before Gazebo has advertised the topics.
        Invoke-GazeboCompose exec -T simulator /ros_entrypoint.sh python3 -u /workspace/scripts/wait_step2_ready.py 2>&1 | Tee-Object -FilePath outputs/step2-topic-readiness.log
        if ($LASTEXITCODE -ne 0) {
            Invoke-GazeboCompose ps 2>&1 | Tee-Object -FilePath outputs/step2-startup-diagnostics.log
            Invoke-GazeboCompose logs --tail 150 simulator 2>&1 | Tee-Object -FilePath outputs/step2-startup-diagnostics.log -Append
            throw 'ROS startup failed. See outputs/step2-topic-readiness.log and outputs/step2-startup-diagnostics.log'
        }
        Invoke-GazeboCompose exec -T simulator /ros_entrypoint.sh python3 -u /workspace/scripts/drive_to_goal_v3.py 2>&1 | Tee-Object -FilePath outputs/step2-run.log
        if ($LASTEXITCODE -ne 0) {
            $reason = Get-Content outputs/step2-run.log -Tail 1
            throw "STEP 2 failed: $reason (details: outputs/step2-run.log)"
        }
        Write-Host 'Goal reached. Inspect the Gazebo view and trajectory; goal success alone does not prove no contact.'
    } finally {
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
}

function Invoke-GazeboCases {
    param([switch]$CheckOnly)
    $projectRoot = Get-GazeboRoot
    $worldPath = Join-Path $projectRoot 'simulation/worlds/practice.sdf'
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
    Assert-GazeboIdle

    $session = Join-Path $projectRoot ('outputs/step2-cases/' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6))
    $previous = Join-Path $session 'previous'
    New-Item -ItemType Directory -Path $previous -Force | Out-Null
    [IO.File]::WriteAllBytes((Join-Path $session 'practice.before-tests.sdf'), $originalBytes)
    $artifacts = @('step2-run.log','step2-run.json','step2-topic-readiness.log','step2-readiness.json','step2-startup-diagnostics.log')
    $results = [System.Collections.Generic.List[object]]::new()
    $allPassed = $true
    $worldChanged = $false
    $cleanupError = $null
    Push-Location $projectRoot
    try {
        # Preserve the existing verified run; suite results live in their own folders.
        foreach ($name in $artifacts) {
            $source = Join-Path $projectRoot "outputs/$name"
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
                Invoke-GazeboDrive
                $run = Get-Content -LiteralPath (Join-Path $projectRoot 'outputs/step2-run.json') -Raw | ConvertFrom-Json
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
                    $source = Join-Path $projectRoot "outputs/$name"
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
                if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $projectRoot "outputs/$name") -Force }
            }
            if ($worldChanged) {
                Invoke-GazeboCompose restart simulator
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
}

function Invoke-OutputCleanup {
    param([switch]$CheckOnly)
    $arguments = @((Join-Path (Get-GazeboRoot) 'scripts/maintenance/archive_outputs.py'))
    if (-not $CheckOnly) { $arguments += '--apply' }
    & python @arguments
    if ($LASTEXITCODE -ne 0) { throw "Output cleanup failed (exit $LASTEXITCODE)." }
}

function Invoke-ExtensionTests {
    $root = Get-GazeboRoot
    Push-Location $root
    try {
        & python (Join-Path $root 'scripts/run_offline_checks.py')
        if ($LASTEXITCODE -ne 0) { throw "Offline checks failed (exit $LASTEXITCODE)." }
    } finally { Pop-Location }
    $shell = @('pwsh','pwsh.exe','powershell.exe') | ForEach-Object { Join-Path $PSHOME $_ } | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $shell) { throw 'Cannot locate PowerShell for isolated command tests.' }
    & $shell -NoProfile -File (Join-Path $script:RepositoryRoot 'tests/powershell/Test-Project.ps1')
    if ($LASTEXITCODE -ne 0) { throw "PowerShell checks failed (exit $LASTEXITCODE)." }
}

# Public command routing. These names are the only operational entry points.
if ($CheckOnly -and $Action -notin @('Evaluate','Cases','Clean')) {
    throw '-CheckOnly is supported only for Evaluate, Cases and Clean. No action was started.'
}
if ($Action -eq 'Help') {
    Write-Output @"
Physical AI workshop (PushT / LeRobot ACT):
  .\project.ps1 Start       Start/build the main JupyterLab workshop
  .\project.ps1 Workshop    Alias for Start
  .\project.ps1 Stop        Stop the workshop
  .\project.ps1 Status      Show workshop status
  .\project.ps1 Logs        Show workshop logs
  .\project.ps1 Shell       Open a shell in the workshop
  .\project.ps1 Build       Build the workshop image
  .\project.ps1 Validate    Validate workshop and extension Compose files
  .\project.ps1 Test        Run workshop pytest (prepare the dataset first)

Optional Gazebo extension:
  .\project.ps1 Simulator   Start/build Gazebo separately
  .\project.ps1 SimulatorStop / SimulatorStatus / SimulatorLogs / SimulatorShell
  .\project.ps1 TestExtension   Run offline Python and unified PowerShell checks
  .\project.ps1 Verify          Run real local AI and simulated navigation
  .\project.ps1 Evaluate -GoalX 3 -GoalY 1 -Driver v5
  .\project.ps1 Cases -CheckOnly
  .\project.ps1 Clean -CheckOnly
Other extension actions: Check, Demo, RunStep2. These move the simulated robot.
Verify/Evaluate restart the simulator. The ACT-to-Gazebo adapter is not implemented.
"@
    return
}
switch ($Action) {
    'Simulator' { Invoke-GazeboManagement -Action Start; return }
    'SimulatorStop' { Invoke-GazeboManagement -Action Stop; return }
    'SimulatorStatus' { Invoke-GazeboManagement -Action Status; return }
    'SimulatorLogs' { Invoke-GazeboManagement -Action Logs; return }
    'SimulatorShell' { Invoke-GazeboManagement -Action Shell; return }
    'Check' { Invoke-GazeboManagement -Action Check; return }
    'Demo' { Invoke-GazeboManagement -Action Demo; return }
    'RunStep2' { Invoke-GazeboDrive; return }
    'Evaluate' { Invoke-GazeboEvaluation -Driver $Driver -GoalX $GoalX -GoalY $GoalY -CheckOnly:$CheckOnly; return }
    'Verify' { Invoke-GazeboVerification; return }
    'Cases' { Invoke-GazeboCases -CheckOnly:$CheckOnly; return }
    'Clean' { Invoke-OutputCleanup -CheckOnly:$CheckOnly; return }
    'TestExtension' { Invoke-ExtensionTests; return }
}
Push-Location $PSScriptRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker Desktop is required for the workshop.'
    }
    switch ($Action) {
        { $_ -in @('Start','Workshop') } {
            & docker compose up -d --build workshop
        }
        'Stop' { & docker compose down }
        'Status' { & docker compose ps }
        'Logs' { & docker compose logs --tail 100 workshop }
        'Build' { & docker compose build workshop }
        'Shell' { & docker compose exec workshop bash }
        'Test' { & docker compose run --rm workshop pytest -q }
        'Validate' { & docker compose config --quiet }
    }
    if ($LASTEXITCODE -ne 0) { throw "Workshop action failed: $Action (exit $LASTEXITCODE)." }
    if ($Action -eq 'Validate') { Invoke-GazeboManagement -Action Validate }
    if ($Action -in @('Start','Workshop')) {
        $config = (& docker compose config --format json | Out-String) | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0) { throw 'Cannot read the workshop Compose configuration.' }
        $port = ($config.services.workshop.ports | Where-Object target -eq 8888).published
        Write-Host "JupyterLab: http://localhost:$port/lab?token=roboops-workshop"
    }
} finally {
    Pop-Location
}
