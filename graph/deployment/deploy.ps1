param(
    [string]$ContainerName = "tigergraph",
    [string]$GraphName = "FraudInvestigationGraph",
    [string]$DeployRoot = "/tmp/agentic_deploy"
)

$ErrorActionPreference = "Stop"

function Invoke-CmdChecked {
    param(
        [string]$Command,
        [string]$Description
    )
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
    param(
        [string]$Command,
        [string]$Description
    )
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

function Get-ProjectRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

function Find-GsqlPath {
    param([string]$Container)
    $cmd = "docker exec $Container bash -lc ""ls /home/tigergraph/tigergraph/app/*/cmd/gsql 2>/dev/null | sort -V | tail -n1"""
    $result = Invoke-CmdChecked -Command $cmd -Description "Discover gsql binary path"
    $path = ($result | Select-Object -Last 1).Trim()
    if ([string]::IsNullOrWhiteSpace($path)) {
        throw "Could not find gsql binary inside container $Container"
    }
    return $path
}

function Ensure-ContainerRunning {
    param([string]$Container)
    $inspectCmd = "docker inspect -f ""{{.State.Running}}"" $Container"
    $result = Invoke-CmdCapture -Command $inspectCmd -Description "Check Docker container status"
    if ($result.ExitCode -ne 0) {
        throw "Container '$Container' not found. Start TigerGraph Docker first."
    }
    $running = ($result.Output | Select-Object -Last 1).Trim()
    if ($running -ne "true") {
        throw "Container '$Container' is not running."
    }
}

function Ensure-FilteredData {
    param([string]$ProjectRoot)
    $txPath = Join-Path $ProjectRoot "DATA\filtered_data\transactions_with_identity_filtered.csv"
    $closedPath = Join-Path $ProjectRoot "DATA\filtered_data\closed_cases_history.csv"
    if (-not (Test-Path $txPath)) {
        throw "Missing filtered transactions file: $txPath"
    }
    $txHeader = Get-Content -Path $txPath -TotalCount 1
    $closedHeader = ""
    if (Test-Path $closedPath) {
        $closedHeader = Get-Content -Path $closedPath -TotalCount 1
    }
    $needsRegen = $false
    if ($txHeader -notmatch "(^|,)derived_card_id(,|$)") {
        $needsRegen = $true
    }
    if ($closedHeader -notmatch "(^|,)ext_card_id(,|$)" -or $closedHeader -notmatch "(^|,)ext_connected_card_ids(,|$)") {
        $needsRegen = $true
    }
    if ($needsRegen) {
        Write-Host "Filtered data missing derived columns. Regenerating with Scripts/Case_data.py..."
        $py = Join-Path $ProjectRoot "venv\Scripts\python.exe"
        $script = Join-Path $ProjectRoot "Scripts\Case_data.py"
        if (-not (Test-Path $py)) {
            throw "Python executable not found: $py"
        }
        $prevErrorPref = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        Invoke-CmdChecked -Command "`"$py`" `"$script`"" -Description "Regenerate filtered_data"
        $ErrorActionPreference = $prevErrorPref
        $txHeader = Get-Content -Path $txPath -TotalCount 1
        $closedHeader = Get-Content -Path $closedPath -TotalCount 1
        if ($txHeader -notmatch "(^|,)derived_card_id(,|$)") {
            throw "derived_card_id is still missing after regeneration."
        }
        if ($closedHeader -notmatch "(^|,)ext_card_id(,|$)" -or $closedHeader -notmatch "(^|,)ext_connected_card_ids(,|$)") {
            throw "ext_card_id/ext_connected_card_ids still missing after regeneration."
        }
    }
}

function Assert-NoLoadingErrors {
    param([string[]]$Output)
    $text = ($Output -join "`n")
    if ($text -match "ERRORS\s*\|\s*([1-9][0-9]*)") {
        throw "Loading job reported ERRORS > 0."
    }
    if ($text -match "Semantic Check Fails") {
        throw "Loading job semantic check failed."
    }
}

function Assert-NoDraftQueries {
    param(
        [string]$Container,
        [string]$GsqlPath,
        [string]$GraphName
    )
    $content = "USE GRAPH $GraphName`nSHOW QUERY *"
    $file = "/tmp/check_draft_queries.gsql"
    Write-ContainerFile -Container $Container -ContainerPath $file -Contents $content
    $check = Invoke-CmdCapture -Command "docker exec $Container bash -lc ""$GsqlPath $file""" -Description "Check for DRAFT queries"
    if ($check.ExitCode -ne 0) {
        throw "SHOW QUERY failed while checking for DRAFT queries."
    }
    $text = ($check.Output -join "`n")
    if ($text -match "\bDRAFT\b") {
        throw "One or more queries remain in DRAFT status after INSTALL QUERY ALL."
    }
}

function Invoke-GsqlFileOptional {
    param(
        [string]$Container,
        [string]$GsqlPath,
        [string]$ContainerFile,
        [string]$Description
    )
    $dir = [System.IO.Path]::GetDirectoryName($ContainerFile).Replace("\", "/")
    $base = [System.IO.Path]::GetFileName($ContainerFile)
    $cmd = "docker exec $Container bash -lc ""cd $dir && $GsqlPath $base"""
    $result = Invoke-CmdCapture -Command $cmd -Description $Description
    if ($result.ExitCode -ne 0) {
        $text = ($result.Output -join "`n").ToLowerInvariant()
        if ($text -match "already exists" -or $text -match "duplicate") {
            Write-Host "Index/schema change reported existing objects; continuing."
            return
        }
        throw "Command failed ($($result.ExitCode)): $Description"
    }
}

function Stage-ProjectIntoContainer {
    param(
        [string]$Container,
        [string]$ProjectRoot,
        [string]$TargetRoot
    )
    Invoke-CmdChecked -Command "docker exec -u 0 $Container bash -lc ""rm -rf $TargetRoot && mkdir -p $TargetRoot && chown -R tigergraph:tigergraph $TargetRoot""" -Description "Reset deployment staging directory in container"
    Invoke-CmdChecked -Command "docker cp `"$ProjectRoot\graph`" ${Container}:$TargetRoot/" -Description "Copy graph folder to container"
    Invoke-CmdChecked -Command "docker exec -u 0 $Container bash -lc ""mkdir -p $TargetRoot/DATA/filtered_data && chown -R tigergraph:tigergraph $TargetRoot/DATA""" -Description "Ensure filtered_data directory in container"
    Invoke-CmdChecked -Command "docker cp `"$ProjectRoot\DATA\filtered_data\.`" ${Container}:$TargetRoot/DATA/filtered_data/" -Description "Copy filtered data folder to container"
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

function Invoke-GsqlFile {
    param(
        [string]$Container,
        [string]$GsqlPath,
        [string]$ContainerFile,
        [string]$Description
    )
    $dir = [System.IO.Path]::GetDirectoryName($ContainerFile).Replace("\", "/")
    $base = [System.IO.Path]::GetFileName($ContainerFile)
    $cmd = "docker exec $Container bash -lc ""cd $dir && $GsqlPath $base"""
    Invoke-CmdChecked -Command $cmd -Description $Description
}

function Invoke-GsqlSchemaChangeRunOptional {
    param(
        [string]$Container,
        [string]$GsqlPath,
        [string]$JobName,
        [string]$Description
    )
    $content = "USE GLOBAL`nRUN GLOBAL SCHEMA_CHANGE JOB $JobName"
    $containerFile = "/tmp/gsql_schema_run_$(Get-Random).gsql"
    Write-ContainerFile -Container $Container -ContainerPath $containerFile -Contents $content
    $result = Invoke-CmdCapture -Command "docker exec $Container bash -lc ""$GsqlPath $containerFile""" -Description $Description
    if ($result.ExitCode -ne 0) {
        $text = ($result.Output -join "`n").ToLowerInvariant()
        if ($text -match "already exists" -or $text -match "duplicate" -or $text -match "already has") {
            Write-Host "Schema change job '$JobName' already applied; continuing."
            return
        }
        throw "Command failed ($($result.ExitCode)): $Description"
    }
}

function Invoke-GsqlInline {
    param(
        [string]$Container,
        [string]$GsqlPath,
        [string]$Content,
        [string]$Description
    )
    $containerFile = "/tmp/gsql_inline_$(Get-Random).gsql"
    Write-ContainerFile -Container $Container -ContainerPath $containerFile -Contents $Content
    Invoke-GsqlFile -Container $Container -GsqlPath $GsqlPath -ContainerFile $containerFile -Description $Description
}

$projectRoot = Get-ProjectRoot
$artifactsDir = Join-Path $projectRoot "artifacts\deployment"
New-Item -ItemType Directory -Force -Path $artifactsDir | Out-Null
$logPath = Join-Path $artifactsDir "deploy.log"
Start-Transcript -Path $logPath -Force | Out-Null

try {
    Ensure-ContainerRunning -Container $ContainerName
    Ensure-FilteredData -ProjectRoot $projectRoot

    $py = Join-Path $projectRoot "venv\Scripts\python.exe"
    $nextScript = Join-Path $projectRoot "Scripts\generate_next_edges.py"
    Invoke-CmdChecked -Command "`"$py`" `"$nextScript`"" -Description "Generate NEXT edge CSV"

    $gsqlPath = Find-GsqlPath -Container $ContainerName
    Stage-ProjectIntoContainer -Container $ContainerName -ProjectRoot $projectRoot -TargetRoot $DeployRoot

    # Schema reset (destructive): attempt drop and continue even if some objects don't exist.
    $dropResult = Invoke-CmdCapture -Command "docker exec $ContainerName bash -lc ""cd $DeployRoot/graph && $gsqlPath drop_schema.gsql""" -Description "Drop existing graph/types (destructive reset)"
    if ($dropResult.ExitCode -ne 0) {
        Write-Host "drop_schema.gsql returned non-zero (often missing objects). Continuing with setup."
    }

    Invoke-GsqlFile -Container $ContainerName -GsqlPath $gsqlPath -ContainerFile "$DeployRoot/graph/setup.gsql" -Description "Apply schema setup.gsql"

    # Install loading jobs
    $loadingFiles = @(
        "load_customers.gsql",
        "load_cards.gsql",
        "load_transactions.gsql",
        "load_devices.gsql",
        "load_email_domains.gsql",
        "load_billing_regions.gsql",
        "load_closed_cases.gsql",
        "load_next_edges.gsql"
    )
    foreach ($file in $loadingFiles) {
        Invoke-GsqlFile -Container $ContainerName -GsqlPath $gsqlPath -ContainerFile "$DeployRoot/graph/loading/$file" -Description "Install loading job $file"
    }

    # Run loading jobs in dependency order with status checks
    $runLoads = @"
USE GRAPH $GraphName
RUN LOADING JOB load_customers USING f_customers="$DeployRoot/DATA/filtered_data/transactions_with_identity_filtered.csv"
SHOW LOADING STATUS ALL
RUN LOADING JOB load_cards USING f_txns="$DeployRoot/DATA/filtered_data/transactions_with_identity_filtered.csv"
SHOW LOADING STATUS ALL
RUN LOADING JOB load_transactions USING f_txns="$DeployRoot/DATA/filtered_data/transactions_with_identity_filtered.csv"
SHOW LOADING STATUS ALL
RUN LOADING JOB load_next_edges USING f_next="$DeployRoot/DATA/filtered_data/next_edges.csv"
SHOW LOADING STATUS ALL
RUN LOADING JOB load_devices USING f_txns="$DeployRoot/DATA/filtered_data/transactions_with_identity_filtered.csv"
SHOW LOADING STATUS ALL
RUN LOADING JOB load_email_domains USING f_txns="$DeployRoot/DATA/filtered_data/transactions_with_identity_filtered.csv"
SHOW LOADING STATUS ALL
RUN LOADING JOB load_billing_regions USING f_txns="$DeployRoot/DATA/filtered_data/transactions_with_identity_filtered.csv"
SHOW LOADING STATUS ALL
RUN LOADING JOB load_closed_cases USING f_closed_cases="$DeployRoot/DATA/filtered_data/closed_cases_history.csv"
SHOW LOADING STATUS ALL
"@
    Write-ContainerFile -Container $ContainerName -ContainerPath "/tmp/gsql_inline_load.gsql" -Contents $runLoads
    $loadResult = Invoke-CmdCapture -Command "docker exec $ContainerName bash -lc ""$gsqlPath /tmp/gsql_inline_load.gsql""" -Description "Run all loading jobs"
    if ($loadResult.ExitCode -ne 0) {
        throw "Loading jobs command failed."
    }
    Assert-NoLoadingErrors -Output $loadResult.Output
    ($loadResult.Output -join "`n") | Set-Content -Path (Join-Path $artifactsDir "04_run_loading_jobs.log") -Encoding UTF8

    # Post-load
    Invoke-GsqlFileOptional -Container $ContainerName -GsqlPath $gsqlPath -ContainerFile "$DeployRoot/graph/utils/indexes.gsql" -Description "Create investigation index schema change job"
    Invoke-GsqlSchemaChangeRunOptional -Container $ContainerName -GsqlPath $gsqlPath -JobName "add_investigation_indexes" -Description "Run investigation index schema change job"
    Invoke-GsqlFileOptional -Container $ContainerName -GsqlPath $gsqlPath -ContainerFile "$DeployRoot/graph/utils/case_memory_vector.gsql" -Description "Create CaseMemory vector schema change job"
    Invoke-GsqlSchemaChangeRunOptional -Container $ContainerName -GsqlPath $gsqlPath -JobName "add_case_memory_vector" -Description "Run CaseMemory vector schema change job"
    Invoke-GsqlFile -Container $ContainerName -GsqlPath $gsqlPath -ContainerFile "$DeployRoot/graph/queries/customer_queries.gsql" -Description "Install customer queries"

    $runPost = @"
USE GRAPH $GraphName
INSTALL QUERY refresh_customer_stats
RUN QUERY refresh_customer_stats()
"@
    Invoke-GsqlInline -Container $ContainerName -GsqlPath $gsqlPath -Content $runPost -Description "Run post-load customer stats refresh"

    $queryFiles = @(
        "customer_queries.gsql",
        "transaction_queries.gsql",
        "fraud_queries.gsql",
        "similarity_queries.gsql",
        "memory_queries.gsql",
        "agent_evidence_queries.gsql"
    )
    foreach ($qf in $queryFiles) {
        Invoke-GsqlFile -Container $ContainerName -GsqlPath $gsqlPath -ContainerFile "$DeployRoot/graph/queries/$qf" -Description "Install query file $qf"
    }
    Invoke-GsqlInline -Container $ContainerName -GsqlPath $gsqlPath -Content "USE GRAPH $GraphName`nINSTALL QUERY ALL" -Description "Install all queries"
    Assert-NoDraftQueries -Container $ContainerName -GsqlPath $gsqlPath -GraphName $GraphName

    Write-Host "Deployment completed successfully."
}
catch {
    Write-Host "Deployment failed: $($_.Exception.Message)"
    Stop-Transcript | Out-Null
    exit 1
}

Stop-Transcript | Out-Null
exit 0
