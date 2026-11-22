# Build full PingVault installer (PyInstaller + Inno Setup).
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Find-ISCC {
  $candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
  )
  foreach ($p in $candidates) {
    if (Test-Path $p) { return $p }
  }
  $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
}

Write-Host "==> Ensuring Inno Setup is installed"
$ISCC = Find-ISCC
if (-not $ISCC) {
  Write-Host "Inno Setup not found. Installing via winget..."
  winget install --id JRSoftware.InnoSetup -e --accept-package-agreements --accept-source-agreements
  $ISCC = Find-ISCC
  if (-not $ISCC) {
    throw "ISCC.exe still not found after Inno Setup install. Re-open terminal and retry."
  }
}
Write-Host "Using ISCC: $ISCC"

Write-Host "==> Step 1/2: Build application folder"
& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "build_exe.ps1")
if ($LASTEXITCODE -ne 0) {
  throw "build_exe.ps1 failed"
}

$DistApp = Join-Path $Root "dist\PingVault\PingVault.exe"
if (-not (Test-Path $DistApp)) {
  throw "Missing $DistApp"
}

$OutDir = Join-Path $Root "dist\installer"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Write-Host "==> Step 2/2: Compile installer"
$Iss = Join-Path $PSScriptRoot "pingvault.iss"
& $ISCC $Iss
if ($LASTEXITCODE -ne 0) {
  throw "Inno Setup compile failed"
}

$Setup = Get-ChildItem $OutDir -Filter "PingVault-Setup-*.exe" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

if (-not $Setup) {
  throw "Installer exe not found in $OutDir"
}

Write-Host ""
Write-Host "========================================"
Write-Host "Installer ready:"
Write-Host "  $($Setup.FullName)"
Write-Host "Size: $([math]::Round($Setup.Length / 1MB, 1)) MB"
Write-Host "========================================"
