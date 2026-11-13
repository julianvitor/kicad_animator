# ==============================================================================
# KiCad Animator - Empacotador Standalone para Windows (.exe) com Blender (bpy)
# ==============================================================================
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "⚡ [KiCad Animator] Empacotando aplicativo standalone para Windows..." -ForegroundColor Cyan

$Pyi = Join-Path $ScriptDir ".venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $Pyi)) {
    Write-Host "📦 Instalando PyInstaller no ambiente local..." -ForegroundColor Yellow
    & poetry run pip install pyinstaller
}

if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "KiCad-Animator.spec") { Remove-Item -Force "KiCad-Animator.spec" }

& $Pyi --noconfirm --onedir --windowed --name "KiCad-Animator" `
  --add-data "ui;ui" `
  --collect-all bpy `
  --collect-all numpy `
  --hidden-import "logging.handlers" `
  --hidden-import "tomllib" `
  --hidden-import "xml.dom.minidom" `
  --hidden-import "xml.etree.ElementTree" `
  --hidden-import "colorsys" `
  main.py

$DistDir = Join-Path $ScriptDir "dist\KiCad-Animator"
$ZipOut = Join-Path $ScriptDir "dist\KiCad-Animator-Windows-x64.zip"

Compress-Archive -Path "$DistDir\*" -DestinationPath $ZipOut -Force

Write-Host "✅ Empacotamento concluído com sucesso!" -ForegroundColor Green
Write-Host "📦 Pasta gerada: dist\KiCad-Animator\KiCad-Animator.exe" -ForegroundColor Green
Write-Host "🗜️ Arquivo ZIP: dist\KiCad-Animator-Windows-x64.zip" -ForegroundColor Green
