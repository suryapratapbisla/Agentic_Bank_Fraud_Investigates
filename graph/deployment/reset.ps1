param(
    [string]$ContainerName = "tigergraph",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Invoke-CmdChecked {
    param([string]$Command, [string]$Description)
    Write-Host "==> $Description"
    Write-Host "    $Command"
    $output = & cmd /c $Command 2>&1
    $exitCode = $LASTEXITCODE
    $output | ForEach-Object { Write-Host $_ }
    if ($exitCode -ne 0) {
        throw "Command failed ($exitCode): $Description"
    }
    return $output
}

if (-not $Force) {
    Write-Host "This will DROP FraudInvestigationGraph and related global types."
    $confirm = Read-Host "Type RESET to continue"
    if ($confirm -ne "RESET") {
        Write-Host "Reset cancelled."
        exit 1
    }
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$dropFile = Join-Path $projectRoot "graph\drop_schema.gsql"

if (-not (Test-Path $dropFile)) {
    throw "Missing drop schema file: $dropFile"
}

$gsqlDetect = Invoke-CmdChecked -Command "docker exec $ContainerName bash -lc ""ls /home/tigergraph/tigergraph/app/*/cmd/gsql 2>/dev/null | sort -V | tail -n1""" -Description "Detect gsql path"
$gsqlPath = ($gsqlDetect | Select-Object -Last 1).Trim()
if ([string]::IsNullOrWhiteSpace($gsqlPath)) {
    throw "Could not detect gsql path in container '$ContainerName'."
}

Invoke-CmdChecked -Command "docker cp `"$dropFile`" ${ContainerName}:/tmp/drop_schema.gsql" -Description "Copy drop_schema.gsql to container"

$dropResult = & cmd /c "docker exec $ContainerName bash -lc ""$gsqlPath /tmp/drop_schema.gsql""" 2>&1
$dropCode = $LASTEXITCODE
$dropResult | ForEach-Object { Write-Host $_ }
if ($dropCode -ne 0) {
    $text = ($dropResult -join "`n").ToLowerInvariant()
    if ($text -match "does not exist") {
        Write-Host "Objects already absent (first-run); reset effectively complete."
        exit 0
    }
    throw "Reset failed."
}

Write-Host "Reset completed successfully."
