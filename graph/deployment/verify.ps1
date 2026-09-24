param(
    [string]$ContainerName = "tigergraph",
    [string]$GraphName = "FraudInvestigationGraph",
    [string]$DeployRoot = "/tmp/agentic_deploy",
    [string]$TigerGraphHost = "http://127.0.0.1:14240",
    [string]$Username = "tigergraph",
    [string]$Password = "tigergraph"
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

function Invoke-CmdCapture {
    param([string]$Command, [string]$Description)
    Write-Host "==> $Description"
    Write-Host "    $Command"
    $output = & cmd /c $Command 2>&1
    $exitCode = $LASTEXITCODE
    $output | ForEach-Object { Write-Host $_ }
    return @{
        ExitCode = $exitCode
        Output = $output
    }
}

function Write-ContainerFile {
    param(
        [string]$Container,
        [string]$ContainerPath,
        [string]$Contents
    )
    $tmp = [System.IO.Path]::GetTempFileName()
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($tmp, $Contents, $utf8NoBom)
    Invoke-CmdChecked -Command "docker cp `"$tmp`" ${Container}:$ContainerPath" -Description "Copy generated file to container: $ContainerPath"
    Remove-Item $tmp -Force
}

function Get-CountFromOutput {
    param(
        [string[]]$Output,
        [string]$Label
    )
    $text = ($Output -join "`n")
    $jsonPattern = '"' + [regex]::Escape($Label) + '"\s*:\s*([0-9]+)'
    $match = [regex]::Match($text, $jsonPattern)
    if (-not $match.Success) {
        $pattern = [regex]::Escape($Label) + "\s*\|\s*([0-9]+)"
        $match = [regex]::Match($text, $pattern)
    }
    if ($match.Success) {
        return [int]$match.Groups[1].Value
    }
    return $null
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$artifactsRoot = Join-Path $projectRoot "artifacts"
$deployArtifacts = Join-Path $artifactsRoot "deployment"
New-Item -ItemType Directory -Force -Path $deployArtifacts | Out-Null
New-Item -ItemType Directory -Force -Path $artifactsRoot | Out-Null

$countsPath = Join-Path $deployArtifacts "counts_and_queries.log"
$sanityPath = Join-Path $deployArtifacts "sanity_checks.log"
$reportPath = Join-Path $projectRoot "deployment_report.md"
$evidencePath = Join-Path $artifactsRoot "evidence_bundle_HHG-001.json"

$gsqlDetect = Invoke-CmdChecked -Command "docker exec $ContainerName bash -lc ""ls /home/tigergraph/tigergraph/app/*/cmd/gsql 2>/dev/null | sort -V | tail -n1""" -Description "Detect gsql path"
$gsqlPath = ($gsqlDetect | Select-Object -Last 1).Trim()
if ([string]::IsNullOrWhiteSpace($gsqlPath)) {
    throw "Could not detect gsql path in container '$ContainerName'."
}

$countScript = @"
USE GRAPH $GraphName
INTERPRET QUERY () FOR GRAPH $GraphName {
  SumAccum<INT> @@customer_vertices = 0;
  SumAccum<INT> @@card_vertices = 0;
  SumAccum<INT> @@transaction_vertices = 0;
  SumAccum<INT> @@device_vertices = 0;
  SumAccum<INT> @@email_vertices = 0;
  SumAccum<INT> @@region_vertices = 0;
  SumAccum<INT> @@closed_case_vertices = 0;
  customers = {Customer.*};
  customers = SELECT c FROM customers:c ACCUM @@customer_vertices += 1;
  cards = {Card.*};
  cards = SELECT c FROM cards:c ACCUM @@card_vertices += 1;
  txns = {Transaction.*};
  txns = SELECT c FROM txns:c ACCUM @@transaction_vertices += 1;
  devices = {DeviceProfile.*};
  devices = SELECT c FROM devices:c ACCUM @@device_vertices += 1;
  emails = {EmailDomain.*};
  emails = SELECT c FROM emails:c ACCUM @@email_vertices += 1;
  regions = {BillingRegion.*};
  regions = SELECT c FROM regions:c ACCUM @@region_vertices += 1;
  cases = {ClosedCase.*};
  cases = SELECT c FROM cases:c ACCUM @@closed_case_vertices += 1;
  PRINT @@customer_vertices AS customer_vertices;
  PRINT @@card_vertices AS card_vertices;
  PRINT @@transaction_vertices AS transaction_vertices;
  PRINT @@device_vertices AS device_vertices;
  PRINT @@email_vertices AS email_vertices;
  PRINT @@region_vertices AS region_vertices;
  PRINT @@closed_case_vertices AS closed_case_vertices;
}
INTERPRET QUERY () FOR GRAPH $GraphName {
  SumAccum<INT> @@owns = 0;
  SumAccum<INT> @@made = 0;
  SumAccum<INT> @@from_device = 0;
  SumAccum<INT> @@purchaser_email = 0;
  SumAccum<INT> @@billed_in = 0;
  SumAccum<INT> @@next = 0;
  SumAccum<INT> @@involves = 0;
  SumAccum<INT> @@on_card = 0;
  SumAccum<INT> @@connected_to = 0;
  allc = {Customer.*};
  allc = SELECT c FROM allc:c -(OWNS:e)-> Card:t ACCUM @@owns += 1;
  allk = {Card.*};
  allk = SELECT c FROM allk:c -(MADE:e)-> Transaction:t ACCUM @@made += 1;
  allt = {Transaction.*};
  allt = SELECT c FROM allt:c -(FROM_DEVICE:e)-> DeviceProfile:t ACCUM @@from_device += 1;
  allt = SELECT c FROM allt:c -(PURCHASER_EMAIL:e)-> EmailDomain:t ACCUM @@purchaser_email += 1;
  allt = SELECT c FROM allt:c -(BILLED_IN:e)-> BillingRegion:t ACCUM @@billed_in += 1;
  allt = SELECT c FROM allt:c -(NEXT:e)-> Transaction:t ACCUM @@next += 1;
  allcc = {ClosedCase.*};
  allcc = SELECT c FROM allcc:c -(INVOLVES:e)-> Transaction:t ACCUM @@involves += 1;
  allcc = SELECT c FROM allcc:c -(ON_CARD:e)-> Card:t ACCUM @@on_card += 1;
  allcc = SELECT c FROM allcc:c -(CONNECTED_TO:e)-> Card:t ACCUM @@connected_to += 1;
  PRINT @@owns AS owns_edges;
  PRINT @@made AS made_edges;
  PRINT @@from_device AS from_device_edges;
  PRINT @@purchaser_email AS purchaser_email_edges;
  PRINT @@billed_in AS billed_in_edges;
  PRINT @@next AS next_edges;
  PRINT @@involves AS involves_edges;
  PRINT @@on_card AS on_card_edges;
  PRINT @@connected_to AS connected_to_edges;
}
SHOW QUERY *
SHOW LOADING STATUS ALL
"@

Write-ContainerFile -Container $ContainerName -ContainerPath "/tmp/verify_counts.gsql" -Contents $countScript
$counts = Invoke-CmdChecked -Command "docker exec $ContainerName bash -lc ""$gsqlPath /tmp/verify_counts.gsql""" -Description "Collect counts and installed query list"
$counts | Set-Content -Path $countsPath -Encoding UTF8

$closedCases = Get-CountFromOutput -Output $counts -Label "closed_case_vertices"
$nextEdges = Get-CountFromOutput -Output $counts -Label "next_edges"
$involvesEdges = Get-CountFromOutput -Output $counts -Label "involves_edges"
$onCardEdges = Get-CountFromOutput -Output $counts -Label "on_card_edges"
$connectedEdges = Get-CountFromOutput -Output $counts -Label "connected_to_edges"

$failures = @()
if ($null -eq $closedCases -or $closedCases -le 0) { $failures += "ClosedCase count is 0" }
if ($null -eq $nextEdges -or $nextEdges -le 0) { $failures += "NEXT edge count is 0" }
if ($null -eq $involvesEdges -or $involvesEdges -le 0) { $failures += "INVOLVES edge count is 0" }
if ($null -eq $onCardEdges -or $onCardEdges -le 0) { $failures += "ON_CARD edge count is 0" }
if ($null -eq $connectedEdges -or $connectedEdges -le 0) { $failures += "CONNECTED_TO edge count is 0" }
if (($counts -join "`n") -match "Saved as draft query") { $failures += "One or more queries remain in DRAFT status" }

$sanityScript = @"
USE GRAPH $GraphName
RUN QUERY get_transaction("3514030")
RUN QUERY get_flagged_context("3514030")
RUN QUERY get_customer_profile("C12382")
RUN QUERY get_evidence_bundle("3514030", "C12382", 100)
"@

Write-ContainerFile -Container $ContainerName -ContainerPath "/tmp/verify_sanity.gsql" -Contents $sanityScript
$sanity = Invoke-CmdChecked -Command "docker exec $ContainerName bash -lc ""$gsqlPath /tmp/verify_sanity.gsql""" -Description "Run sanity queries including get_evidence_bundle"
$sanity | Set-Content -Path $sanityPath -Encoding UTF8

$pythonScript = @"
import json
import pyTigerGraph as tg

conn = tg.TigerGraphConnection(
    host=r'$TigerGraphHost',
    restppPort=14240,
    username=r'$Username',
    password=r'$Password',
    graphname=r'$GraphName',
)
result = conn.runInstalledQuery(
    'get_evidence_bundle',
    {'flagged_txn_id': '3514030', 'customer_id': 'C12382', 'card_txn_limit': 100}
)
with open(r'$evidencePath', 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2)
print('saved', r'$evidencePath')
"@

$tmpPy = [System.IO.Path]::GetTempFileName() + ".py"
Set-Content -Path $tmpPy -Value $pythonScript -Encoding UTF8
$venvPy = Join-Path $projectRoot "venv\Scripts\python.exe"
Invoke-CmdChecked -Command "`"$venvPy`" `"$tmpPy`"" -Description "Fetch evidence bundle and save JSON artifact"
Remove-Item $tmpPy -Force

$evidenceJson = Get-Content -Path $evidencePath -Raw
if ($evidenceJson -match '"status"\s*:\s*"failed"') {
    $failures += "Evidence artifact contains failed status payload"
}

$report = @()
$report += "# deployment_report"
$report += ""
$report += "Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$report += ""
$report += "## completed steps"
$report += "- verify.ps1 collected vertex/edge counts, query install list, sanity queries, and evidence JSON."
$report += ""
if ($failures.Count -eq 0) {
    $report += "## failed steps"
    $report += "- none"
} else {
    $report += "## failed steps"
    foreach ($f in $failures) { $report += "- $f" }
}
$report += ""
$report += "## validation snapshot"
$report += "- ClosedCase vertices: $closedCases"
$report += "- NEXT edges: $nextEdges"
$report += "- INVOLVES edges: $involvesEdges"
$report += "- ON_CARD edges: $onCardEdges"
$report += "- CONNECTED_TO edges: $connectedEdges"
$report += ""
$report += "## artifacts"
$report += "- artifacts/deployment/counts_and_queries.log"
$report += "- artifacts/deployment/sanity_checks.log"
$report += "- artifacts/evidence_bundle_HHG-001.json"

$report -join "`n" | Set-Content -Path $reportPath -Encoding UTF8
Write-Host "Wrote deployment report to $reportPath"

if ($failures.Count -gt 0) {
    throw ("Verification failed: " + ($failures -join "; "))
}
