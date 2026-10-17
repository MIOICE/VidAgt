$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$projectRoot = Split-Path -Parent $PSScriptRoot

Write-Host '[1/5] Python syntax'
@'
import ast
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
files = list((root / "app").rglob("*.py")) + list((root / "tests").rglob("*.py"))
errors = []
for path in files:
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except Exception as exc:
        errors.append((path, exc))
print(f"Parsed {len(files)} Python files; errors={len(errors)}")
for path, exc in errors:
    print(f"{path}: {exc}")
raise SystemExit(bool(errors))
'@ | python - "$projectRoot\backend"

Write-Host '[2/5] YAML and JSON syntax'
@'
import json
import pathlib
import sys
import xml.etree.ElementTree as ET
import yaml

root = pathlib.Path(sys.argv[1])
yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
yaml.safe_load((root / "docker-compose.gpu.yml").read_text(encoding="utf-8"))
yaml.safe_load((root / "frontend/pnpm-workspace.yaml").read_text(encoding="utf-8"))
for relative in [
    "frontend/package.json",
    "frontend/tsconfig.json",
    "frontend/tsconfig.app.json",
    "frontend/tsconfig.node.json",
]:
    json.loads((root / relative).read_text(encoding="utf-8"))
ET.parse(root / "deploy/minio-cors.xml")
print("YAML, JSON and XML files are valid")
'@ | python - "$projectRoot"

Write-Host '[3/5] Docker Compose'
if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker compose -f "$projectRoot\docker-compose.yml" config --quiet
} else {
    Write-Warning 'Docker is not installed; skipping Compose validation.'
}

Write-Host '[4/5] Backend checks'
$backendPython = "$projectRoot\backend\.venv\Scripts\python.exe"
if (Test-Path $backendPython) {
    Push-Location "$projectRoot\backend"
    try {
        & $backendPython -m ruff check --no-cache app tests
        $env:PYTHONDONTWRITEBYTECODE = '1'
        & $backendPython -m pytest -q -p no:cacheprovider -p no:pytest_cov tests
        & $backendPython -c "from app.main import app; schema = app.openapi(); assert len(schema['paths']) >= 19; print('OpenAPI schema:', len(schema['paths']), 'paths')"
    } finally {
        Pop-Location
    }
} else {
    Write-Warning 'backend/.venv not found; skipping pytest.'
}

Write-Host '[5/5] Frontend production build'
$pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
$pnpmPath = if ($pnpm) { $pnpm.Source } else { $null }
$bundledPnpm = 'C:\Users\yz173\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd'
if (-not $pnpmPath -and (Test-Path $bundledPnpm)) {
    $pnpmPath = $bundledPnpm
}

if ($pnpmPath -and (Test-Path "$projectRoot\frontend\node_modules")) {
    Push-Location "$projectRoot\frontend"
    try {
        & $pnpmPath run build
    } finally {
        Pop-Location
    }
} elseif (-not $pnpmPath) {
    Write-Warning 'pnpm is not available; skipping frontend build.'
} else {
    Write-Warning 'frontend/node_modules not found; run pnpm install before frontend verification.'
}

Write-Host 'Verification finished.'
