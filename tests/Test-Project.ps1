# Simulator command contracts. All services are mocked.
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
$global:PhysicalAiTestFixtureRoot = Join-Path $repositoryFixtureRoot 'gazebo'
$cacheBoundary = $cacheRoot + [IO.Path]::DirectorySeparatorChar
if (-not $global:PhysicalAiTestFixtureRoot.StartsWith($cacheBoundary, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Test fixture must stay inside the test cache.'
}
New-Item -ItemType Directory -Path (Join-Path $global:PhysicalAiTestFixtureRoot 'scripts') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'project.ps1') -Destination $repositoryFixtureRoot
Copy-Item -LiteralPath (Join-Path $root 'gazebo/scripts/project_commands.ps1') -Destination (Join-Path $global:PhysicalAiTestFixtureRoot 'scripts/project_commands.ps1')
$worldDir = Join-Path $global:PhysicalAiTestFixtureRoot 'simulation/worlds'
New-Item -ItemType Directory -Path $worldDir -Force | Out-Null
$worldPath = Join-Path $worldDir 'practice.sdf'
Copy-Item -LiteralPath (Join-Path $root 'gazebo/simulation/worlds/practice.sdf') -Destination $worldPath
foreach ($name in @('navigate_to_goal.py')) {
    Set-Content -LiteralPath (Join-Path $global:PhysicalAiTestFixtureRoot "scripts/$name") -Value '# fixture only'
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
        Write-Output '{"services":{"simulator":{"ports":[{"target":6080,"published":6080}]}}}'
        return
    }
    if ($global:PhysicalAiTestFailReadiness -and $command -match 'wait_for_sensors.py') {
        Write-Output 'Mock readiness failure'
        $global:LASTEXITCODE = 1
        return
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
        $sources = @(Get-Item -LiteralPath (Join-Path $root 'project.ps1'), (Join-Path $root 'gazebo/scripts/project_commands.ps1'), $PSCommandPath)
        foreach ($source in $sources) {
            $tokens = $null; $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($source.FullName, [ref]$tokens, [ref]$errors) | Out-Null
            Assert-True ($errors.Count -eq 0) "PowerShell syntax error: $($source.FullName)"
        }
    }
    Test-Case 'Help does not contact services' {
        $global:PhysicalAiTestDockerCalls.Clear(); $global:PhysicalAiTestPythonCalls.Clear()
        $help = & $launcher Help | Out-String
        Assert-True ($help -match 'Verify' -and $help -match 'Test' -and $help -match 'Record') 'Help omitted primary commands.'
        Assert-True ($global:PhysicalAiTestDockerCalls.Count -eq 0 -and $global:PhysicalAiTestPythonCalls.Count -eq 0) 'Help started a service.'
    }
    Test-Case 'Evaluate forwards parameters from an unrelated working directory' {
        $before = (Get-FileHash -LiteralPath $worldPath).Hash
        $output = & $launcher Evaluate -GoalX 1 -GoalY -1 -CheckOnly 6>&1 | Out-String
        Assert-True ($output -match 'configured for navigation') 'Navigation preview was not returned.'
        Assert-True ((Get-FileHash -LiteralPath $worldPath).Hash -eq $before) 'CheckOnly changed the world.'
        Assert-True ($global:PhysicalAiTestDockerCalls.Count -eq 0) 'CheckOnly called Docker.'
    }
    Test-Case 'Unsupported CheckOnly cannot start navigation' {
        Assert-Fails { & $launcher Verify -CheckOnly } 'supported only'
        Assert-True ($global:PhysicalAiTestPythonCalls.Count -eq 0) 'Unsupported CheckOnly launched Python.'
    }
    Test-Case 'Navigation lock stops evaluation before Docker' {
        $lock = Join-Path $global:PhysicalAiTestFixtureRoot 'outputs/navigation.lock'
        Set-Content -LiteralPath $lock -Value 'test fixture'
        try {
            foreach ($action in @('Evaluate')) {
                Assert-Fails { & $launcher $action } 'navigation.lock'
            }
            Assert-True ($global:PhysicalAiTestDockerCalls.Count -eq 0) 'Locked navigation called Docker.'
        } finally { Remove-Item -LiteralPath $lock }
    }
    Test-Case 'Management commands use the compose project directory and restore location' {
        $before = (Get-Location).Path
        & $launcher Status | Out-Null
        Assert-True ($global:PhysicalAiTestDockerCalls[-1].Directory -eq $global:PhysicalAiTestFixtureRoot) 'Compose used the caller directory.'
        Assert-True ((Get-Location).Path -eq $before) 'Management command leaked its working directory.'
    }
    Test-Case 'Evaluate forwards goal coordinates and executes in the project directory' {
        & $launcher Evaluate -GoalX 1 -GoalY -1 | Out-Null
        $call = $global:PhysicalAiTestDockerCalls[-1]
        $command = $call.Arguments -join ' '
        Assert-True ($command -match '--goal-x 1 --goal-y -1') 'Evaluate dropped the goal coordinates.'
        Assert-True ($call.Directory -eq $global:PhysicalAiTestFixtureRoot) 'Evaluate used the wrong compose directory.'
    }
    Test-Case 'Verify dispatches the installed small model and saves the latest log' {
        & $launcher Verify -Model qwen3:1.7b | Out-Null
        $call = $global:PhysicalAiTestPythonCalls[-1]
        Assert-True (($call.Arguments -join ' ') -match 'verify_navigation.py --model qwen3:1.7b') 'Verify used the wrong model or entry point.'
        Assert-True ($call.Directory -eq $global:PhysicalAiTestFixtureRoot) 'Verify used the wrong directory.'
        Assert-True (Test-Path -LiteralPath (Join-Path $global:PhysicalAiTestFixtureRoot 'outputs/navigation-verification.log')) 'Verify did not preserve its log.'
    }
    Test-Case 'Verification and offline-test failures propagate to the caller' {
        $global:PhysicalAiTestPythonExit = 7
        try {
            Assert-Fails { & $launcher Verify } 'exit 7'
            $log = Get-Content -LiteralPath (Join-Path $global:PhysicalAiTestFixtureRoot 'outputs/navigation-verification.log') -Raw
            Assert-True ($log -match 'VERIFICATION INCOMPLETE') 'Verification failure was missing from the log.'
            Assert-Fails { & $launcher Test } 'exit 7'
        } finally { $global:PhysicalAiTestPythonExit = 0 }
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
    Test-Case 'Stop targets the submitted Gazebo Compose project' {
        & $launcher Stop | Out-Null
        $call = $global:PhysicalAiTestDockerCalls[-1]
        Assert-True (($call.Arguments -join ' ') -match 'down$' -and $call.Directory -eq $global:PhysicalAiTestFixtureRoot) 'Stop targeted the wrong project.'
    }
    Test-Case 'Status reads the shared root environment file' {
        $environmentFile = Join-Path $repositoryFixtureRoot '.env'
        Set-Content -LiteralPath $environmentFile -Value 'GAZEBO_WEB_PORT=6099'
        & $launcher Status | Out-Null
        $arguments = $global:PhysicalAiTestDockerCalls[-1].Arguments
        Assert-True ($arguments -contains '--env-file' -and $arguments -contains $environmentFile) 'Status ignored the root environment file.'
    }
    Test-Case 'Unsupported Start preview cannot dispatch commands' {
        $before = $global:PhysicalAiTestDockerCalls.Count
        Assert-Fails { & $launcher Start -CheckOnly } 'supported only'
        Assert-True ($global:PhysicalAiTestDockerCalls.Count -eq $before) 'Invalid preview called Docker.'
    }
    Test-Case 'Start selects the submitted simulator' {
        & $launcher Start | Out-Null
        Assert-True (($global:PhysicalAiTestDockerCalls[-2].Arguments -join ' ') -match 'up -d --build simulator$') 'Start did not select Gazebo.'
    }
    Test-Case 'Run and Record preserve instruction arguments and preview semantics' {
        $instruction = '東へ行って; echo should-not-run'
        & $launcher Run -Instruction $instruction | Out-Null
        $call = $global:PhysicalAiTestPythonCalls[-1].Arguments
        Assert-True ($call -contains $instruction -and $call -contains '--execute') 'Run split or lost the instruction.'
        & $launcher Record -CheckOnly | Out-Null
        Assert-True ($global:PhysicalAiTestPythonCalls[-1].Arguments -notcontains '--run') 'Record preview started execution.'
        & $launcher Record | Out-Null
        Assert-True ($global:PhysicalAiTestPythonCalls[-1].Arguments -contains '--run') 'Record omitted execution.'
    }
    Test-Case 'A missing Python interpreter is not reported as an AI outage' {
        Assert-Fails { & $launcher Verify -Python 'missing-physical-ai-python-executable' } 'Python 3.12'
    }
    Test-Case 'Removed commands cannot contact services' {
        $beforeDocker = $global:PhysicalAiTestDockerCalls.Count
        $beforePython = $global:PhysicalAiTestPythonCalls.Count
        foreach ($removed in @('Workshop','Simulator','SimulatorStop','SimulatorStatus','SimulatorLogs','SimulatorShell','TestExtension','Check','Demo','RunReference','Cases')) {
            Assert-Fails { & $launcher $removed } ([regex]::Escape($removed))
        }
        Assert-True ($global:PhysicalAiTestDockerCalls.Count -eq $beforeDocker) 'Removed command called Docker.'
        Assert-True ($global:PhysicalAiTestPythonCalls.Count -eq $beforePython) 'Removed command called Python.'
    }

} finally {
    Pop-Location
    Remove-Item Function:\docker, Function:\python, Function:\Invoke-RestMethod -ErrorAction SilentlyContinue
}
Assert-True ((Get-Location).Path -eq $originalDirectory) 'Tests did not restore the original directory.'
Write-Host "POWERSHELL CHECKS: PASS ($global:PhysicalAiTestTestsPassed tests; all services mocked)."
