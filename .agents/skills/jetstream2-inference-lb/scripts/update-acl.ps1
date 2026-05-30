param(
    [string]$ListenerName = "js2-inference-smalusa-443"
)

$ErrorActionPreference = "Stop"

$env:PATH = "C:\Users\smalusa\.local\bin;$env:PATH"
$env:OS_CLIENT_CONFIG_FILE = "C:\Development\openstack\clouds.yaml"

$ip = Invoke-RestMethod -Uri "https://api.ipify.org" -UseBasicParsing -TimeoutSec 15
if ($ip -notmatch '^\d+\.\d+\.\d+\.\d+$') {
    throw "Expected public IPv4, got '$ip'"
}

$cidr = "$ip/32"
$listener = openstack --os-cloud openstack loadbalancer listener show $ListenerName -f json | ConvertFrom-Json
$current = @($listener.allowed_cidrs, $listener.allowed_cidr) | Where-Object { $_ } | Select-Object -First 1

if ($current -eq $cidr -or $current -match [regex]::Escape($cidr)) {
    Write-Host "Listener already allows $cidr"
    exit 0
}

Write-Host "Updating $ListenerName allowed CIDR: $current -> $cidr"
openstack --os-cloud openstack loadbalancer listener set --allowed-cidr $cidr $ListenerName --wait
Write-Host "Updated listener ACL to $cidr"
