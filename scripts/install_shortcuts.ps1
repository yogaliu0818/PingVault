# Install PingVault shortcuts on Desktop and Start Menu.
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File scripts\install_shortcuts.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$pywCmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
if ($pywCmd) {
  $Pythonw = $pywCmd.Source
} else {
  $Pythonw = (Get-Command python.exe).Source
}

$Desktop = [Environment]::GetFolderPath("Desktop")
$StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$IconPath = Join-Path $Root "pingvault\assets\pingvault.ico"
$MainPy = Join-Path $Root "main.py"

if (-not (Test-Path $IconPath)) {
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
out = Path(r'$IconPath')
out.parent.mkdir(parents=True, exist_ok=True)
pix.save(str(out), 'ICO')
"@
}

$Wsh = New-Object -ComObject WScript.Shell
function New-PingVaultShortcut([string]$Path) {
  $sc = $Wsh.CreateShortcut($Path)
  $sc.TargetPath = $Pythonw
  $sc.Arguments = "`"$MainPy`""
  $sc.WorkingDirectory = $Root
  $sc.WindowStyle = 1
  $sc.Description = "PingVault - local game boost and monitor"
  if (Test-Path $IconPath) {
    $sc.IconLocation = "$IconPath,0"
  }
  $sc.Save()
  Write-Host "Created: $Path"
}

New-PingVaultShortcut (Join-Path $Desktop "PingVault.lnk")
New-PingVaultShortcut (Join-Path $StartMenu "PingVault.lnk")
Write-Host "Done."
