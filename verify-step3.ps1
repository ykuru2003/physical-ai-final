# Compatibility entry point. New commands are listed by .\project.ps1 Help.
[CmdletBinding()]
param()
& (Join-Path $PSScriptRoot 'scripts/powershell/verify-step3.ps1')
