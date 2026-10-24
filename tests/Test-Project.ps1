# One PowerShell suite for workshop and simulator commands. All services are mocked.
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$cacheRoot = [IO.Path]::GetFullPath((Join-Path $root '.cache/test-runs'))
if ($env:PHYSICAL_AI_TEST_SCRIPT -ne $PSCommandPath) {
    $runner = Join-Path $root 'tests/run_powershell.py'
    $python = (Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $shell = @('pwsh', 'pwsh.exe', 'powershell.exe') | ForEach-Object { Join-Path $PSHOME $_ } | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $shell) { throw 'Cannot locate PowerShell for the isolated test process.' }
    & $python $runner $PSCommandPath --shell $shell --cache-root $cacheRoot
    exit $LASTEXITCODE
}
$repositoryFixtureRoot = [IO.Path]::GetFullPath($env:PHYSICAL_AI_TEST_FIXTURE)
$global:PhysicalAiTestFixtureRoot = Join-Path $repositoryFixtureRoot 'extensions/gazebo'
$cacheBoundary = $cacheRoot + [IO.Path]::DirectorySeparatorChar
if (-not $global:PhysicalAiTestFixtureRoot.StartsWith($cacheBoundary, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Test fixture must stay inside the test cache.'
}
New-Item -ItemType Directory -Path (Join-Path $global:PhysicalAiTestFixtureRoot 'scripts') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'project.ps1') -Destination $repositoryFixtureRoot
$worldDir = Join-Path $global:PhysicalAiTestFixtureRoot 'simulation/worlds'
New-Item -ItemType Directory -Path $worldDir -Force | Out-Null
$worldPath = Join-Path $worldDir 'practice.sdf'
Copy-Item -LiteralPath (Join-Path $root 'extensions/gazebo/simulation/worlds/practice.sdf') -Destination $worldPath
foreach ($version in @('v3','v4','v5')) {
    Set-Content -LiteralPath (Join-Path $global:PhysicalAiTestFixtureRoot "scripts/drive_to_goal_$version.py") -Value '# fixture only'
}
New-Item -ItemType Directory -Path (Join-Path $global:PhysicalAiTestFixtureRoot 'outputs') -Force | Out-Null
$global:PhysicalAiTestDockerCalls = [System.Collections.Generic.List[object]]::new()
$global:PhysicalAiTestPythonCalls = [System.Collections.Generic.List[object]]::new()
$global:PhysicalAiTestPythonExit = 0
$global:PhysicalAiTestDockerExit = 0
$global:PhysicalAiTestFailReadiness = $false
$global:PhysicalAiTestTestsPassed = 0

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Assert-Fails([scriptblock]$Operation, [string]$Pattern) {
    try { & $Operation | Out-Null } catch {
        Assert-True ($_.Exception.Message -match $Pattern) "Unexpected error: $($_.Exception.Message)"
        return
    }
    throw 'Expected the action to fail, but it succeeded.'
}
function Test-Case([string]$Name, [scriptblock]$Action) {
    & $Action
    $global:PhysicalAiTestTestsPassed++
    Write-Host "PASS: $Name"
}
function global:docker {
    $arguments = @($args)
    $global:PhysicalAiTestDockerCalls.Add([pscustomobject]@{ Arguments=$arguments; Directory=(Get-Location).Path })
    $global:LASTEXITCODE = $global:PhysicalAiTestDockerExit
    $command = $arguments -join ' '
    if ($command -eq 'info --format {{.OSType}}') { Write-Output 'linux'; return }
    if ($command -match 'config --format json') {
        Write-Output '{"services":{"simulator":{"ports":[{"target":6080,"published":6080}]},"workshop":{"ports":[{"target":8888,"published":8888}]}}}'
        return
    }
    if ($global:PhysicalAiTestFailReadiness -and $command -match 'wait_step2_ready.py') {
        Write-Output 'Mock readiness failure'
        $global:LASTEXITCODE = 1
        return
    }
    if ($command -match 'drive_to_goal_v3.py') {
        $report = @{ result='GOAL REACHED!'; obstacle_collisions=@(); final_pose=@(3,1,0); support_contact_count=20; trace=@(@{clearance=0.5}) }
        $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $global:PhysicalAiTestFixtureRoot 'outputs/step2-run.json') -Encoding UTF8
    }
}
function global:python {
    $global:PhysicalAiTestPythonCalls.Add([pscustomobject]@{ Arguments=@($args); Directory=(Get-Location).Path })
    $global:LASTEXITCODE = $global:PhysicalAiTestPythonExit
    Write-Output "Mock Python exit $global:PhysicalAiTestPythonExit"
}
function global:Invoke-RestMethod { return @{ models=@() } }

