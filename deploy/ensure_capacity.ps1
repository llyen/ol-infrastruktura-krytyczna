<#
.SYNOPSIS
    Sprawdza i w razie potrzeby wznawia pojemnosc Fabric.

.DESCRIPTION
    Pojemnosc demonstracyjna bywa wstrzymywana (auto-pause), a wtedy kazde wywolanie
    Fabric API konczy sie bledem "CapacityNotActive". Skrypt sprawdza stan zasobu
    Azure i wznawia go, czekajac az zmieni stan na Active.

.EXAMPLE
    .\deploy\ensure_capacity.ps1
#>
[CmdletBinding()]
param(
    [string]$CapacityName  = 'fcdemo',
    [string]$ResourceGroup = 'rg-fabric-cap-demo',
    [int]$TimeoutSeconds   = 300
)

$ErrorActionPreference = 'Stop'

$state = az resource show --resource-type Microsoft.Fabric/capacities -n $CapacityName -g $ResourceGroup --query 'properties.state' -o tsv
if ($state -eq 'Active') { Write-Host "Pojemnosc $CapacityName jest aktywna." -ForegroundColor Green; return }

Write-Host "Pojemnosc $CapacityName ma stan '$state' - wznawianie..." -ForegroundColor Yellow
$subscription = az account show --query id -o tsv
$uri = "https://management.azure.com/subscriptions/$subscription/resourceGroups/$ResourceGroup/providers/Microsoft.Fabric/capacities/$CapacityName/resume?api-version=2023-11-01"
az rest --method post --url $uri | Out-Null

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
do {
    Start-Sleep -Seconds 10
    $state = az resource show --resource-type Microsoft.Fabric/capacities -n $CapacityName -g $ResourceGroup --query 'properties.state' -o tsv
    Write-Host "  stan: $state" -ForegroundColor Gray
    if ((Get-Date) -gt $deadline) { throw "Pojemnosc $CapacityName nie wrocila do stanu Active w $TimeoutSeconds s." }
} while ($state -ne 'Active')

Write-Host "Pojemnosc $CapacityName aktywna." -ForegroundColor Green
