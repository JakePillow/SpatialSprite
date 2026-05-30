$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$studioDir = Join-Path $repoRoot "studio"

Write-Host "SpriteSpatial local studio" -ForegroundColor Cyan
Write-Host ""
Write-Host "Terminal 1:" -ForegroundColor Yellow
Write-Host "  python tools\run_studio_api.py --host 127.0.0.1 --port 8787"
Write-Host ""
Write-Host "Terminal 2:" -ForegroundColor Yellow
Write-Host "  cd studio"
Write-Host "  npm run dev"
Write-Host ""
Write-Host "URLs:" -ForegroundColor Yellow
Write-Host "  API:      http://127.0.0.1:8787/health"
Write-Host "  Frontend: http://127.0.0.1:5173"
Write-Host ""
Write-Host "Optional: start both now in hidden PowerShell windows." -ForegroundColor Gray
Write-Host "The commands are printed instead of auto-started to keep process control explicit."

if (-not (Test-Path $studioDir)) {
  throw "Studio directory not found: $studioDir"
}
