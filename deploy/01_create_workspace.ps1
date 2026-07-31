param(
    [string]$WorkspaceName = "OL-ZK-Demo-IK",
    [string]$CapacityId    = "75d74dac-c3ee-4861-8a22-e7017940afbb"
)

$ErrorActionPreference = "Stop"
$FabricApi = "https://api.fabric.microsoft.com/v1"

function Get-FabricHeaders {
    $t = az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv
    if ($LASTEXITCODE -ne 0) { throw "Nie udalo sie pobrac tokenu Fabric." }
    return @{ Authorization = "Bearer $t"; "Content-Type" = "application/json" }
}

function Invoke-Fabric {
    param([string]$Method, [string]$Path, $Body)
    $h = Get-FabricHeaders
    $uri = if ($Path -match '^https?://') { $Path } else { "$FabricApi/$Path" }
    $a = @{ Method = $Method; Uri = $uri; Headers = $h }
    if ($Body) { $a.Body = ($Body | ConvertTo-Json -Depth 20) }
    return Invoke-RestMethod @a
}

Write-Host "== Workspace: $WorkspaceName"
$all = Invoke-Fabric GET "workspaces"
$ws = $all.value | Where-Object displayName -eq $WorkspaceName
if (-not $ws) {
    $ws = Invoke-Fabric POST "workspaces" @{
        displayName = $WorkspaceName
        description = "Demo: Infrastruktura Krytyczna - efekt domina. Dane w 100% syntetyczne."
        capacityId  = $CapacityId
    }
    Write-Host "   utworzony: $($ws.id)"
} else {
    Write-Host "   istnieje: $($ws.id)"
    if (-not $ws.capacityId) {
        Invoke-Fabric POST "workspaces/$($ws.id)/assignToCapacity" @{ capacityId = $CapacityId } | Out-Null
        Write-Host "   przypisano capacity"
    }
}
$wsId = $ws.id

function New-FabricItem {
    param([string]$Type, [string]$Endpoint, [string]$Name, [string]$Description)
    $items = Invoke-Fabric GET "workspaces/$wsId/items"
    $existing = $items.value | Where-Object { $_.displayName -eq $Name -and $_.type -eq $Type }
    if ($existing) { Write-Host "   $Type '$Name' istnieje: $($existing.id)"; return $existing }

    $body = @{ displayName = $Name; description = $Description }
    $h = Get-FabricHeaders
    $r = Invoke-WebRequest -Method POST -Uri "$FabricApi/workspaces/$wsId/$Endpoint" `
         -Headers $h -Body ($body | ConvertTo-Json -Depth 20) -SkipHttpErrorCheck
    if ($r.StatusCode -eq 201) {
        $item = $r.Content | ConvertFrom-Json
        Write-Host "   $Type '$Name' utworzony: $($item.id)"
        return $item
    }
    if ($r.StatusCode -eq 202) {
        $op = $r.Headers['x-ms-operation-id'][0]
        Write-Host "   $Type '$Name' tworzony asynchronicznie..."
        do {
            Start-Sleep -Seconds 5
            $st = Invoke-Fabric GET "operations/$op"
        } while ($st.status -in @("NotStarted", "Running"))
        if ($st.status -ne "Succeeded") { throw "$Type '$Name': $($st.status)" }
        $items = Invoke-Fabric GET "workspaces/$wsId/items"
        $item = $items.value | Where-Object { $_.displayName -eq $Name -and $_.type -eq $Type }
        Write-Host "   $Type '$Name' utworzony: $($item.id)"
        return $item
    }
    throw "$Type '$Name': HTTP $($r.StatusCode) $($r.Content)"
}

Write-Host "== Lakehouse"
$lh = New-FabricItem -Type "Lakehouse" -Endpoint "lakehouses" -Name "lh_ci_graph" `
      -Description "Rejestr obiektow IK, graf zaleznosci i wyniki symulacji kaskad."

Write-Host "== Eventhouse"
$eh = New-FabricItem -Type "Eventhouse" -Endpoint "eventhouses" -Name "eh_ci_realtime" `
      -Description "Telemetria obiektow IK, meldunki operatorow SPO-10, hydrologia."

$state = [ordered]@{
    workspaceName = $WorkspaceName
    workspaceId   = $wsId
    capacityId    = $CapacityId
    lakehouseId   = $lh.id
    eventhouseId  = $eh.id
}
$outDir = Join-Path $PSScriptRoot "..\.fabric"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$statePath = Join-Path $outDir "deployment.json"
$state | ConvertTo-Json -Depth 5 | Set-Content $statePath -Encoding UTF8
Write-Host "== Zapisano stan: $statePath"
$state | Format-List
