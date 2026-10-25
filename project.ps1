[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('Help','Start','Stop','Status','Logs','Build','Validate','Shell','Test','Evaluate','Verify','Clean','Run','Select','Record','SubmissionCheck')]
    [string]$Action = 'Help',
    [double]$GoalX = 3.0,
    [double]$GoalY = 1.0,
    [string]$Instruction = '東側の資材受け渡し場所へ行って',
    [string]$Model = '',
    [string]$Python = $(if ($env:PHYSICAL_AI_PYTHON) { $env:PHYSICAL_AI_PYTHON } else { 'python' }),
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$env:PYTHONDONTWRITEBYTECODE = '1'
$script:RepositoryRoot = $PSScriptRoot

. (Join-Path $script:RepositoryRoot "gazebo/scripts/project_commands.ps1")

# Public entry point. Start/Stop refer to the submitted Gazebo task.
if ($CheckOnly -and $Action -notin @('Evaluate','Clean','Record')) {
    throw '-CheckOnly is supported only for Evaluate, Clean and Record. No action was started.'
}
if ($Action -eq 'Help') {
    Write-Output @"
Physical AI final submission: Japanese instruction -> local AI -> Gazebo navigation
  ./project.ps1 Start / Stop / Status / Logs / Build / Shell
  ./project.ps1 SubmissionCheck   Qualify east, test real AI, execute 3 trials
  ./project.ps1 Run -Instruction "東側の資材受け渡し場所へ行って"
  ./project.ps1 Select -Instruction "東側の資材受け渡し場所へ行って"
  ./project.ps1 Record            Reset, record fresh inference/navigation, save MP4
  ./project.ps1 Record -CheckOnly Preview recording without contacting services
  ./project.ps1 Test              Offline Python, layout and PowerShell checks
  ./project.ps1 Validate          Validate the simulator Compose configuration
  ./project.ps1 Verify            Extended verification for two destinations
  ./project.ps1 Evaluate -GoalX 3 -GoalY 1
  ./project.ps1 Clean -CheckOnly
Use -Python to choose a Python 3.12+ interpreter; -Model overrides .env OLLAMA_MODEL.
Run, Record, SubmissionCheck, Verify and Evaluate may reset/move the simulated robot.

"@
    return
}
switch ($Action) {
    { $_ -in @('Start','Stop','Status','Logs','Build','Shell','Validate') } {
        Invoke-GazeboManagement -Action $Action
        return
    }
    'Test' { Invoke-OfflineTests; return }
    'Run' { Invoke-TaskScript -Script 'destination_control.py' -ScriptArguments @($Instruction,'--execute'); return }
    'Select' { Invoke-TaskScript -Script 'destination_control.py' -ScriptArguments @($Instruction); return }
    'Record' {
        $recordArguments = @()
        if (-not $CheckOnly) { $recordArguments += '--run' }
        $recordArguments += @('--instruction',$Instruction)
        Invoke-TaskScript -Script 'record_submission.py' -ScriptArguments $recordArguments
        return
    }
    'SubmissionCheck' { Invoke-TaskScript -Script 'submission_check.py'; return }
    'Evaluate' { Invoke-GazeboEvaluation -GoalX $GoalX -GoalY $GoalY -CheckOnly:$CheckOnly; return }
    'Verify' { Invoke-GazeboVerification; return }
    'Clean' { Invoke-OutputCleanup -CheckOnly:$CheckOnly; return }
}
