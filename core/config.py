"""
KiCad Animator - Configurações Globais e Utilitários de Ambiente
"""

import os
import sys
import re
import shutil
import subprocess

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
# Localização de Binários Essenciais (Multiplataforma: Linux, Windows, macOS)
# ---------------------------------------------------------------------------
def find_binary(name, extra_paths=None):
    found = shutil.which(name)
    if found:
        return found
    if sys.platform == "win32" and not name.lower().endswith(".exe"):
        found = shutil.which(f"{name}.exe")
        if found:
            return found
    if extra_paths:
        for p in extra_paths:
            if not p:
                continue
            if "*" in p:
                import glob
                matches = glob.glob(p)
                if matches:
                    return sorted(matches, reverse=True)[0]
            elif os.path.exists(p):
                return p
    return None

prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
prog_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
local_app_data = os.environ.get("LOCALAPPDATA", "")

KICAD_CLI_PATHS = [
    # macOS
    "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
    os.path.expanduser("~/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"),
    # Linux
    "/usr/bin/kicad-cli",
    "/usr/local/bin/kicad-cli",
    "/app/bin/kicad-cli",
    # Windows
    os.path.join(prog_files, "KiCad", "*", "bin", "kicad-cli.exe"),
    os.path.join(prog_files, "KiCad", "bin", "kicad-cli.exe"),
    os.path.join(prog_files_x86, "KiCad", "*", "bin", "kicad-cli.exe"),
    os.path.join(prog_files_x86, "KiCad", "bin", "kicad-cli.exe"),
]
KICAD_CLI = find_binary("kicad-cli", KICAD_CLI_PATHS)

FFMPEG_PATHS = [
    # macOS
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    # Linux
    "/usr/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/snap/bin/ffmpeg",
    # Windows
    r"C:\ffmpeg\bin\ffmpeg.exe",
    os.path.join(prog_files, "ffmpeg", "bin", "ffmpeg.exe"),
    os.path.join(prog_files, "ffmpeg", "ffmpeg.exe"),
    os.path.join(local_app_data, "Microsoft", "WinGet", "Packages", "*", "*ffmpeg.exe") if local_app_data else None,
]
FFMPEG = find_binary("ffmpeg", FFMPEG_PATHS)

BLENDER_PATHS = [
    # macOS
    "/Applications/Blender.app/Contents/MacOS/Blender",
    os.path.expanduser("~/Applications/Blender.app/Contents/MacOS/Blender"),
    # Linux
    "/usr/bin/blender",
    "/usr/local/bin/blender",
    "/snap/bin/blender",
    # Windows
    os.path.join(prog_files, "Blender Foundation", "Blender *", "blender.exe"),
    os.path.join(prog_files, "Blender Foundation", "Blender", "blender.exe"),
    r"C:\Blender\blender.exe",
]
BLENDER_BIN = find_binary("blender", BLENDER_PATHS)

UV_PATHS = [
    os.path.expanduser("~/.local/bin/uv"),
    os.path.expanduser("~/.cargo/bin/uv"),
    "/opt/homebrew/bin/uv",
    "/usr/local/bin/uv",
    os.path.join(local_app_data, "Programs", "uv", "uv.exe") if local_app_data else None,
]
UV_BIN = find_binary("uv", UV_PATHS)

POETRY_PATHS = [
    os.path.expanduser("~/.local/bin/poetry"),
    os.path.expanduser("~/.poetry/bin/poetry"),
    "/opt/homebrew/bin/poetry",
    "/usr/local/bin/poetry",
    os.path.join(os.environ.get("APPDATA", ""), "Python", "Scripts", "poetry.exe") if os.environ.get("APPDATA") else None,
]
POETRY_BIN = find_binary("poetry", POETRY_PATHS)

def get_best_python():
    """Retorna o executável Python no ambiente Poetry/.venv local ou sys.executable."""
    script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    # 1. Prioriza o .venv local do projeto (Unix: bin/python, Windows: Scripts/python.exe)
    if sys.platform == "win32":
        venv_candidates = [
            os.path.join(script_dir, ".venv", "Scripts", "python.exe"),
            os.path.join(script_dir, ".venv", "python.exe")
        ]
    else:
        venv_candidates = [
            os.path.join(script_dir, ".venv", "bin", "python"),
            os.path.join(script_dir, ".venv", "bin", "python3")
        ]

    for p in venv_candidates:
        if os.path.exists(p):
            return p

    # 2. Verifica ambiente Poetry ativo via CLI
    if POETRY_BIN:
        try:
            res = subprocess.run([POETRY_BIN, "--directory", script_dir, "env", "info", "-e"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=script_dir)
            if res.returncode == 0 and res.stdout.strip() and os.path.exists(res.stdout.strip()):
                return res.stdout.strip()
        except Exception:
            pass

    # 3. Fallback: se o Python atual tem as dependências
    try:
        import webview
        return sys.executable
    except ImportError:
        pass

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
