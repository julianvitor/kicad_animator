#!/usr/bin/env python3
"""
KiCad PCB Universal Assembly Animator - Ponto de Entrada Principal (main.py)
---------------------------------------------------------------------------
Gerador universal de animações 3D cinemáticas para placas KiCad (KiCad 7, 8, 9 e 10).
Oferece 2 motores de renderização integrados:
  1. Blender 3D (GPU PBR / EEVEE & Cycles com gerenciamento AgX)
  2. KiCad Nativo (kicad-cli / CPU Raytracing paralelo)

Modos de uso:
  - Desktop Web App: python3 main.py (ou python3 main.py --gui)
  - Terminal Interativo: python3 main.py -i
  - Linha de Comando (CLI): python3 main.py --pcb placa.kicad_pcb --backend blender ...
"""

import os
import sys
import argparse
import tempfile
import subprocess

# Auto-elevação para o ambiente Poetry / .venv local se o Python atual não possuir as dependências (bpy/pywebview)
script_dir = os.path.dirname(os.path.abspath(__file__))
is_win = sys.platform == "win32"
venv_candidates = [
    os.path.join(script_dir, ".venv", "Scripts", "python.exe") if is_win else os.path.join(script_dir, ".venv", "bin", "python"),
    os.path.join(script_dir, ".venv", "bin", "python3")
]
target_py = next((p for p in venv_candidates if os.path.exists(p)), None)

if target_py and os.path.abspath(sys.executable) != os.path.abspath(target_py):
    try:
        import bpy
        import webview
    except ImportError:
        sys.exit(subprocess.call([target_py, os.path.abspath(__file__)] + sys.argv[1:], cwd=script_dir))

from core.config import (
    KICAD_CLI, FFMPEG, BLENDER_BIN, UV_BIN, POETRY_BIN, HAS_BPY, STYLE_DESCRIPTIONS
)
from core.parser import PCBMetaParser
from core.jobs import resolve_jobs, prompt_terminal_interactive
from engines.kicad_engine import KiCadNativePCBAnimator