$launcher = Join-Path $repositoryFixtureRoot 'project.ps1'
$originalDirectory = (Get-Location).Path
Push-Location $PSScriptRoot
try {
    Test-Case 'All project PowerShell sources parse' {
        $sources = @(Get-Item -LiteralPath (Join-Path $root 'project.ps1'), $PSCommandPath)
        foreach ($source in $sources) {
            $tokens = $null; $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($source.FullName, [ref]$tokens, [ref]$errors) | Out-Null
            Assert-True ($errors.Count -eq 0) "PowerShell syntax error: $($source.FullName)"
        }
    }
    Test-Case 'Help does not contact services' {
        $global:PhysicalAiTestDockerCalls.Clear(); $global:PhysicalAiTestPythonCalls.Clear()
        $help = & $launcher Help | Out-String
        Assert-True ($help -match 'Verify' -and $help -match 'Test' -and $help -match 'JupyterLab') 'Help omitted primary commands.'
        Assert-True ($global:PhysicalAiTestDockerCalls.Count -eq 0 -and $global:PhysicalAiTestPythonCalls.Count -eq 0) 'Help started a service.'
    }
    Test-Case 'Evaluate forwards parameters from an unrelated working directory' {
        $before = (Get-FileHash -LiteralPath $worldPath).Hash
        $output = & $launcher Evaluate -Driver v5 -GoalX 1 -GoalY -1 -CheckOnly 6>&1 | Out-String
        Assert-True ($output -match 'configured for v5') 'Driver parameter was not forwarded.'
        Assert-True ((Get-FileHash -LiteralPath $worldPath).Hash -eq $before) 'CheckOnly changed the world.'
        Assert-True ($global:PhysicalAiTestDockerCalls.Count -eq 0) 'CheckOnly called Docker.'
    }
    Test-Case 'Case CheckOnly validates geometry without moving files or calling services' {
        $before = (Get-FileHash -LiteralPath $worldPath).Hash
        & $launcher Cases -CheckOnly | Out-Null
        Assert-True ((Get-FileHash -LiteralPath $worldPath).Hash -eq $before) 'Case CheckOnly changed the world.'
        Assert-True ($global:PhysicalAiTestDockerCalls.Count -eq 0) 'Case CheckOnly called Docker.'
    }
    Test-Case 'Unsupported CheckOnly cannot start navigation' {
        Assert-Fails { & $launcher Verify -CheckOnly } 'supported only'
        Assert-True ($global:PhysicalAiTestPythonCalls.Count -eq 0) 'Unsupported CheckOnly launched Python.'
    }
    Test-Case 'Navigation lock stops evaluate, cases and legacy runs before Docker' {
        $lock = Join-Path $global:PhysicalAiTestFixtureRoot 'outputs/navigation.lock'
        Set-Content -LiteralPath $lock -Value 'test fixture'
        try {
            foreach ($action in @('Evaluate','Cases','RunStep2')) {
                Assert-Fails { & $launcher $action } 'navigation.lock'
            }
            Assert-True ($global:PhysicalAiTestDockerCalls.Count -eq 0) 'Locked navigation called Docker.'
        } finally { Remove-Item -LiteralPath $lock }
    }
    Test-Case 'Management commands use the compose project directory and restore location' {
        $before = (Get-Location).Path
        & $launcher Validate | Out-Null
        Assert-True ($global:PhysicalAiTestDockerCalls[-1].Directory -eq $global:PhysicalAiTestFixtureRoot) 'Compose used the caller directory.'
        Assert-True ((Get-Location).Path -eq $before) 'Management command leaked its working directory.'
    }
    Test-Case 'Evaluate forwards goal coordinates and executes in the project directory' {
        & $launcher Evaluate -Driver v5 -GoalX 1 -GoalY -1 | Out-Null
        $call = $global:PhysicalAiTestDockerCalls[-1]
        $command = $call.Arguments -join ' '
        Assert-True ($command -match '--driver v5 --goal-x 1 --goal-y -1') 'Evaluate dropped the goal coordinates.'
        Assert-True ($call.Directory -eq $global:PhysicalAiTestFixtureRoot) 'Evaluate used the wrong compose directory.'
    }
    Test-Case 'Verify dispatches the installed small model and saves the latest log' {
        & $launcher Verify | Out-Null
        $call = $global:PhysicalAiTestPythonCalls[-1]
        Assert-True (($call.Arguments -join ' ') -match 'complete_step3.py --model qwen3:1.7b') 'Verify used the wrong model or entry point.'
        Assert-True ($call.Directory -eq $global:PhysicalAiTestFixtureRoot) 'Verify used the wrong directory.'
        Assert-True (Test-Path -LiteralPath (Join-Path $global:PhysicalAiTestFixtureRoot 'outputs/step3-full-check.log')) 'Verify did not preserve its log.'
    }
    Test-Case 'Verification and offline-test failures propagate to the caller' {
        $global:PhysicalAiTestPythonExit = 7
        try {
            Assert-Fails { & $launcher Verify } 'exit 7'
            $log = Get-Content -LiteralPath (Join-Path $global:PhysicalAiTestFixtureRoot 'outputs/step3-full-check.log') -Raw
            Assert-True ($log -match 'VERIFICATION INCOMPLETE') 'Verification failure was missing from the log.'
            Assert-Fails { & $launcher TestExtension } 'exit 7'
        } finally { $global:PhysicalAiTestPythonExit = 0 }
    }
    Test-Case 'Failed legacy case suite restores original world and previous run evidence' {
        $before = (Get-FileHash -LiteralPath $worldPath).Hash
        $reportPath = Join-Path $global:PhysicalAiTestFixtureRoot 'outputs/step2-run.json'
        Set-Content -LiteralPath $reportPath -Value '{"original":true}' -Encoding UTF8
        $reportBefore = (Get-FileHash -LiteralPath $reportPath).Hash
        $global:PhysicalAiTestFailReadiness = $true
        try { Assert-Fails { & $launcher Cases } 'Some cases failed' } finally { $global:PhysicalAiTestFailReadiness = $false }
        Assert-True ((Get-FileHash -LiteralPath $worldPath).Hash -eq $before) 'Failed suite did not restore the original world bytes.'
        Assert-True ((Get-FileHash -LiteralPath $reportPath).Hash -eq $reportBefore) 'Failed suite replaced existing run evidence.'
    }
    Test-Case 'Successful legacy case suite restores original world and run evidence' {
        $before = (Get-FileHash -LiteralPath $worldPath).Hash
        $reportPath = Join-Path $global:PhysicalAiTestFixtureRoot 'outputs/step2-run.json'
        $reportBefore = (Get-FileHash -LiteralPath $reportPath).Hash
        $sessionRoot = Join-Path $global:PhysicalAiTestFixtureRoot 'outputs/step2-cases'
        $previousSessions = @(Get-ChildItem -LiteralPath $sessionRoot -Directory | Select-Object -ExpandProperty FullName)
        & $launcher Cases | Out-Null
        $newSession = @(Get-ChildItem -LiteralPath $sessionRoot -Directory | Where-Object { $_.FullName -notin $previousSessions })
        Assert-True ($newSession.Count -eq 1) 'Case suite did not save one new session.'
        $summary = Get-Content -LiteralPath (Join-Path $newSession[0].FullName 'summary.json') -Raw | ConvertFrom-Json
        Assert-True ($summary.result -eq 'PASS' -and $summary.cases.Count -eq 3) 'Mock successful cases were not recorded as PASS.'
        Assert-True ((Get-FileHash -LiteralPath $worldPath).Hash -eq $before) 'Successful suite did not restore original world bytes.'
        Assert-True ((Get-FileHash -LiteralPath $reportPath).Hash -eq $reportBefore) 'Successful suite replaced existing run evidence.'
    }
    Test-Case 'Clean preview and apply preserve argument boundaries and use the absolute script path' {
        & $launcher Clean -CheckOnly | Out-Null
        $preview = $global:PhysicalAiTestPythonCalls[-1].Arguments
        Assert-True ($preview[0] -eq (Join-Path $global:PhysicalAiTestFixtureRoot 'scripts/archive_outputs.py')) 'Clean used the wrong implementation.'
        Assert-True ($preview -notcontains '--apply') 'Clean CheckOnly applied changes.'
        & $launcher Clean | Out-Null
        $apply = $global:PhysicalAiTestPythonCalls[-1].Arguments
        Assert-True ($apply -contains '--apply') 'Clean omitted the apply flag.'
    }
    Test-Case 'Clean failures propagate to the caller' {
        $global:PhysicalAiTestPythonExit = 9
        try { Assert-Fails { & $launcher Clean } 'exit 9' } finally { $global:PhysicalAiTestPythonExit = 0 }
    }
    Test-Case 'Start and Workshop launch only the main workshop' {
        foreach ($action in @('Start','Workshop')) {
            $before = (Get-Location).Path
            & $launcher $action | Out-Null
            $call = $global:PhysicalAiTestDockerCalls[-2]
            Assert-True (($call.Arguments -join ' ') -eq 'compose up -d --build workshop') 'Start selected the simulator.'
            Assert-True ($call.Directory -eq $repositoryFixtureRoot) 'Workshop used the wrong directory.'
            Assert-True ((Get-Location).Path -eq $before) 'Start leaked its directory.'
        }
    }
    Test-Case 'Test runs workshop pytest' {
        & $launcher Test | Out-Null
        Assert-True (($global:PhysicalAiTestDockerCalls[-1].Arguments -join ' ') -eq 'compose run --rm workshop pytest -q') 'Wrong workshop test command.'
    }
    Test-Case 'Stop targets the workshop Compose project' {
        & $launcher Stop | Out-Null
        $call = $global:PhysicalAiTestDockerCalls[-1]
        Assert-True (($call.Arguments -join ' ') -eq 'compose down' -and $call.Directory -eq $repositoryFixtureRoot) 'Stop targeted the wrong project.'
    }
    Test-Case 'Simulator explicitly selects simulator service and project directory' {
        & $launcher Simulator | Out-Null
        $call = $global:PhysicalAiTestDockerCalls[-2]
        Assert-True (($call.Arguments -join ' ') -match 'up -d --build simulator$') 'Simulator selected the wrong service.'
        Assert-True ($call.Directory -eq $global:PhysicalAiTestFixtureRoot) 'Simulator used the wrong directory.'
    }
    Test-Case 'Simulator reads the shared root environment file' {
        $environmentFile = Join-Path $repositoryFixtureRoot '.env'
        Set-Content -LiteralPath $environmentFile -Value 'JUPYTER_PORT=8899'
        & $launcher SimulatorStatus | Out-Null
        $arguments = $global:PhysicalAiTestDockerCalls[-1].Arguments
        Assert-True ($arguments -contains '--env-file' -and $arguments -contains $environmentFile) 'Simulator ignored the root environment file.'
    }
    Test-Case 'Unsupported simulator preview cannot dispatch commands' {
        $before = $global:PhysicalAiTestDockerCalls.Count
        Assert-Fails { & $launcher Simulator -CheckOnly } 'supported only'
        Assert-True ($global:PhysicalAiTestDockerCalls.Count -eq $before) 'Invalid preview called Docker.'
    }
    Test-Case 'Workshop native errors propagate and restore the caller directory' {
        $before = (Get-Location).Path
        $global:PhysicalAiTestDockerExit = 7
        try { Assert-Fails { & $launcher Build } 'exit 7' } finally { $global:PhysicalAiTestDockerExit = 0 }
        Assert-True ((Get-Location).Path -eq $before) 'Workshop error leaked its directory.'
    }
} finally {
    Pop-Location
    Remove-Item Function:\docker, Function:\python, Function:\Invoke-RestMethod -ErrorAction SilentlyContinue
}
Assert-True ((Get-Location).Path -eq $originalDirectory) 'Tests did not restore the original directory.'
Write-Host "POWERSHELL CHECKS: PASS ($global:PhysicalAiTestTestsPassed tests; all services mocked)."
