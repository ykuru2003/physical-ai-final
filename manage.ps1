param(
    [ValidateSet('Start', 'Stop', 'Status', 'Check', 'Demo', 'Workshop', 'Shell', 'Logs', 'Build', 'Validate')]
    [string]$Action = 'Start'
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker Desktop is required. Install it and enable Linux containers.'
    }
    & docker compose --profile workshop config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Invalid Docker Compose configuration.' }
    if ($Action -eq 'Validate') { Write-Host 'Compose configuration: PASS'; return }

    $engine = & docker info --format '{{.OSType}}' 2>$null
    if ($LASTEXITCODE -ne 0 -or $engine -ne 'linux') {
        throw 'Start Docker Desktop, wait until Engine running, and use Linux containers. Then retry.'
    }
    switch ($Action) {
        'Start' { & docker compose up -d --build simulator }
        'Stop' { & docker compose --profile workshop down }
        'Status' { & docker compose --profile workshop ps }
        'Build' { & docker compose build simulator }
        'Check' { & docker compose exec -T simulator /ros_entrypoint.sh python3 /workspace/scripts/check_environment.py }
        'Demo' { & docker compose exec -T simulator /ros_entrypoint.sh python3 /workspace/scripts/demo_drive.py }
        'Workshop' { & docker compose --profile workshop up -d --build workshop }
        'Shell' { & docker compose exec simulator /ros_entrypoint.sh bash }
        'Logs' { & docker compose logs --tail 100 simulator }
    }
    if ($LASTEXITCODE -ne 0) { throw "Docker action failed: $Action" }
    if ($Action -eq 'Start') {
        $config = (& docker compose config --format json | Out-String) | ConvertFrom-Json
        $port = ($config.services.simulator.ports | Where-Object target -eq 6080).published
        Write-Host "Gazebo: http://localhost:$port/vnc.html?autoconnect=true&resize=scale"
        Write-Host 'Wait for the desktop, then run: .\manage.ps1 Check'
    }
    if ($Action -eq 'Workshop') {
        $config = (& docker compose --profile workshop config --format json | Out-String) | ConvertFrom-Json
        $port = ($config.services.workshop.ports | Where-Object target -eq 8888).published
        Write-Host "JupyterLab: http://localhost:$port/lab?token=roboops-workshop"
    }
}
finally { Pop-Location }
