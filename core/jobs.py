"""
KiCad Animator - Planejamento e Resolução de Trabalhos
"""

import os
from core.config import ALL_STYLES, STYLE_DESCRIPTIONS
from core.parser import find_available_pcbs

def resolve_jobs(pcb_path, style, resolution, fps, out_dest, make_gif, save_blend, backend="blender"):
    pcb_name = os.path.splitext(os.path.basename(pcb_path))[0]
    default_dir = os.path.dirname(os.path.abspath(pcb_path))
    exports_dir = os.path.join(default_dir, "exports", "animacoes")
    target_dir = exports_dir if os.path.exists(exports_dir) else default_dir

    backend_tag = f"_{backend}" if backend == "kicad" else ""
    styles_to_run = ALL_STYLES if style == "all" else [style]
    jobs = []

    if style == "all":
        base_dir = out_dest if (out_dest and (os.path.isdir(out_dest) or not out_dest.endswith(".mp4"))) else target_dir
        os.makedirs(base_dir, exist_ok=True)
        for s in styles_to_run:
            mp4_path = os.path.join(base_dir, f"{pcb_name}{backend_tag}_{s}_{resolution}_{fps}fps.mp4")
            gif_path = os.path.join(base_dir, f"{pcb_name}{backend_tag}_{s}_{resolution}_{fps}fps.gif") if make_gif else None
            blend_path = os.path.join(base_dir, f"{pcb_name}_{s}.blend") if (save_blend and backend == "blender") else None
            jobs.append((s, mp4_path, gif_path, blend_path))
    else:
        if not out_dest:
            mp4_path = os.path.join(target_dir, f"{pcb_name}{backend_tag}_{style}_{resolution}_{fps}fps.mp4")
        elif os.path.isdir(out_dest):
            mp4_path = os.path.join(out_dest, f"{pcb_name}{backend_tag}_{style}_{resolution}_{fps}fps.mp4")
        else:
            mp4_path = out_dest

        gif_path = os.path.splitext(mp4_path)[0] + ".gif" if make_gif else None
        blend_path = os.path.splitext(mp4_path)[0] + ".blend" if (save_blend and backend == "blender") else None
        jobs.append((style, mp4_path, gif_path, blend_path))

    return jobs

