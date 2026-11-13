#!/usr/bin/env python3
"""
KiCad PCB Universal Assembly Animator
-------------------------------------
Gerador universal de animações 3D cinemáticas para projetos KiCad (KiCad 7 e KiCad 8).
Oferece 4 estilos de montagem procedural + opção de gerar todos em lote:
  1. Chuva Linear Gravitacional (Rain)
  2. Onda Radial do Centro (Ripple)
  3. Montagem SMT por Categoria (Pick-and-Place Realista)
  4. Vórtice Magnético 3D (Vortex Espiral)
  5. Todos os 4 Estilos em Lote (All)

Permite execução interativa pelo terminal (perguntando os parâmetros com sugestões
inteligentes) ou via argumentos de linha de comando.
"""

import os
import sys
import re
import math
import glob
import random
import shutil
import argparse
import tempfile
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed

def find_binary(name, macos_path=None):
    found = shutil.which(name)
    if found:
        return found
    if macos_path and os.path.exists(macos_path):
        return macos_path
    return None

KICAD_CLI = find_binary("kicad-cli", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
FFMPEG = find_binary("ffmpeg", "/opt/homebrew/bin/ffmpeg")

ALL_STYLES = ["rain", "radial", "assembly", "vortex"]

STYLE_DESCRIPTIONS = {
    "rain": "Chuva Linear Gravitacional (Rain)",
    "radial": "Onda Radial do Centro (Ripple)",
    "assembly": "Linha de Montagem SMT por Categoria (Pick-and-Place)",
    "vortex": "Vórtice Magnético Espiral 3D (Vortex)"
}

# Categorização de componentes por prefixo de Reference
PASSIVES_PREFIXES = ("R", "C", "L", "D", "LED", "FB", "RV", "RN", "TP")
ICS_PREFIXES = ("U", "IC", "Q", "T", "M", "MOD", "VR")
MECH_PREFIXES = ("J", "P", "TB", "SW", "BZ", "SPK", "F", "DISP", "OLED", "K")

def categorize_ref(ref):
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

class PCBRainAnimator:
    def __init__(self, pcb_path, style="rain", mode="both", fps=60, resolution="4k", workers=None):
        self.pcb_path = os.path.abspath(pcb_path)
        self.style = style.lower()
        self.mode = mode.lower()
        self.fps = fps
        self.workers = workers or max(1, os.cpu_count())

        res_map = {
            "4k": (3840, 2160),
            "1080p": (1920, 1080),
            "720p": (1280, 720)
        }
        if resolution in res_map:
            self.width, self.height = res_map[resolution]
        else:
            w, h = resolution.lower().split("x")
            self.width, self.height = int(w), int(h)

        with open(self.pcb_path, "r", encoding="utf-8") as f:
            self.pcb_txt = f.read()

        self._parse_pcb()

    def _parse_pcb(self):
        pts_x = []
        pts_y = []
        for line in self.pcb_txt.splitlines():
            if "Edge.Cuts" in line:
                for match in re.finditer(r"\((?:start|end|mid|xy|at)\s+([\d\.\-]+)\s+([\d\.\-]+)", line):
                    pts_x.append(float(match.group(1)))
                    pts_y.append(float(match.group(2)))

        fp_pattern = re.compile(r"\t\(footprint\s+\"([^\"]+)\"[\s\S]*?\n\t\)")
        self.footprints = []
        for m in fp_pattern.finditer(self.pcb_txt):
            blk = m.group(0)
            ref_m = re.search(r"\(property \"Reference\" \"([^\"]+)\"", blk)
            ref = ref_m.group(1) if ref_m else "UNKNOWN"
            at_m = re.search(r"\(at ([\d\.\-]+) ([\d\.\-]+)", blk)
            x = float(at_m.group(1)) if at_m else 0.0
            y = float(at_m.group(2)) if at_m else 0.0
            has_model = "(model " in blk
            layer_m = re.search(r"\(layer \"([^\"]+)\"\)", blk)
            layer = layer_m.group(1) if layer_m else "F.Cu"

            pts_x.append(x)
            pts_y.append(y)

            self.footprints.append({
                "ref": ref,
                "layer": layer,
                "x": x,
                "y": y,
                "category": categorize_ref(ref),
                "blk": blk,
                "has_model": has_model,
                "start": m.start(),
                "end": m.end()
            })

        self.min_x = min(pts_x) if pts_x else 0.0
        self.max_x = max(pts_x) if pts_x else 100.0
        self.min_y = min(pts_y) if pts_y else 0.0
        self.max_y = max(pts_y) if pts_y else 100.0
        self.center_x = (self.min_x + self.max_x) / 2.0
        self.center_y = (self.min_y + self.max_y) / 2.0
        self.board_width = max(10.0, self.max_x - self.min_x)
        self.board_height = max(10.0, self.max_y - self.min_y)
        self.max_radius = math.hypot(self.board_width / 2.0, self.board_height / 2.0)

        self.prefix = self.pcb_txt[:self.footprints[0]["start"]]
        self.suffix = self.pcb_txt[self.footprints[-1]["end"]:]

        self.top_models = [fp for fp in self.footprints if fp["layer"] == "F.Cu" and fp["has_model"] and not fp["ref"].startswith("H")]
        self.bot_models = [fp for fp in self.footprints if fp["layer"] == "B.Cu" and fp["has_model"] and not fp["ref"].startswith("H")]

    def generate(self, output_mp4, output_gif=None):
        temp_dir = tempfile.mkdtemp(prefix="kicad_anim_")
        try:
            total_frames = self._calculate_timeline()
            print("\n" + "="*60)
            print("🚀 INICIANDO RENDERIZAÇÃO DA ANIMAÇÃO 3D")
            print("="*60)
            print(f"📁 Projeto PCB   : {os.path.basename(self.pcb_path)}")
            print(f"📐 Dimensões     : {self.board_width:.1f} mm × {self.board_height:.1f} mm")
            print(f"🧩 Componentes 3D: Top={len(self.top_models)} | Bottom={len(self.bot_models)}")
            print(f"🎨 Estilo        : {STYLE_DESCRIPTIONS.get(self.style, self.style)}")
            print(f"🔄 Modo          : {self.mode.upper()}")
            print(f"📺 Resolução     : {self.width}×{self.height} @ {self.fps} fps")
            print(f"⏱️ Duração       : {total_frames} frames ({total_frames/self.fps:.1f} segundos)")
            print(f"⚡ Núcleos CPU   : {self.workers} workers em paralelo")
            print("="*60 + "\n")

            self._render_all_frames(temp_dir, total_frames)

            print("\n🎬 Codificando vídeo MP4 final com FFmpeg...")
            self._encode_video(temp_dir, total_frames, output_mp4)

            if output_gif:
                print("🖼️ Gerando GIF otimizado de preview...")
                self._encode_gif(output_mp4, output_gif)

            print("\n" + "-"*60)
            print("✅ ESTILO CONCLUÍDO COM SUCESSO!")
            print(f"📹 Vídeo MP4 : {os.path.abspath(output_mp4)}")
            if output_gif:
                print(f"🎞️ GIF        : {os.path.abspath(output_gif)}")
            print("-"*60 + "\n")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _calculate_timeline(self):
        if self.mode == "both":
            self.total_frames = int(8.0 * self.fps)
            self.act1_end = int(1.33 * self.fps)
            self.act2_end = int(2.67 * self.fps)
            self.act3_end = int(6.33 * self.fps)
        elif self.mode == "top":
            self.total_frames = int(5.0 * self.fps)
            self.act1_end = 0
            self.act2_end = 0
            self.act3_end = int(4.0 * self.fps)
        else: # bottom
            self.total_frames = int(5.0 * self.fps)
            self.act1_end = int(4.0 * self.fps)
            self.act2_end = 0
            self.act3_end = 0

        random.seed(42)
        self.spawn_timings = {}

        for fp in self.footprints:
            ref = fp["ref"]
            if not fp["has_model"] or ref.startswith("H"):
                self.spawn_timings[ref] = None
                continue

            if self.style == "rain":
                norm = (fp["x"] - self.min_x) / self.board_width
            elif self.style == "radial":
                dist = math.hypot(fp["x"] - self.center_x, fp["y"] - self.center_y)
                norm = dist / max(1.0, self.max_radius)
            elif self.style == "assembly":
                cat = fp["category"] # 1=passivo, 2=CI, 3=mecanico
                norm_x = (fp["x"] - self.min_x) / self.board_width
                if cat == 1:
                    norm = 0.0 + 0.30 * norm_x
                elif cat == 2:
                    norm = 0.35 + 0.30 * norm_x
                else:
                    norm = 0.70 + 0.30 * norm_x
            elif self.style == "vortex":
                dist = math.hypot(fp["x"] - self.center_x, fp["y"] - self.center_y)
                norm_r = dist / max(1.0, self.max_radius)
                norm_x = (fp["x"] - self.min_x) / self.board_width
                norm = 0.6 * norm_x + 0.4 * norm_r
            else:
                norm = (fp["x"] - self.min_x) / self.board_width

            norm = max(0.0, min(1.0, norm))
            jitter = random.uniform(-5.0, 5.0)

            if fp["layer"] == "B.Cu":
                if self.mode == "both":
                    spawn = 15.0 + norm * (self.act1_end - 45.0) + jitter
                else:
                    spawn = 20.0 + norm * (self.act1_end - 40.0) + jitter
            else:
                if self.mode == "both":
                    spawn = self.act2_end + 15.0 + norm * (self.act3_end - self.act2_end - 45.0) + jitter
                else:
                    spawn = 20.0 + norm * (self.act3_end - 40.0) + jitter

            self.spawn_timings[ref] = max(0.0, spawn)

        return self.total_frames

    def _compute_component_state(self, fp, frame_idx):
        ref = fp["ref"]
        spawn_f = self.spawn_timings.get(ref)

        if spawn_f is None:
            return True, 0.0, 0.0, 0.0

        if frame_idx < spawn_f:
            return False, 0.0, 0.0, 0.0

        df = frame_idx - spawn_f
        fall_dur = int(0.33 * self.fps)
        bounce_dur = int(0.13 * self.fps)

        if df < fall_dur:
            p = df / float(fall_dur)
            z = 55.0 * (1.0 - p * p)

            if self.style == "vortex":
                radius = 18.0 * (1.0 - p)
                theta = 3.5 * math.pi * (1.0 - p)
                dx = radius * math.cos(theta)
                dy = radius * math.sin(theta)
            elif self.style == "radial":
                dir_x = (fp["x"] - self.center_x) / max(1.0, self.max_radius)
                dir_y = (fp["y"] - self.center_y) / max(1.0, self.max_radius)
                disp = 6.0 * (1.0 - p)
                dx = dir_x * disp
                dy = dir_y * disp
            else:
                dx = 0.0
                dy = 0.0
            return True, dx, dy, z

        elif df < fall_dur + bounce_dur:
            p_b = (df - fall_dur) / float(bounce_dur)
            z = 1.4 * math.sin(p_b * math.pi) * (1.0 - p_b)
            return True, 0.0, 0.0, z
        else:
            return True, 0.0, 0.0, 0.0

    def _get_frame_camera(self, frame):
        base_zoom = 1.25

        if self.mode == "both":
            if frame < self.act1_end:
                p = frame / float(self.act1_end)
                rx = 148.0 - 2.0 * p
                rz = 28.0 + 1.0 * p
                zm = base_zoom * 1.04
            elif frame < self.act2_end:
                t = (frame - self.act1_end) / float(self.act2_end - self.act1_end)
                p = t * t * t * (t * (t * 6.0 - 15.0) + 10.0)
                rx = 148.0 - 180.0 * p
                rz = 29.0 - 3.0 * p
                zm = base_zoom * (1.04 - 0.06 * math.sin(p * math.pi))
            elif frame < self.act3_end:
                p = (frame - self.act2_end) / float(self.act3_end - self.act2_end)
                rx = -32.0 + 2.5 * p
                rz = 26.0 + 3.0 * p
                zm = base_zoom * (0.98 + 0.04 * p)
            else:
                p = (frame - self.act3_end) / float(self.total_frames - self.act3_end)
                rx = -29.5 + 1.8 * math.sin(p * math.pi)
                rz = 29.0 + 2.0 * p
                zm = base_zoom * (1.02 + 0.02 * math.cos(p * math.pi))
        elif self.mode == "top":
            p = frame / float(self.total_frames)
            rx = -34.0 + 3.0 * p
            rz = 26.0 + 4.0 * p
            zm = base_zoom * (0.98 + 0.05 * p)
        else:
            p = frame / float(self.total_frames)
            rx = 148.0 - 3.0 * p
            rz = 28.0 + 4.0 * p
            zm = base_zoom * (1.04 + 0.05 * p)

        return rx, rz, zm

    def _render_frame_worker(self, temp_dir, frame_idx):
        frame_pcb = f"{temp_dir}/board_{frame_idx:04d}.kicad_pcb"
        frame_png = f"{temp_dir}/frame_{frame_idx:04d}.png"

        new_fps = []
        for fp in self.footprints:
            blk = fp["blk"]
            visible, dx, dy, dz = self._compute_component_state(fp, frame_idx)

            if not visible:
                no_model = re.sub(r"\t\t\(model\s+\"[^\"]*\"[\s\S]*?\n\t\t\)\n", "", blk)
                new_fps.append(no_model)
            else:
                def repl_offset(m):
                    ox = float(m.group(1))
                    oy = float(m.group(2))
                    oz = float(m.group(3))
                    return f"(offset (xyz {ox + dx:.2f} {oy + dy:.2f} {oz + dz:.2f}))"

                mod_blk = re.sub(
                    r"\(offset\s*\(xyz\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s*\)\s*\)",
                    repl_offset,
                    blk
                )
                new_fps.append(mod_blk)

        full_txt = self.prefix + "".join(new_fps) + self.suffix
        with open(frame_pcb, "w", encoding="utf-8") as f:
            f.write(full_txt)

        rx, rz, zm = self._get_frame_camera(frame_idx)
        cmd = [
            KICAD_CLI, "pcb", "render",
            "--rotate", f"{rx:.2f},0,{rz:.2f}",
            "--perspective",
            "--zoom", f"{zm:.3f}",
            "--width", str(self.width),
            "--height", str(self.height),
            "--quality", "basic",
            "-o", frame_png,
            frame_pcb
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        for ext in [".kicad_pcb", ".kicad_prl"]:
            p = frame_pcb.replace(".kicad_pcb", ext)
            if os.path.exists(p):
                try: os.remove(p)
                except OSError: pass

        return frame_idx

    def _render_all_frames(self, temp_dir, total_frames):
        completed = 0
        with ProcessPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(self._render_frame_worker, temp_dir, i): i for i in range(total_frames)}
            for f in as_completed(futures):
                f.result()
                completed += 1
                if completed % (max(1, total_frames // 10)) == 0 or completed == total_frames:
                    pct = completed / total_frames * 100.0
                    print(f"⏳ Progresso: [{completed:03d}/{total_frames:03d}] {pct:5.1f}% renderizado")

    def _encode_video(self, temp_dir, total_frames, output_mp4):
        duration = total_frames / float(self.fps)
        os.makedirs(os.path.dirname(os.path.abspath(output_mp4)), exist_ok=True)
        cmd = [
            FFMPEG, "-y",
            "-framerate", str(self.fps),
            "-i", f"{temp_dir}/frame_%04d.png",
            "-filter_complex", f"color=c=0x0f172a:s={self.width}x{self.height}:d={duration:.2f}:r={self.fps}[bg];[bg][0:v]overlay=x=(W-w)/2:y=(H-h)/2:shortest=1:format=auto[v]",
            "-map", "[v]",
            "-r", str(self.fps),
            "-c:v", "libx264",
            "-profile:v", "high",
            "-crf", "17",
            "-pix_fmt", "yuv420p",
            output_mp4
        ]
        subprocess.run(cmd, check=True)

    def _encode_gif(self, input_mp4, output_gif):
        os.makedirs(os.path.dirname(os.path.abspath(output_gif)), exist_ok=True)
        cmd = [
            FFMPEG, "-y",
            "-i", input_mp4,
            "-vf", "fps=30,scale=1000:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=256:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3",
            output_gif
        ]
        subprocess.run(cmd, check=True)

def find_available_pcbs():
    found = glob.glob("**/*.kicad_pcb", recursive=True) + glob.glob("*.kicad_pcb")
    clean = [p for p in set(found) if not p.endswith(".bak") and ".history" not in p]
    return sorted(clean)

def prompt_terminal_interactive():
    print("\n" + "="*60)
    print("🛠️  GERADOR UNIVERSAL DE ANIMAÇÃO 3D DE PCB (KICAD)")
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

    # 2. Estilo de Animação
    print("\n🎨 Escolha o estilo da animação:")
    print("  [1] Chuva Linear Gravitacional (Rain)       - Ondas de componentes caindo com gravidade e rebote (Padrão)")
    print("  [2] Onda Radial do Centro (Ripple)          - Expansão concêntrica circular do centro para as bordas")
    print("  [3] Linha de Montagem SMT por Categoria     - Passivos (R/C/D) -> CIs/Chips -> Conectores/Mecânicos")
    print("  [4] Vórtice Magnético Espiral 3D (Vortex)   - Componentes descem em redemoinho espiral 3D suave")
    print("  [5] 🌟 GERAR TODOS OS 4 ESTILOS EM LOTE (All) - Renderiza todas as animações sequencialmente")

    style_choices = {"1": "rain", "2": "radial", "3": "assembly", "4": "vortex", "5": "all"}
    s_choice = input("\nEstilo [1-5] (Padrão: 1): ").strip()
    style = style_choices.get(s_choice, "rain")

    # 3. Faces da Placa (Modo)
    print("\n🔄 Faces da placa a visualizar:")
    print("  [1] Ambas as faces com giro 3D de 180° (Both) [Recomendado]")
    print("  [2] Apenas face superior (Top)")
    print("  [3] Apenas face inferior (Bottom)")
    mode_choices = {"1": "both", "2": "top", "3": "bottom"}
    m_choice = input("\nModo [1-3] (Padrão: 1): ").strip()
    mode = mode_choices.get(m_choice, "both")

    # 4. Resolução
    print("\n📺 Resolução do vídeo:")
    print("  [1] 4K Ultra HD (3840×2160) [Qualidade Máxima]")
    print("  [2] 1080p Full HD (1920×1080) [Equilibrado]")
    print("  [3] 720p HD (1280×720) [Renderização Rápida]")
    res_choices = {"1": "4k", "2": "1080p", "3": "720p"}
    r_choice = input("\nResolução [1-3] (Padrão: 1): ").strip()
    resolution = res_choices.get(r_choice, "4k")

    # 5. FPS
    print("\n⏱️ Taxa de quadros:")
    print("  [1] 60 fps (Fluidez cinematográfica máxima) [Padrão]")
    print("  [2] 30 fps (Mais rápido para renderizar)")
    fps_choice = input("\nTaxa de quadros [1-2] (Padrão: 1): ").strip()
    fps = 30 if fps_choice == "2" else 60

    # 6. GIF de Preview
    gif_choice = input("\n🎞️ Gerar também arquivos GIF de preview? (S/n) [Padrão: S]: ").strip().lower()
    make_gif = gif_choice != "n"

    # 7. Arquivos de Saída
    pcb_name = os.path.splitext(os.path.basename(pcb_path))[0]
    default_dir = os.path.dirname(os.path.abspath(pcb_path))
    exports_dir = os.path.join(default_dir, "exports", "animacoes")
    if not os.path.exists(exports_dir):
        exports_dir = default_dir

    if style == "all":
        out_dest = input(f"\n📁 Diretório para salvar as 4 animações [Padrão: {exports_dir}]: ").strip()
        out_dest = out_dest if out_dest else exports_dir
    else:
        default_mp4 = os.path.join(exports_dir, f"{pcb_name}_{style}_{resolution}_{fps}fps.mp4")
        out_mp4 = input(f"\n📁 Caminho do arquivo de vídeo MP4 [Padrão: {default_mp4}]: ").strip()
        out_dest = out_mp4 if out_mp4 else default_mp4

    return {
        "pcb": pcb_path,
        "style": style,
        "mode": mode,
        "res": resolution,
        "fps": fps,
        "output": out_dest,
        "gif": make_gif
    }

def resolve_jobs(pcb_path, style, resolution, fps, out_dest, make_gif):
    pcb_name = os.path.splitext(os.path.basename(pcb_path))[0]
    default_dir = os.path.dirname(os.path.abspath(pcb_path))
    exports_dir = os.path.join(default_dir, "exports", "animacoes")
    target_dir = exports_dir if os.path.exists(exports_dir) else default_dir

    styles_to_run = ALL_STYLES if style == "all" else [style]
    jobs = []

    if style == "all":
        base_dir = out_dest if (out_dest and (os.path.isdir(out_dest) or not out_dest.endswith(".mp4"))) else target_dir
        os.makedirs(base_dir, exist_ok=True)
        for s in styles_to_run:
            mp4_path = os.path.join(base_dir, f"{pcb_name}_{s}_{resolution}_{fps}fps.mp4")
            gif_path = os.path.join(base_dir, f"{pcb_name}_{s}_{resolution}_{fps}fps.gif") if make_gif else None
            jobs.append((s, mp4_path, gif_path))
    else:
        if not out_dest:
            mp4_path = os.path.join(target_dir, f"{pcb_name}_{style}_{resolution}_{fps}fps.mp4")
        elif os.path.isdir(out_dest):
            mp4_path = os.path.join(out_dest, f"{pcb_name}_{style}_{resolution}_{fps}fps.mp4")
        else:
            mp4_path = out_dest

        gif_path = os.path.splitext(mp4_path)[0] + ".gif" if make_gif else None
        jobs.append((style, mp4_path, gif_path))

    return jobs

def main():
    parser = argparse.ArgumentParser(description="KiCad PCB Universal Assembly Animator")
    parser.add_argument("--pcb", help="Caminho do arquivo .kicad_pcb")
    parser.add_argument("--style", choices=["rain", "radial", "assembly", "vortex", "all"], default="rain", help="Estilo da animacao ou 'all' para gerar todos")
    parser.add_argument("--mode", choices=["both", "top", "bottom"], default="both", help="Faces a animar")
    parser.add_argument("--output", "-o", help="Arquivo ou pasta de saida")
    parser.add_argument("--gif", action="store_true", help="Gerar arquivo(s) GIF de preview")
    parser.add_argument("--res", default="4k", help="Resolucao: 4k, 1080p, 720p ou WxH")
    parser.add_argument("--fps", type=int, default=60, help="Taxa de quadros (padrao: 60)")
    parser.add_argument("--workers", type=int, default=None, help="Numero de nucleos de CPU a utilizar")
    parser.add_argument("--interactive", "-i", action="store_true", help="Executar no modo interativo pelo terminal")

    args = parser.parse_args()

    if not KICAD_CLI:
        print("❌ Erro: 'kicad-cli' não foi encontrado no sistema.", file=sys.stderr)
        sys.exit(1)
    if not FFMPEG:
        print("❌ Erro: 'ffmpeg' não foi encontrado no sistema.", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) == 1 or args.interactive or not args.pcb:
        params = prompt_terminal_interactive()
        pcb_path = params["pcb"]
        style = params["style"]
        mode = params["mode"]
        resolution = params["res"]
        fps = params["fps"]
        out_dest = params["output"]
        make_gif = params["gif"]
        workers = args.workers
    else:
        pcb_path = args.pcb
        style = args.style
        mode = args.mode
        resolution = args.res
        fps = args.fps
        out_dest = args.output
        make_gif = args.gif
        workers = args.workers

    jobs = resolve_jobs(pcb_path, style, resolution, fps, out_dest, make_gif)

    print("\n" + "="*60)
    print(f"📦 PLANEJAMENTO: {len(jobs)} ANIMAÇÃO(ÕES) A SEREM PROCESSADAS")
    print("="*60)
    for idx, (s, mp4, gif) in enumerate(jobs, 1):
        print(f" [{idx}] {STYLE_DESCRIPTIONS.get(s, s)}")
        print(f"     MP4: {mp4}")
        if gif:
            print(f"     GIF: {gif}")
    print("="*60)

    for idx, (s, mp4, gif) in enumerate(jobs, 1):
        if len(jobs) > 1:
            print(f"\n{'#'*60}")
            print(f"🎬 EXECUTANDO TRABALHO [{idx}/{len(jobs)}]: {s.upper()}")
            print(f"{'#'*60}")

        animator = PCBRainAnimator(
            pcb_path=pcb_path,
            style=s,
            mode=mode,
            fps=fps,
            resolution=resolution,
            workers=workers
        )
        animator.generate(mp4, gif)

    if len(jobs) > 1:
        print("\n" + "="*60)
        print("🎉 TODOS OS TRABALHOS EM LOTE FORAM CONCLUÍDOS COM SUCESSO!")
        print("="*60)
        for idx, (s, mp4, gif) in enumerate(jobs, 1):
            print(f" [{idx}] {STYLE_DESCRIPTIONS.get(s, s)}:")
            print(f"     📹 {mp4}")
            if gif:
                print(f"     🎞️ {gif}")
        print("="*60 + "\n")

if __name__ == "__main__":
    main()
