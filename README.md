# KiCad Animator (3D Studio)

> **Universal 3D cinematic animation studio for KiCad printed circuit boards (KiCad 7, 8, 9 & 10).**

<p align="center">
  <img src="docs/assets/demo_jardim.gif" alt="KiCad Animator 3D Demo" width="100%">
</p>

<p align="center">
  <a href="#-english"><b>English</b></a> • <a href="#-português"><b>Português</b></a>
</p>

---

## 🌐 English

Universal tool for generating 3D cinematic PCB animations directly from KiCad projects:
- **Blender 3D (GPU PBR)**: Photorealistic materials, AgX studio lighting, and procedural component animations (*Rain*, *Radial Wave*, *SMT Assembly*, *Vortex*).
- **KiCad Native (CPU)**: Built-in raytracing via `kicad-cli` with multi-core parallel rendering (no Blender installation required).
- **Cross-Platform**: Linux, Windows, and macOS.

<p align="center">
  <img src="docs/assets/ui_studio.png" alt="KiCad Animator Desktop UI" width="100%">
</p>

### 📦 Standalone Binaries (Pre-built)

Download ready-to-run executables from [Releases](https://github.com/julianvitor/kicad_animator/releases):
- **Windows (x64)**: `KiCad-Animator-Windows-x64.zip` (`KiCad-Animator.exe`)
- **macOS (Apple Silicon & Intel)**: `KiCad-Animator-macOS.zip` (`KiCad-Animator.app`)

*Build locally:* `.\package_windows.ps1` (Windows) or `./package_mac.sh` (macOS).

### 🚀 1-Click Launch (From Source)

Automatically checks Python, installs Poetry & dependencies, and launches the application:
- **Linux / macOS**: `./run_unix.sh`
- **Windows**: `.\run_windows.ps1` (or double-click `run_windows.bat`)

### 💻 Usage

#### Desktop GUI
```bash
poetry run kicad-animator
# or: python main.py
```

#### Command Line (CLI / Headless / CI)
```bash
# Blender GPU render (Rain style, 1080p)
poetry run kicad-animator --pcb board.kicad_pcb --backend blender --style rain --res 1080p

# KiCad Native CPU render (8 parallel workers, 1080p)
poetry run kicad-animator --pcb board.kicad_pcb --backend kicad --workers 8 --res 1080p

# Single still-frame preview
poetry run kicad-animator --pcb board.kicad_pcb --still-frame 90 -o preview.png

# Interactive terminal mode
poetry run kicad-animator -i
```

### 🛠️ System Requirements

| Tool | Windows | Linux | macOS |
|------|---------|-------|-------|
| **KiCad** (`kicad-cli`) | Default path / `PATH` | `/usr/bin/kicad-cli` / `PATH` | `/Applications/KiCad/...` / `PATH` |
| **FFmpeg** | `PATH` | `apt` / `pacman` / `PATH` | `brew install ffmpeg` / `PATH` |
| **Blender** *(optional)* | Default path / `PATH` | `snap` / `flatpak` / `PATH` | `/Applications/Blender.app` / `PATH` |
| **Python** *(source only)* | `3.11` – `3.13` | `3.11` – `3.13` | `3.11` – `3.13` |

---

## 🌐 Português

Gerador universal e cinemático de animações 3D para placas de circuito impresso do KiCad:
- **Blender 3D (GPU PBR)**: Materiais realistas, iluminação de estúdio AgX e animações procedurais (*Chuva*, *Onda Radial*, *Montagem SMT*, *Vórtice*).
- **KiCad Nativo (CPU)**: Raytracing multi-core paralelo via `kicad-cli` (dispensa instalação do Blender).
- **Multiplataforma**: Linux, Windows e macOS.

### 📦 Executáveis Prontos (Standalone)

Baixe executáveis compilados na aba [Releases](https://github.com/julianvitor/kicad_animator/releases):
- **Windows (x64)**: `KiCad-Animator-Windows-x64.zip` (`KiCad-Animator.exe`)
- **macOS (Apple Silicon & Intel)**: `KiCad-Animator-macOS.zip` (`KiCad-Animator.app`)

*Gerar executável localmente:* `.\package_windows.ps1` (Windows) ou `./package_mac.sh` (macOS).

### 🚀 Inicialização em 1 Clique (Código-Fonte)

Verifica o Python, instala o Poetry e as dependências e abre a aplicação automaticamente:
- **Linux / macOS**: `./run_unix.sh`
- **Windows**: `.\run_windows.ps1` (ou clique duplo em `run_windows.bat`)

### 💻 Modos de Uso

#### Interface Desktop (GUI)
```bash
poetry run kicad-animator
# ou: python main.py
```

#### Linha de Comando (CLI / CI)
```bash
# Renderizar via Blender GPU (Estilo Chuva, 1080p)
poetry run kicad-animator --pcb placa.kicad_pcb --backend blender --style rain --res 1080p

# Renderizar via KiCad Nativo CPU (8 workers, 1080p)
poetry run kicad-animator --pcb placa.kicad_pcb --backend kicad --workers 8 --res 1080p

# Pré-visualização de 1 quadro estático
poetry run kicad-animator --pcb placa.kicad_pcb --still-frame 90 -o preview.png

# Modo interativo no terminal
poetry run kicad-animator -i
```

### 🛠️ Pré-requisitos do Sistema

| Ferramenta | Windows | Linux | macOS |
|------------|---------|-------|-------|
| **KiCad** (`kicad-cli`) | Caminho padrão / `PATH` | `/usr/bin/kicad-cli` / `PATH` | `/Applications/KiCad/...` / `PATH` |
| **FFmpeg** | `PATH` | `apt` / `pacman` / `PATH` | `brew install ffmpeg` / `PATH` |
| **Blender** *(opcional)* | Caminho padrão / `PATH` | `snap` / `flatpak` / `PATH` | `/Applications/Blender.app` / `PATH` |
| **Python** *(código-fonte)* | `3.11` a `3.13` | `3.11` a `3.13` | `3.11` a `3.13` |
