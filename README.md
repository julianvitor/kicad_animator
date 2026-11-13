# KiCad Animator (3D Studio)

Gerador universal e cinemático de animações 3D para circuitos impressos projetados no KiCad (KiCad 7, 8, 9 e 10).

Possui dois motores de renderização integrados:
1. **Blender 3D (GPU PBR)**: Renderização com materiais realistas, iluminação de estúdio profissional com color grading AgX e animação procedural de componentes (chuva gravitacional, onda radial, montagem SMT, vórtice 3D).
2. **KiCad Nativo (CPU)**: Renderizador interno via `kicad-cli` com raytracing multi-core paralelo (sem necessidade de Blender instalado).

Compatível com **Linux**, **Windows** e **macOS**.

---

## 🚀 Inicialização em 1 Clique (Zero Configuração)

Para não precisar digitar comandos ou instalar manualmente dependências e Poetry, use o inicializador correspondente ao seu sistema operacional:

### Linux e macOS
```bash
./run_unix.sh
```

### Windows (PowerShell ou Clique Duplo)
```powershell
.\run_windows.ps1
```
*(ou simplesmente dê um duplo clique no arquivo `run_windows.bat`).*

> Ambos os scripts detectam a versão adequada do Python, instalam o Poetry automaticamente se necessário, instalam todas as dependências do projeto e abrem a aplicação de imediato.

---

## 🛠️ Modos de Execução Manual (Poetry / Python)

### Usando Poetry (Recomendado)
```bash
# 1. Instalar as dependências do projeto
poetry install

# 2. Executar o aplicativo (abre a interface gráfica)
poetry run kicad-animator
# ou:
poetry run python main.py
```

### Opcional: Instalar com suporte ao pacote `bpy` no Python
Caso queira usar o motor Blender sem necessitar de um executável externo do Blender instalado:
```bash
poetry install --extras blender
```

### Usando Python diretamente
```bash
# Executa a aplicação a partir de main.py
python main.py
```

---

## 💻 Modos de Uso

### 1. Interface Gráfica Desktop (Padrão)
Abre o aplicativo nativo com preview em tempo real, console de execução e barra de progresso:
```bash
poetry run kicad-animator
# ou:
python main.py
```

### 2. Linha de Comando (Headless / Scripts / CI)
```bash
# Renderizar animação estilo Chuva (Rain) com motor Blender GPU
poetry run kicad-animator --pcb minha_placa.kicad_pcb --backend blender --style rain --res 1080p

# Renderizar com motor KiCad Nativo (CPU raytracing com 8 núcleos)
poetry run kicad-animator --pcb minha_placa.kicad_pcb --backend kicad --workers 8 --res 1080p

# Renderizar apenas 1 quadro estático para pré-visualização rápida
poetry run kicad-animator --pcb minha_placa.kicad_pcb --still-frame 90 -o preview.png
```

### 3. Modo Interativo no Terminal
```bash
poetry run kicad-animator -i
# ou:
python main.py -i
```

---

## 🛠️ Pré-requisitos do Sistema

O KiCad Animator detecta automaticamente as ferramentas em seus caminhos padrão em cada sistema operacional:

| Ferramenta | Windows | Linux | macOS |
|------------|---------|-------|-------|
| **KiCad** (`kicad-cli`) | `C:\Program Files\KiCad\*\bin\kicad-cli.exe` ou `PATH` | `/usr/bin/kicad-cli` ou `PATH` | `/Applications/KiCad/KiCad.app/...` ou `PATH` |
| **FFmpeg** | `C:\ffmpeg\bin\ffmpeg.exe` ou `PATH` | `/usr/bin/ffmpeg` ou `PATH` | `brew install ffmpeg` ou `PATH` |
| **Blender** *(opcional)* | `C:\Program Files\Blender Foundation\Blender*\blender.exe` | `/usr/bin/blender` ou `snap/flatpak` | `/Applications/Blender.app` ou `PATH` |
| **Python** | `>= 3.10, < 3.14` | `>= 3.10, < 3.14` | `>= 3.10, < 3.14` |
