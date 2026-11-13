#!/usr/bin/env bash
# ==============================================================================
# KiCad Animator - Empacotador Standalone para macOS (.app) com Blender (bpy)
# ==============================================================================
set -e

cd "$(dirname "$0")"

echo "⚡ [KiCad Animator] Empacotando aplicativo standalone para macOS..."

# Garante ambiente com PyInstaller e bpy
if [ -x ".venv/bin/pyinstaller" ]; then
    PYI=".venv/bin/pyinstaller"
else
    echo "📦 Instalando PyInstaller no ambiente local..."
    ./run_unix.sh --help >/dev/null 2>&1 || true
    .venv/bin/pip install pyinstaller || uv pip install --python .venv/bin/python pyinstaller
    PYI=".venv/bin/pyinstaller"
fi

rm -rf build dist KiCad-Animator.spec

$PYI --noconfirm --onedir --windowed --name "KiCad-Animator" \
  --add-data "ui:ui" \
  --collect-all bpy \
  --collect-all numpy \
  --hidden-import "logging.handlers" \
  --hidden-import "tomllib" \
  --hidden-import "xml.dom.minidom" \
  --hidden-import "xml.etree.ElementTree" \
  --hidden-import "colorsys" \
  main.py

cd dist
zip -r -q KiCad-Animator-macOS.zip KiCad-Animator.app
cd ..

echo "✅ Empacotamento concluído com sucesso!"
echo "📦 Aplicativo gerado: dist/KiCad-Animator.app"
echo "🗜️ Arquivo ZIP: dist/KiCad-Animator-macOS.zip"
