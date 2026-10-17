param(
    [ValidateRange(1, 10)]
    [int]$RetryCount = 3
)

$ErrorActionPreference = "Continue"
$projectRoot = Split-Path -Parent $PSScriptRoot
$dockerBin = "C:\Program Files\Docker\Docker\resources\bin"
$docker = Join-Path $dockerBin "docker.exe"

if (-not (Test-Path -LiteralPath $docker)) {
    throw "Docker CLI not found at $docker"
}

$env:PATH = "$dockerBin;$env:PATH"
Set-Location -LiteralPath $projectRoot

$images = @(
    "mysql:8.4",
    "redis:7.4-alpine",
    "alpine/minio:RELEASE.2025-10-15T17-29-55Z",
    "python:3.12-slim",
    "node:24-alpine",
    "nginx:1.27-alpine"
)

foreach ($image in $images) {
    $pulled = $false
    for ($attempt = 1; $attempt -le $RetryCount; $attempt++) {
        Write-Host "Pulling $image (attempt $attempt/$RetryCount)"
        & $docker pull $image
        if ($LASTEXITCODE -eq 0) {
            $pulled = $true
            break
        }
        if ($attempt -lt $RetryCount) {
            Start-Sleep -Seconds 3
        }
    }
    if (-not $pulled) {
        throw "Failed to pull $image after $RetryCount attempts."
    }
}

& $docker compose config --quiet
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose configuration validation failed."
}

$started = $false
for ($attempt = 1; $attempt -le $RetryCount; $attempt++) {
    Write-Host "Building and starting Compose services (attempt $attempt/$RetryCount)"
    & $docker compose --progress plain up -d --build
    if ($LASTEXITCODE -eq 0) {
        $started = $true
        break
    }
    if ($attempt -lt $RetryCount) {
        Start-Sleep -Seconds 3
    }
}
if (-not $started) {
    throw "Docker Compose build or startup failed after $RetryCount attempts."
}

& $docker compose ps
