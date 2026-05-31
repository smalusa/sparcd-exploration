$ErrorActionPreference = "Stop"

$appDir = $PSScriptRoot
$port = 2780
$url = "http://127.0.0.1:$port/"
$uv = "C:\Development\.tools\sparcd-exploration\uv\uv.exe"
if (-not (Test-Path -LiteralPath $uv)) {
    $uv = "uv"
}

function Test-SparcdExplorer {
    try {
        $health = Invoke-RestMethod -Uri "$url`health" -TimeoutSec 2
        return $health.status -eq "healthy"
    } catch {
        return $false
    }
}

if (-not (Test-SparcdExplorer)) {
    Start-Process `
        -FilePath $uv `
        -ArgumentList @("run", "marimo", "run", "notebooks/hello.py", "--no-token", "--host", "127.0.0.1", "--port", "$port") `
        -WorkingDirectory $appDir `
        -WindowStyle Hidden

    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        if (Test-SparcdExplorer) {
            break
        }
        Start-Sleep -Milliseconds 500
    }
}

$edgeCandidates = @(
    "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
)
$edge = $edgeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if ($edge) {
    Start-Process -FilePath $edge -ArgumentList @("--app=$url")
} else {
    Start-Process $url
}
