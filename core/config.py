"""
KiCad Animator - Configurações Globais e Utilitários de Ambiente
"""

import os
import sys
import re
import shutil

# ---------------------------------------------------------------------------
# Verificação de Runtime do Blender (bpy)
# ---------------------------------------------------------------------------
try:
    import bpy
    from mathutils import Vector
    HAS_BPY = True
except ImportError:
    HAS_BPY = False

# ---------------------------------------------------------------------------
# Localização de Binários Essenciais
# ---------------------------------------------------------------------------
def find_binary(name, extra_paths=None):
    found = shutil.which(name)
    if found:
        return found
    if extra_paths:
        for p in extra_paths:
            if os.path.exists(p):
                return p
    return None

KICAD_CLI_PATHS = [
    "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
    "/usr/bin/kicad-cli",
    "/usr/local/bin/kicad-cli",
]
KICAD_CLI = find_binary("kicad-cli", KICAD_CLI_PATHS)

FFMPEG_PATHS = [
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/usr/bin/ffmpeg"
]
FFMPEG = find_binary("ffmpeg", FFMPEG_PATHS)

BLENDER_PATHS = [
    "/Applications/Blender.app/Contents/MacOS/Blender",
    os.path.expanduser("~/Applications/Blender.app/Contents/MacOS/Blender"),
    "/usr/bin/blender",
    "/usr/local/bin/blender",
    "/snap/bin/blender"
]
BLENDER_BIN = find_binary("blender", BLENDER_PATHS)

UV_PATHS = [
    os.path.expanduser("~/.local/bin/uv"),
    "/opt/homebrew/bin/uv",
    "/usr/local/bin/uv"
]
UV_BIN = find_binary("uv", UV_PATHS)

def get_best_python():
    """Retorna o executável do Python no .venv local (que possui bpy e pywebview) ou o sys.executable."""
    script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    venv_py = os.path.join(script_dir, ".venv", "bin", "python")
    if os.path.exists(venv_py):
        return venv_py
    return sys.executable

PYTHON_BIN = get_best_python()

# ---------------------------------------------------------------------------
# Estilos de Animação e Descrições
# ---------------------------------------------------------------------------
ALL_STYLES = ["rain", "radial", "assembly", "vortex"]

STYLE_DESCRIPTIONS = {
    "rain": "Chuva Linear Gravitacional (Rain)",
    "radial": "Onda Radial do Centro (Ripple)",
    "assembly": "Linha de Montagem SMT por Categoria (Pick-and-Place)",
    "vortex": "Vórtice Magnético Espiral 3D (Vortex)",
    "all": "Todos os 4 Estilos em Lote (All)"
}

RES_MAP = {
    "4k": (3840, 2160),
    "1080p": (1920, 1080),
    "720p": (1280, 720)
}

# ---------------------------------------------------------------------------
# Categorização de Componentes por Referência
# ---------------------------------------------------------------------------
PASSIVES_PREFIXES = ("R", "C", "L", "D", "LED", "FB", "RV", "RN", "TP")
ICS_PREFIXES = ("U", "IC", "Q", "T", "M", "MOD", "VR")
MECH_PREFIXES = ("J", "P", "TB", "SW", "BZ", "SPK", "F", "DISP", "OLED", "K")

def categorize_ref(ref):
    """Categoriza o componente em: 1=passivo, 2=CI/semicondutor, 3=mecânico/conector."""
    clean_ref = ref.upper()
    for p in ("LED", "DISP", "OLED", "TB", "SPK", "MOD", "VR"):
        if clean_ref.startswith(p):
            if p in ("LED",): return 1
            if p in ("MOD", "VR"): return 2
            return 3
    m = re.match(r"^([A-Z]+)", clean_ref)
    if not m:
        return 3
    prefix = m.group(1)
    if prefix in PASSIVES_PREFIXES:
        return 1
    if prefix in ICS_PREFIXES:
        return 2
    return 3
