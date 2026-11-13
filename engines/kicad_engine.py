"""
KiCad Animator - Motor de Renderização KiCad Nativo (kicad-cli / CPU Raytracing)
"""

import os
import re
import math
import random
import shutil
import tempfile
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed

from core.config import (
    KICAD_CLI, FFMPEG, RES_MAP, STYLE_DESCRIPTIONS, categorize_ref
)
from core.progress import RenderProgressBar

class KiCadNativePCBAnimator:
    def __init__(self, pcb_path, style="rain", mode="both", fps=60, resolution="1080p", workers=None, quality="basic"):
        self.pcb_path = os.path.abspath(pcb_path)
        self.style = style.lower()
        self.mode = mode.lower()
        self.fps = fps
        self.workers = workers or max(1, os.cpu_count())
        self.quality = quality

        if resolution in RES_MAP:
            self.width, self.height = RES_MAP[resolution]
        else:
            w, h = resolution.lower().split("x")
            self.width, self.height = int(w), int(h)

        with open(self.pcb_path, "r", encoding="utf-8", errors="ignore") as f:
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

        self.prefix = self.pcb_txt[:self.footprints[0]["start"]] if self.footprints else self.pcb_txt
        self.suffix = self.pcb_txt[self.footprints[-1]["end"]:] if self.footprints else ""

        self.top_models = [fp for fp in self.footprints if fp["layer"] == "F.Cu" and fp["has_model"] and not fp["ref"].startswith("H")]
        self.bot_models = [fp for fp in self.footprints if fp["layer"] == "B.Cu" and fp["has_model"] and not fp["ref"].startswith("H")]

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
        else:
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
                cat = fp["category"]
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
        base_zoom = 1.18

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
            "--quality", self.quality,
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
        pbar = RenderProgressBar(total_frames, prefix="KiCad Nativo Render")
        with ProcessPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(self._render_frame_worker, temp_dir, i): i for i in range(total_frames)}
            for f in as_completed(futures):
                f.result()
                completed += 1
                pbar.update(current=completed)
        pbar.close("Renderização de quadros finalizada")

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
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    def _encode_gif(self, input_mp4, output_gif):
        os.makedirs(os.path.dirname(os.path.abspath(output_gif)), exist_ok=True)
        cmd = [
            FFMPEG, "-y",
            "-i", input_mp4,
            "-vf", "fps=30,scale=1000:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=256:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3",
            output_gif
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    def generate(self, output_mp4, output_gif=None):
        temp_dir = tempfile.mkdtemp(prefix="kicad_anim_")
        try:
            total_frames = self._calculate_timeline()
            print("\n" + "="*60, flush=True)
            print("🚀 INICIANDO RENDERIZAÇÃO DA ANIMAÇÃO 3D (KICAD NATIVO / CPU)", flush=True)
            print("="*60, flush=True)
            print(f"📁 Projeto PCB   : {os.path.basename(self.pcb_path)}", flush=True)
            print(f"📐 Dimensões     : {self.board_width:.1f} mm × {self.board_height:.1f} mm", flush=True)
            print(f"🧩 Componentes 3D: Top={len(self.top_models)} | Bottom={len(self.bot_models)}", flush=True)
            print(f"🎨 Estilo        : {STYLE_DESCRIPTIONS.get(self.style, self.style)}", flush=True)
            print(f"🔄 Modo          : {self.mode.upper()}", flush=True)
            print(f"📺 Resolução     : {self.width}×{self.height} @ {self.fps} fps", flush=True)
            print(f"⏱️ Duração       : {total_frames} frames ({total_frames/self.fps:.1f} segundos)", flush=True)
            print(f"⚡ Núcleos CPU   : {self.workers} workers em paralelo", flush=True)
            print("="*60 + "\n", flush=True)

            self._render_all_frames(temp_dir, total_frames)

            print("\n🎬 Codificando vídeo MP4 final com FFmpeg...", flush=True)
            self._encode_video(temp_dir, total_frames, output_mp4)

            if output_gif:
                print("🖼️ Gerando GIF otimizado de preview...", flush=True)
                self._encode_gif(output_mp4, output_gif)

            print("\n" + "-"*60, flush=True)
            print("✅ ESTILO CONCLUÍDO COM SUCESSO!", flush=True)
            print(f"📹 Vídeo MP4 : {os.path.abspath(output_mp4)}", flush=True)
            if output_gif:
                print(f"🎞️ GIF        : {os.path.abspath(output_gif)}", flush=True)
            print("-"*60 + "\n", flush=True)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def render_single_frame(self, frame_idx, output_png):
        temp_dir = tempfile.mkdtemp(prefix="kicad_still_")
        pbar = RenderProgressBar(1, prefix="KiCad Preview")
        try:
            self._calculate_timeline()
            if frame_idx is None or frame_idx < 0:
                frame_idx = self.total_frames - int(0.5 * self.fps)
            frame_idx = max(0, min(frame_idx, self.total_frames - 1))
            pbar.update(0, status=f"Renderizando quadro {frame_idx} com KiCad Nativo...")
            print(f"📸 Renderizando quadro {frame_idx} com KiCad Nativo ({self.width}x{self.height})...", flush=True)
            self._render_frame_worker(temp_dir, frame_idx)
            src = os.path.join(temp_dir, f"frame_{frame_idx:04d}.png")
            if os.path.exists(src):
                os.makedirs(os.path.dirname(os.path.abspath(output_png)), exist_ok=True)
                shutil.copy2(src, output_png)
                pbar.update(1, status="Finalizado")
                pbar.close("Preview salvo")
                print(f"✅ Preview salvo em: {output_png}", flush=True)
                return output_png
            else:
                raise RuntimeError(f"Quadro {frame_idx} não foi gerado.")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