def main():
    if "--" in sys.argv:
        raw_args = sys.argv[sys.argv.index("--") + 1:]
    else:
        raw_args = sys.argv[1:]

    parser = argparse.ArgumentParser(description="KiCad PCB Universal Assembly Animator (Blender & KiCad CLI)")
    parser.add_argument("--pcb", help="Caminho do arquivo .kicad_pcb")
    parser.add_argument("--backend", choices=["blender", "kicad"], default="blender", help="Motor de render: 'blender' (GPU PBR) ou 'kicad' (KiCad CLI raytracing)")
    parser.add_argument("--style", choices=["rain", "radial", "assembly", "vortex", "all"], default="rain", help="Estilo da animação ou 'all' para gerar todos")
    parser.add_argument("--mode", choices=["both", "top", "bottom"], default="both", help="Faces a animar")
    parser.add_argument("--engine", choices=["eevee", "cycles"], default="eevee", help="Motor de renderização do Blender (padrão: eevee)")
    parser.add_argument("--samples", type=int, default=32, help="Número de amostras de render (samples)")
    parser.add_argument("--light-intensity", type=float, default=1.0, help="Multiplicador de intensidade das luzes de estúdio (padrão: 1.0)")
    parser.add_argument("--still-frame", type=int, nargs="?", const=-1, default=None, help="Renderizar apenas um frame estático para preview (ex: --still-frame ou --still-frame 90)")
    parser.add_argument("--save-blend", action="store_true", help="Salvar arquivo(s) de projeto .blend")
    parser.add_argument("--workers", type=int, default=None, help="Número de workers/núcleos de CPU para KiCad Nativo")
    parser.add_argument("--kicad-quality", choices=["basic", "high"], default="basic", help="Qualidade de render do kicad-cli (basic ou high)")
    parser.add_argument("--output", "-o", help="Arquivo ou pasta de saída")
    parser.add_argument("--gif", action="store_true", help="Gerar arquivo(s) GIF de preview")
    parser.add_argument("--res", default="1080p", help="Resolução: 4k, 1080p, 720p ou WxH")
    parser.add_argument("--fps", type=int, default=60, help="Taxa de quadros (padrão: 60)")
    parser.add_argument("--gui", action="store_true", help="Iniciar interface gráfica Desktop Web (pywebview)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Executar no modo interativo pelo terminal")

    args = parser.parse_args(raw_args)

    # 1. Se executado sem argumentos ou com flag --gui, abre a Interface Gráfica Desktop Web
    if len(raw_args) == 0 or args.gui:
        try:
            from ui.app import launch_ui
            launch_ui()
            return
        except Exception as e:
            print(f"❌ Erro ao iniciar interface gráfica: {e}", file=sys.stderr)
            print("💡 Tentando modo interativo no terminal como fallback...\n")

    # 2. Verificação de Runtime para o Blender (se backend == "blender"):
    if args.backend == "blender" and not HAS_BPY:
        # Se for executável standalone empacotado (.app ou .exe), não tenta invocar ferramentas de dev
        if getattr(sys, "frozen", False):
            if BLENDER_BIN:
                cmd = [BLENDER_BIN, "--background", "--python", os.path.abspath(__file__), "--"] + raw_args
                sys.exit(subprocess.call(cmd, cwd=script_dir))
            else:
                print("\n❌ Erro: O motor Blender não foi encontrado no sistema.", file=sys.stderr)
                print("💡 O executável standalone requer o aplicativo Blender instalado (ex: /Applications/Blender.app ou no PATH).", file=sys.stderr)
                print("💡 Alternativa: Selecione o motor 'KiCad Nativo (CPU)' no painel esquerdo, ou execute via './run_unix.sh' que roda com o motor bpy integrado.\n", file=sys.stderr)
                sys.exit(1)

        # Modo desenvolvimento / código-fonte:
        if target_py and os.path.exists(target_py) and os.path.abspath(sys.executable) != os.path.abspath(target_py):
            cmd = [target_py, os.path.abspath(__file__)] + raw_args
            sys.exit(subprocess.call(cmd, cwd=script_dir))

        if POETRY_BIN and "POETRY_ACTIVE" not in os.environ and os.path.exists(os.path.join(script_dir, "pyproject.toml")):
            cmd = [POETRY_BIN, "--directory", script_dir, "run", "python", os.path.abspath(__file__)] + raw_args
            sys.exit(subprocess.call(cmd, cwd=script_dir))

        if UV_BIN and os.path.exists(os.path.join(script_dir, "pyproject.toml")):
            cmd = [UV_BIN, "run", "--directory", script_dir, "--python", "3.13", "--with", "bpy", "python", os.path.abspath(__file__)] + raw_args
            sys.exit(subprocess.call(cmd, cwd=script_dir))

        if BLENDER_BIN:
            cmd = [BLENDER_BIN, "--background", "--python", os.path.abspath(__file__), "--"] + raw_args
            sys.exit(subprocess.call(cmd, cwd=script_dir))

        print("\n❌ Erro: A biblioteca 'bpy' ou o Blender não foram encontrados para o motor Blender.", file=sys.stderr)
        print("💡 Dica: Você pode executar com o motor KiCad Nativo adicionando '--backend kicad'.\n", file=sys.stderr)
        sys.exit(1)

    # 3. Verificação de binários externos essenciais
    if not KICAD_CLI:
        print("❌ Erro: 'kicad-cli' não foi encontrado no sistema.", file=sys.stderr)
        sys.exit(1)
    if not FFMPEG:
        print("❌ Erro: 'ffmpeg' não foi encontrado no sistema.", file=sys.stderr)
        sys.exit(1)

    # 4. Modo Interativo no Terminal
    if args.interactive or not args.pcb:
        params = prompt_terminal_interactive()
        pcb_path = params["pcb"]
        backend = params["backend"]
        style = params["style"]
        mode = params["mode"]
        engine = params["engine"]
        resolution = params["res"]
        fps = params["fps"]
        save_blend = params["save_blend"]
        workers = params["workers"]
        kicad_quality = params["kicad_quality"]
        out_dest = params["output"]
        make_gif = params["gif"]
        samples = args.samples
        light_intensity = args.light_intensity
    else:
        pcb_path = args.pcb
        backend = args.backend
        style = args.style
        mode = args.mode
        engine = args.engine
        resolution = args.res
        fps = args.fps
        save_blend = args.save_blend
        workers = args.workers
        kicad_quality = args.kicad_quality
        out_dest = args.output
        make_gif = args.gif
        samples = args.samples
        light_intensity = args.light_intensity

    pcb_path = os.path.abspath(pcb_path)
    if not os.path.exists(pcb_path):
        print(f"❌ Erro: Arquivo PCB '{pcb_path}' não foi encontrado.", file=sys.stderr)
        sys.exit(1)

    jobs = resolve_jobs(pcb_path, style, resolution, fps, out_dest, make_gif, save_blend, backend=backend)

    # -----------------------------------------------------------------------
    # Execução com Motor KiCad Nativo (kicad-cli)
    # -----------------------------------------------------------------------
    if backend == "kicad":
        if args.still_frame is not None:
            preview_png = out_dest if (out_dest and out_dest.lower().endswith(".png")) else os.path.splitext(out_dest or pcb_path)[0] + "_preview.png"
            animator = KiCadNativePCBAnimator(
                pcb_path=pcb_path,
                style=style if style != "all" else "rain",
                mode=mode,
                fps=fps,
                resolution=resolution,
                workers=workers,
                quality=kicad_quality
            )
            animator.render_single_frame(args.still_frame, preview_png)
            return

        print("\n" + "="*60, flush=True)
        print(f"📦 PLANEJAMENTO: {len(jobs)} ANIMAÇÃO(ÕES) (KICAD NATIVO CPU)", flush=True)
        print("="*60, flush=True)
        for idx, (s, mp4, gif, _) in enumerate(jobs, 1):
            print(f" [{idx}] {STYLE_DESCRIPTIONS.get(s, s)}", flush=True)
            print(f"     MP4: {mp4}", flush=True)
            if gif:
                print(f"     GIF: {gif}", flush=True)
        print("="*60, flush=True)

        for idx, (s, mp4, gif, _) in enumerate(jobs, 1):
            if len(jobs) > 1:
                print(f"\n{'#'*60}", flush=True)
                print(f"🎬 EXECUTANDO TRABALHO [{idx}/{len(jobs)}]: {s.upper()} (KICAD NATIVO)", flush=True)
                print(f"{'#'*60}", flush=True)

            animator = KiCadNativePCBAnimator(
                pcb_path=pcb_path,
                style=s,
                mode=mode,
                fps=fps,
                resolution=resolution,
                workers=workers,
                quality=kicad_quality
            )
            animator.generate(mp4, gif)

        if len(jobs) > 1:
            print("\n" + "="*60, flush=True)
            print("🎉 TODOS OS TRABALHOS EM LOTE FORAM CONCLUÍDOS COM SUCESSO!", flush=True)
            print("="*60, flush=True)
            for idx, (s, mp4, gif, _) in enumerate(jobs, 1):
                print(f" [{idx}] {STYLE_DESCRIPTIONS.get(s, s)}:", flush=True)
                print(f"     📹 {mp4}", flush=True)
                if gif:
                    print(f"     🎞️ {gif}", flush=True)
            print("="*60 + "\n", flush=True)
        return

    # -----------------------------------------------------------------------
    # Execução com Motor Blender 3D (bpy)
    # -----------------------------------------------------------------------
    from engines.blender_engine import BlenderPCBAnimator, export_kicad_glb

    pcb_meta = PCBMetaParser(pcb_path)
    temp_glb = tempfile.mktemp(prefix="board_export_", suffix=".glb")
    try:
        export_kicad_glb(pcb_path, temp_glb)

        if args.still_frame is not None:
            preview_png = out_dest if (out_dest and out_dest.lower().endswith(".png")) else os.path.splitext(out_dest or pcb_path)[0] + "_preview.png"
            animator = BlenderPCBAnimator(
                pcb_path=pcb_path,
                glb_path=temp_glb,
                pcb_meta=pcb_meta,
                style=style if style != "all" else "rain",
                mode=mode,
                fps=fps,
                resolution=resolution,
                engine=engine,
                samples=samples,
                light_intensity=light_intensity
            )
            animator.render_single_frame(args.still_frame, preview_png)
            return

        print("\n" + "="*60, flush=True)
        print(f"📦 PLANEJAMENTO: {len(jobs)} ANIMAÇÃO(ÕES) (BLENDER / BPY)", flush=True)
        print("="*60, flush=True)
        for idx, (s, mp4, gif, blend) in enumerate(jobs, 1):
            print(f" [{idx}] {STYLE_DESCRIPTIONS.get(s, s)}", flush=True)
            print(f"     MP4: {mp4}", flush=True)
            if gif:
                print(f"     GIF: {gif}", flush=True)
            if blend:
                print(f"     BLEND: {blend}", flush=True)
        print("="*60, flush=True)

        for idx, (s, mp4, gif, blend) in enumerate(jobs, 1):
            if len(jobs) > 1:
                print(f"\n{'#'*60}", flush=True)
                print(f"🎬 EXECUTANDO TRABALHO [{idx}/{len(jobs)}]: {s.upper()} (BLENDER)", flush=True)
                print(f"{'#'*60}", flush=True)

            animator = BlenderPCBAnimator(
                pcb_path=pcb_path,
                glb_path=temp_glb,
                pcb_meta=pcb_meta,
                style=s,
                mode=mode,
                fps=fps,
                resolution=resolution,
                engine=engine,
                samples=samples,
                light_intensity=light_intensity,
                save_blend=blend
            )
            animator.generate(mp4, gif)

        if len(jobs) > 1:
            print("\n" + "="*60, flush=True)
            print("🎉 TODOS OS TRABALHOS EM LOTE FORAM CONCLUÍDOS COM SUCESSO!", flush=True)
            print("="*60, flush=True)
            for idx, (s, mp4, gif, blend) in enumerate(jobs, 1):
                print(f" [{idx}] {STYLE_DESCRIPTIONS.get(s, s)}:", flush=True)
                print(f"     📹 {mp4}", flush=True)
                if gif:
                    print(f"     🎞️ {gif}", flush=True)
                if blend:
                    print(f"     💾 {blend}", flush=True)
            print("="*60 + "\n", flush=True)

    finally:
        if os.path.exists(temp_glb):
            try: os.remove(temp_glb)
            except OSError: pass

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