def prompt_terminal_interactive():
    print("\n" + "="*60)
    print("🛠️  GERADOR UNIVERSAL DE ANIMAÇÃO 3D DE PCB")
    print("="*60)

    # 1. Seleção do PCB
    available_pcbs = find_available_pcbs()
    pcb_path = None
    if available_pcbs:
        print("\n📂 Placas KiCad encontradas no projeto:")
        for idx, p in enumerate(available_pcbs, 1):
            print(f"  [{idx}] {p}")
        print(f"  [{len(available_pcbs)+1}] Digitar outro caminho...")

        while True:
            choice = input(f"\nEscolha o número da placa [1-{len(available_pcbs)+1}] (Padrão: 1): ").strip()
            if not choice or choice == "1":
                pcb_path = available_pcbs[0]
                break
            elif choice.isdigit() and 1 <= int(choice) <= len(available_pcbs):
                pcb_path = available_pcbs[int(choice)-1]
                break
            elif choice == str(len(available_pcbs)+1):
                custom = input("Caminho do arquivo .kicad_pcb: ").strip()
                if os.path.exists(custom):
                    pcb_path = custom
                    break
                print("❌ Arquivo não encontrado. Tente novamente.")
            else:
                print("❌ Opção inválida.")
    else:
        while True:
            pcb_path = input("\n📂 Digite o caminho do arquivo .kicad_pcb: ").strip()
            if os.path.exists(pcb_path):
                break
            print("❌ Arquivo não encontrado. Tente novamente.")

    # 2. Motor de Render (Backend)
    print("\n⚙️  Escolha o motor de renderização (Backend):")
    print("  [1] Blender 3D (GPU / EEVEE & Cycles PBR) [Recomendado - Materiais realistas e alta performance]")
    print("  [2] KiCad Nativo (kicad-cli / CPU Raytracing) [Renderizador interno do KiCad]")
    backend_choice = input("\nBackend [1-2] (Padrão: 1): ").strip()
    backend = "kicad" if backend_choice == "2" else "blender"

    engine = "eevee"
    save_blend = False
    workers = None
    kicad_quality = "basic"

    if backend == "blender":
        print("\n🎨 Motor de renderização do Blender:")
        print("  [1] Blender EEVEE (Ultra rápido, PBR em tempo real) [Padrão]")
        print("  [2] Blender Cycles (Raytracing fotorrealista com GPU Metal)")
        eng_choice = input("\nMotor [1-2] (Padrão: 1): ").strip()
        engine = "cycles" if eng_choice == "2" else "eevee"

        save_blend_choice = input("\n💾 Deseja também salvar o projeto .blend gerado? (s/N) [Padrão: N]: ").strip().lower()
        save_blend = save_blend_choice == "s"
    else:
        print("\n⚡ Configurações do KiCad Nativo:")
        cpu_total = os.cpu_count() or 4
        w_in = input(f"Número de núcleos CPU para render paralelo [1-{cpu_total}] (Padrão: {cpu_total}): ").strip()
        workers = int(w_in) if w_in.isdigit() and int(w_in) > 0 else cpu_total

        print("Qualidade de Raytracing:")
        print("  [1] Basic (Rápido, ideal para vídeos) [Padrão]")
        print("  [2] High (Raytracing completo com sombras suaves e reflexos)")
        q_in = input("Qualidade [1-2] (Padrão: 1): ").strip()
        kicad_quality = "high" if q_in == "2" else "basic"

    # 3. Estilo de Animação
    print("\n🎨 Escolha o estilo da animação:")
    print("  [1]  Chuva Linear Gravitacional (Rain)       - Ondas de componentes caindo com gravidade e rebote (Padrão)")
    print("  [2]  Onda Radial do Centro (Ripple)          - Expansão concêntrica circular do centro para as bordas")
    print("  [3]  Linha de Montagem SMT por Categoria     - Passivos (R/C/D) -> CIs/Chips -> Conectores/Mecânicos")
    print("  [4]  Vórtice Magnético Espiral 3D (Vortex)   - Componentes descem em redemoinho espiral 3D suave")
    print("  [5]  Visão Explodida Técnica (Exploded)      - Componentes levitam em camadas por categoria e retornam")
    print("  [6]  Varredura Laser Sci-Fi (Laser Scan)     - Materialização diagonal rápida com efeito elástico")
    print("  [7]  Implosão Magnética (Constellation)      - Componentes flutuam em constelação 3D e convergem na placa")
    print("  [8]  Showcase Cinemático 360° (Turntable)    - Giro orbital de 360° com aproximação macro nos detalhes")
    print("  [9]  Fluxo de Energia e Sinal (Signal Flow)  - Montagem seguindo a topologia elétrica (Entrada -> CIs -> Sinais)")
    print("  [10] 🌟 GERAR TODOS OS 9 ESTILOS EM LOTE (All) - Renderiza todas as animações sequencialmente")

    style_choices = {
        "1": "rain", "2": "radial", "3": "assembly", "4": "vortex",
        "5": "exploded", "6": "scan", "7": "implode", "8": "turntable",
        "9": "signal", "10": "all"
    }
    s_choice = input("\nEstilo [1-10] (Padrão: 1): ").strip()
    style = style_choices.get(s_choice, "rain")

    # 4. Faces da Placa (Modo)
    print("\n🔄 Faces da placa a visualizar:")
    print("  [1] Ambas as faces com giro 3D de 180° (Both) [Recomendado]")
    print("  [2] Apenas face superior (Top)")
    print("  [3] Apenas face inferior (Bottom)")
    mode_choices = {"1": "both", "2": "top", "3": "bottom"}
    m_choice = input("\nModo [1-3] (Padrão: 1): ").strip()
    mode = mode_choices.get(m_choice, "both")

    # 5. Resolução
    print("\n📺 Resolução do vídeo:")
    print("  [1] 1080p Full HD (1920×1080) [Equilibrado / Recomendado]")
    print("  [2] 4K Ultra HD (3840×2160) [Qualidade Máxima]")
    print("  [3] 720p HD (1280×720) [Renderização Rápida]")
    res_choices = {"1": "1080p", "2": "4k", "3": "720p"}
    r_choice = input("\nResolução [1-3] (Padrão: 1): ").strip()
    resolution = res_choices.get(r_choice, "1080p")

    # 6. FPS
    print("\n⏱️ Taxa de quadros:")
    print("  [1] 60 fps (Fluidez cinematográfica máxima) [Padrão]")
    print("  [2] 30 fps (Mais rápido para renderizar)")
    fps_choice = input("\nTaxa de quadros [1-2] (Padrão: 1): ").strip()
    fps = 30 if fps_choice == "2" else 60

    # 7. GIF de Preview
    gif_choice = input("\n🎞️ Gerar também arquivos GIF de preview? (S/n) [Padrão: S]: ").strip().lower()
    make_gif = gif_choice != "n"

    # 8. Arquivos de Saída
    pcb_name = os.path.splitext(os.path.basename(pcb_path))[0]
    default_dir = os.path.dirname(os.path.abspath(pcb_path))
    exports_dir = os.path.join(default_dir, "exports", "animacoes")
    if not os.path.exists(exports_dir):
        exports_dir = default_dir

    backend_tag = "blender" if backend == "blender" else "kicad"
    if style == "all":
        out_dest = input(f"\n📁 Diretório para salvar as 4 animações [Padrão: {exports_dir}]: ").strip()
        out_dest = out_dest if out_dest else exports_dir
    else:
        default_mp4 = os.path.join(exports_dir, f"{pcb_name}_{backend_tag}_{style}_{resolution}_{fps}fps.mp4")
        out_mp4 = input(f"\n📁 Caminho do arquivo de vídeo MP4 [Padrão: {default_mp4}]: ").strip()
        out_dest = out_mp4 if out_mp4 else default_mp4

    return {
        "pcb": pcb_path,
        "backend": backend,
        "style": style,
        "mode": mode,
        "engine": engine,
        "res": resolution,
        "fps": fps,
        "save_blend": save_blend,
        "workers": workers,
        "kicad_quality": kicad_quality,
        "output": out_dest,
        "gif": make_gif
    }
