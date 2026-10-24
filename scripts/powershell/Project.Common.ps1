# Shared paths and safety guards for project PowerShell commands.
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$script:PhysicalAiProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))

function Get-PhysicalAiProjectRoot {
    return $script:PhysicalAiProjectRoot
}

function Assert-PhysicalAiIdle {
    $root = Get-PhysicalAiProjectRoot
    foreach ($name in @('step2-autotest.request', 'step2-autotest.running', 'navigation.lock')) {
        if (Test-Path -LiteralPath (Join-Path $root "outputs/$name")) {
            throw "Navigation or automatic test pending/running: $name"
        }
    }
}
