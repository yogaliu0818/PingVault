# Build a one-folder PingVault distributable with PyInstaller.
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "==> Installing build deps"
python -m pip install -r requirements.txt "pyinstaller>=6.0" | Out-Host

$Dist = Join-Path $Root "dist\PingVault"
$Work = Join-Path $Root "build\pyinstaller"
$Icon = Join-Path $Root "pingvault\assets\pingvault.ico"
$VersionInfo = Join-Path $Root "scripts\version_info.txt"
New-Item -ItemType Directory -Force -Path $Work | Out-Null

if (-not (Test-Path $Icon)) {
  Write-Host "==> Generating app icon"
  python -c @"
from pathlib import Path
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
import sys
app = QApplication(sys.argv)
size = 256
pix = QPixmap(size, size)
pix.fill(QColor(0, 0, 0, 0))
p = QPainter(pix)
p.setRenderHint(QPainter.RenderHint.Antialiasing)
p.setBrush(QColor('#0B1424'))
p.setPen(QColor('#35D0FF'))
p.drawRoundedRect(8, 8, size - 16, size - 16, 36, 36)
p.setPen(QColor('#35D0FF'))
p.setFont(QFont('Bahnschrift', 72, QFont.Weight.Bold))
p.drawText(pix.rect(), int(Qt.AlignmentFlag.AlignCenter), 'PV')
p.end()
out = Path(r'$Icon')
out.parent.mkdir(parents=True, exist_ok=True)
pix.save(str(out), 'ICO')
"@
}

Write-Host "==> Building PingVault.exe (full features)"
$pyArgs = @(
  "-m", "PyInstaller",
  "--noconfirm",
  "--clean",
  "--windowed",
  "--uac-admin",
  "--name", "PingVault",
  "--paths", $Root,
  "--distpath", (Join-Path $Root "dist"),
  "--workpath", $Work,
  "--add-data", "pingvault\data\games.json;pingvault\data",
  "--add-data", "pingvault\assets;pingvault\assets",
  "--hidden-import", "pynvml",
  "--hidden-import", "PySide6.QtCore",
  "--hidden-import", "PySide6.QtGui",
  "--hidden-import", "PySide6.QtWidgets",
  "--hidden-import", "PySide6.QtNetwork"
)
if (Test-Path $Icon) {
  $pyArgs += @("--icon", $Icon)
}
if (Test-Path $VersionInfo) {
  $pyArgs += @("--version-file", $VersionInfo)
}
$pyArgs += "main.py"

python @pyArgs
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$Exe = Join-Path $Dist "PingVault.exe"
if (-not (Test-Path $Exe)) {
  throw "Build failed: PingVault.exe not found"
}

Write-Host ""
Write-Host "Done. Distribute folder:"
Write-Host "  $Dist"
Write-Host "Run:"
Write-Host "  $Exe"
