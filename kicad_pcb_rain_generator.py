#!/usr/bin/env python3
"""
KiCad PCB Universal Assembly Animator (Blender / bpy Headless Edition)
----------------------------------------------------------------------
Gerador universal de animações 3D cinemáticas para placas KiCad (KiCad 7, 8, 9 e 10).
Utiliza o Blender em modo headless com a biblioteca `bpy` para renderização PBR acelerada por GPU.

Oferece 4 estilos de montagem procedural + opção de gerar todos em lote:
  1. Chuva Linear Gravitacional (Rain)
  2. Onda Radial do Centro (Ripple)
  3. Montagem SMT por Categoria (Pick-and-Place Realista)
  4. Vórtice Magnético 3D (Vortex Espiral)
  5. Todos os 4 Estilos em Lote (All)

Permite execução interativa pelo terminal ou via argumentos de linha de comando.
Compatível com:
  - Ambiente Python com `bpy` instalado (`pip install bpy`)
  - Execução via `uv run --python 3.13 --with bpy`
  - Binário do Blender desktop (`blender -b -P ...`)
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

# ---------------------------------------------------------------------------
# Verificação de Runtime (bpy vs Runner Externo)
# ---------------------------------------------------------------------------
try:
    import bpy
    from mathutils import Vector
    HAS_BPY = True
except ImportError:
    HAS_BPY = False

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

ALL_STYLES = ["rain", "radial", "assembly", "vortex"]

STYLE_DESCRIPTIONS = {
    "rain": "Chuva Linear Gravitacional (Rain)",
    "radial": "Onda Radial do Centro (Ripple)",
    "assembly": "Linha de Montagem SMT por Categoria (Pick-and-Place)",
    "vortex": "Vórtice Magnético Espiral 3D (Vortex)"
}

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

# ---------------------------------------------------------------------------
# Parser de Metadados da Placa (.kicad_pcb)
# ---------------------------------------------------------------------------
class PCBMetaParser:
    def __init__(self, pcb_path):
        self.pcb_path = os.path.abspath(pcb_path)
        with open(self.pcb_path, "r", encoding="utf-8") as f:
            self.txt = f.read()
        self._parse()

    def _parse(self):
        pts_x = []
        pts_y = []
        for line in self.txt.splitlines():
            if "Edge.Cuts" in line:
                for match in re.finditer(r"\((?:start|end|mid|xy|at)\s+([\d\.\-]+)\s+([\d\.\-]+)", line):
                    pts_x.append(float(match.group(1)))
                    pts_y.append(float(match.group(2)))

        fp_pattern = re.compile(r"\t\(footprint\s+\"([^\"]+)\"[\s\S]*?\n\t\)")
        self.footprints = []
        for m in fp_pattern.finditer(self.txt):
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

            # Ignora componentes mecânicos sem modelo ou furos de fixação
            if ref.startswith("H") or ref.startswith("MH") or ref.startswith("FID"):
                continue

            self.footprints.append({
                "ref": ref,
                "layer": layer,
                "x": x,
                "y": y,
                "category": categorize_ref(ref),
                "has_model": has_model
            })

        self.min_x = min(pts_x) if pts_x else 0.0
        self.max_x = max(pts_x) if pts_x else 100.0
        self.min_y = min(pts_y) if pts_y else 0.0
        self.max_y = max(pts_y) if pts_y else 100.0
        self.center_x = (self.min_x + self.max_x) / 2.0
        self.center_y = (self.min_y + self.max_y) / 2.0
        self.width = max(10.0, self.max_x - self.min_x)
        self.height = max(10.0, self.max_y - self.min_y)
        self.max_radius = math.hypot(self.width / 2.0, self.height / 2.0)

        self.top_models = [fp for fp in self.footprints if fp["layer"] == "F.Cu" and fp["has_model"]]
        self.bot_models = [fp for fp in self.footprints if fp["layer"] == "B.Cu" and fp["has_model"]]

# ---------------------------------------------------------------------------
# Motor de Animação 3D Headless via Blender / bpy
# ---------------------------------------------------------------------------
class BlenderPCBAnimator:
    def __init__(self, pcb_path, glb_path, pcb_meta, style="rain", mode="both", fps=60, resolution="4k",
                 engine="eevee", samples=16, light_intensity=1.0, save_blend=None):
        self.pcb_path = os.path.abspath(pcb_path)
        self.glb_path = os.path.abspath(glb_path)
        self.meta = pcb_meta
        self.style = style.lower()
        self.mode = mode.lower()
        self.fps = fps
        self.engine = engine.lower()
        self.samples = samples
        self.light_intensity = float(light_intensity)
        self.save_blend = save_blend

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

    def _setup_scene(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.scene = bpy.context.scene

        # Configuração do Motor de Render
        if self.engine == "cycles":
            self.scene.render.engine = "CYCLES"
            self.scene.cycles.samples = self.samples
            # Tenta ativar aceleração Metal (macOS) ou CUDA
            try:
                cpref = bpy.context.preferences.addons["cycles"].preferences
                cpref.compute_device_type = "METAL"
                cpref.get_devices()
                for d in cpref.devices:
                    d.use = True
                self.scene.cycles.device = "GPU"
            except Exception:
                pass
        else:
            self.scene.render.engine = "BLENDER_EEVEE"

        self.scene.render.resolution_x = self.width
        self.scene.render.resolution_y = self.height
        self.scene.render.resolution_percentage = 100
        self.scene.render.fps = self.fps
        self.scene.render.image_settings.file_format = "PNG"

        # Gerenciamento de Cores Profissional (evita estouro de brancos / clipping)
        self.scene.view_settings.view_transform = "AgX"
        self.scene.view_settings.look = "AgX - Base Contrast"
        self.scene.view_settings.exposure = -0.3

        # Fundo de Estúdio Dark Slate (#0b1120) suave e elegante
        world = bpy.data.worlds.new("StudioWorld")
        self.scene.world = world
        tree = world.node_tree
        tree.nodes.clear()
        bg_node = tree.nodes.new(type="ShaderNodeBackground")
        bg_node.inputs["Color"].default_value = (0.012, 0.018, 0.032, 1.0)
        bg_node.inputs["Strength"].default_value = 0.25
        out_node = tree.nodes.new(type="ShaderNodeOutputWorld")
        tree.links.new(bg_node.outputs["Background"], out_node.inputs["Surface"])

        # Importa GLB do KiCad
        bpy.ops.import_scene.gltf(filepath=self.glb_path)

        # Localiza o mesh da placa PCB para obter centro e dimensões exatas em metros
        pcb_mesh_objs = [obj for obj in bpy.data.objects if obj.type == "MESH" and obj.data and "_PCB" in obj.data.name]
        if pcb_mesh_objs:
            pcb_obj = pcb_mesh_objs[0]
            bbox = [pcb_obj.matrix_world @ Vector(c) for c in pcb_obj.bound_box]
            min_x = min(c.x for c in bbox)
            max_x = max(c.x for c in bbox)
            min_y = min(c.y for c in bbox)
            max_y = max(c.y for c in bbox)
            min_z = min(c.z for c in bbox)
            max_z = max(c.z for c in bbox)
            self.board_center = Vector(((min_x + max_x) / 2.0, (min_y + max_y) / 2.0, (min_z + max_z) / 2.0))
            self.board_w = max_x - min_x
            self.board_h = max_y - min_y
            self.board_thick = max(0.001, max_z - min_z)
        else:
            self.board_center = Vector((self.meta.center_x / 1000.0, -self.meta.center_y / 1000.0, 0.0008))
            self.board_w = self.meta.width / 1000.0
            self.board_h = self.meta.height / 1000.0
            self.board_thick = 0.0016

        # Centraliza todos os objetos da raiz no ponto (0, 0, 0)
        root_objs = [obj for obj in bpy.data.objects if obj.parent is None]
        for obj in root_objs:
            obj.location -= self.board_center

        self._setup_lighting_and_materials()
        self._setup_camera()

    def _setup_lighting_and_materials(self):
        # Target Empty na origem (0, 0, 0)
        self.target = bpy.data.objects.new("CamTarget", None)
        self.scene.collection.objects.link(self.target)
        self.target.location = Vector((0, 0, 0))

        # Fator de escala quadrático baseado no tamanho da placa (referência: 100mm = 0.10m).
        # Em distâncias macro (~15-25cm), potências de 1.2W a 3.2W proporcionam exposição
        # fotográfica equilibrada sem estourar brancos ou criar clarões especulares.
        diag = max(self.board_w, self.board_h)
        base_scale = ((diag / 0.10) ** 2) * self.light_intensity

        def add_light(name, loc, size, energy, color):
            ldata = bpy.data.lights.new(name=name, type="AREA")
            ldata.shape = "RECTANGLE"
            ldata.size = size
            ldata.size_y = size
            ldata.energy = energy
            ldata.color = color
            lobj = bpy.data.objects.new(name=name, object_data=ldata)
            self.scene.collection.objects.link(lobj)
            lobj.location = loc
            tt = lobj.constraints.new(type="TRACK_TO")
            tt.target = self.target
            tt.track_axis = "TRACK_NEGATIVE_Z"
            tt.up_axis = "UP_Y"
            return lobj

        # 3-Point Lighting de Estúdio Suave
        add_light("KeyLight", Vector((diag * 1.5, -diag * 1.6, diag * 1.8)), diag * 1.8, 3.2 * base_scale, (1.0, 0.97, 0.94))
        add_light("FillLight", Vector((-diag * 1.6, -diag * 1.2, diag * 1.3)), diag * 2.2, 1.4 * base_scale, (0.88, 0.93, 1.0))
        add_light("RimLight", Vector((0.0, diag * 1.9, diag * 1.4)), diag * 2.0, 2.2 * base_scale, (1.0, 1.0, 1.0))

        # Luz suave de preenchimento inferior para a face inferior (B.Cu)
        add_light("BotLight", Vector((diag * 1.2, -diag * 1.3, -diag * 1.6)), diag * 2.2, 1.2 * base_scale, (0.9, 0.94, 1.0))

        # Calibração e Correção de Materiais PBR
        # Nota importante: kicad-cli exporta materiais nomeados genericamente como 'mat_0'...'mat_30'.
        # O identificador semântico de camada (soldermask, silkscreen, etc.) reside em obj.data.name.
        # Além disso, o KiCad exporta camadas da PCB com blend_method='BLEND' e alpha < 1.0, o que no
        # EEVEE causa falha severa de profundidade/ordenação alpha e embranquece a máscara de solda.
        for obj in bpy.data.objects:
            if obj.type == "MESH" and obj.data:
                dname = obj.data.name.lower()
                for slot in obj.material_slots:
                    mat = slot.material
                    if not mat or not mat.node_tree:
                        continue

                    # Força blend_method OPAQUE e Alpha 1.0 nas camadas da placa
                    if any(k in dname for k in ["pcb", "soldermask", "silkscreen", "pad", "copper", "track", "via"]):
                        mat.blend_method = "OPAQUE"
                        for n in mat.node_tree.nodes:
                            if n.type == "BSDF_PRINCIPLED":
                                if "Alpha" in n.inputs:
                                    n.inputs["Alpha"].default_value = 1.0

                    for n in mat.node_tree.nodes:
                        if n.type == "BSDF_PRINCIPLED":
                            if "soldermask" in dname:
                                # Máscara de solda KiCad: verde esmeralda profundo acetinado
                                cur_col = n.inputs["Base Color"].default_value
                                if cur_col[1] >= cur_col[0] and cur_col[1] >= cur_col[2]:
                                    n.inputs["Base Color"].default_value = (0.015, 0.18, 0.055, 1.0)
                                if "Roughness" in n.inputs:
                                    n.inputs["Roughness"].default_value = 0.35
                                if "Specular IOR Level" in n.inputs:
                                    n.inputs["Specular IOR Level"].default_value = 0.45
                            elif "silkscreen" in dname:
                                # Serigrafia branca nítida e fosca
                                n.inputs["Base Color"].default_value = (0.95, 0.95, 0.95, 1.0)
                                if "Roughness" in n.inputs:
                                    n.inputs["Roughness"].default_value = 0.60
                            elif any(k in dname for k in ["pad", "copper", "track", "via"]):
                                # Trilha e ilha de solda metálica
                                if "Metallic" in n.inputs:
                                    n.inputs["Metallic"].default_value = 0.95
                                if "Roughness" in n.inputs:
                                    n.inputs["Roughness"].default_value = 0.22
                            elif "pcb" in dname:
                                # Substrato FR4 escuro nas bordas/cortes
                                n.inputs["Base Color"].default_value = (0.08, 0.12, 0.05, 1.0)
                                if "Roughness" in n.inputs:
                                    n.inputs["Roughness"].default_value = 0.50

        # Realce de materiais de componentes (LEDs, metais, etc.)
        for mat in bpy.data.materials:
            if not mat.node_tree:
                continue
            mname = mat.name.lower()
            for n in mat.node_tree.nodes:
                if n.type == "BSDF_PRINCIPLED":
                    if "led" in mname:
                        if "Emission Strength" in n.inputs:
                            n.inputs["Emission Strength"].default_value = 1.8

    def _setup_camera(self):
        cam_data = bpy.data.cameras.new("MainCam")
        cam_data.lens = 50  # 50mm natural / estúdio
        cam_data.clip_start = 0.01  # 1 cm (alta precisão no z-buffer contra z-fighting)
        cam_data.clip_end = 5.0     # 5 m
        cam_data.dof.use_dof = True
        cam_data.dof.focus_object = self.target
        cam_data.dof.aperture_fstop = 7.1

        self.cam_obj = bpy.data.objects.new("MainCam", cam_data)
        self.scene.collection.objects.link(self.cam_obj)
        self.scene.camera = self.cam_obj

        tt = self.cam_obj.constraints.new(type="TRACK_TO")
        tt.target = self.target
        tt.track_axis = "TRACK_NEGATIVE_Z"
        tt.up_axis = "UP_Y"

        # Distância calculada pela diagonal para garantir que a placa inteira e componentes
        # fiquem sempre visíveis e confortavelmente enquadrados com margem de respiro
        board_diag = math.hypot(self.board_w, self.board_h)
        self.cam_dist = board_diag * 2.85

    def _calculate_timeline(self):
        if self.mode == "both":
            self.total_frames = int(8.0 * self.fps)
            self.act1_end = int(2.4 * self.fps)
            self.act2_end = int(4.6 * self.fps)
            self.act3_end = int(7.0 * self.fps)
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

        for fp in self.meta.footprints:
            ref = fp["ref"]
            if not fp["has_model"]:
                self.spawn_timings[ref] = None
                continue

            if self.style == "rain":
                norm = (fp["x"] - self.meta.min_x) / self.meta.width
            elif self.style == "radial":
                dist = math.hypot(fp["x"] - self.meta.center_x, fp["y"] - self.meta.center_y)
                norm = dist / max(1.0, self.meta.max_radius)
            elif self.style == "assembly":
                cat = fp["category"]
                norm_x = (fp["x"] - self.meta.min_x) / self.meta.width
                if cat == 1:
                    norm = 0.0 + 0.30 * norm_x
                elif cat == 2:
                    norm = 0.35 + 0.30 * norm_x
                else:
                    norm = 0.70 + 0.30 * norm_x
            elif self.style == "vortex":
                dist = math.hypot(fp["x"] - self.meta.center_x, fp["y"] - self.meta.center_y)
                norm_r = dist / max(1.0, self.meta.max_radius)
                norm_x = (fp["x"] - self.meta.min_x) / self.meta.width
                norm = 0.6 * norm_x + 0.4 * norm_r
            else:
                norm = (fp["x"] - self.meta.min_x) / self.meta.width

            norm = max(0.0, min(1.0, norm))
            jitter = random.uniform(-4.0, 4.0)

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

            self.spawn_timings[ref] = max(1.0, spawn)

        return self.total_frames

    def _animate_camera(self):
        R = self.cam_dist

        for frame in range(1, self.total_frames + 1):
            if self.mode == "both":
                if frame < self.act1_end:
                    # Act 1: Vista da Face Inferior (Bottom)
                    p = frame / float(self.act1_end)
                    phi = math.radians(140.0 - 2.0 * p)
                    theta = math.radians(-65.0 + 10.0 * p)
                elif frame < self.act2_end:
                    # Act 2: Transição Esférica 3D Suave (180° Flip Arc)
                    t = (frame - self.act1_end) / float(self.act2_end - self.act1_end)
                    p = t * t * (3.0 - 2.0 * t)  # Smoothstep
                    phi = math.radians(138.0 - 98.0 * p)  # Vai de 138° para 40°
                    theta = math.radians(-55.0 + 35.0 * math.sin(p * math.pi))
                elif frame < self.act3_end:
                    # Act 3: Vista da Face Superior (Top)
                    p = (frame - self.act2_end) / float(self.act3_end - self.act2_end)
                    phi = math.radians(40.0 + 2.0 * p)
                    theta = math.radians(-55.0 + 10.0 * p)
                else:
                    # Act 4: Órbita Lenta de Beleza Final (Beauty Orbit)
                    p = (frame - self.act3_end) / float(self.total_frames - self.act3_end)
                    phi = math.radians(42.0 + 3.0 * math.sin(p * math.pi))
                    theta = math.radians(-45.0 + 25.0 * p)
            elif self.mode == "top":
                p = frame / float(self.total_frames)
                phi = math.radians(42.0 + 2.0 * math.sin(p * math.pi))
                theta = math.radians(-60.0 + 30.0 * p)
            else: # bottom
                p = frame / float(self.total_frames)
                phi = math.radians(138.0 - 2.0 * math.sin(p * math.pi))
                theta = math.radians(-60.0 + 30.0 * p)

            x = R * math.sin(phi) * math.cos(theta)
            y = R * math.sin(phi) * math.sin(theta)
            z = R * math.cos(phi)

            self.cam_obj.location = Vector((x, y, z))
            self.cam_obj.keyframe_insert(data_path="location", frame=frame)

    def _animate_components(self):
        fall_dur = max(4, int(0.35 * self.fps))
        bounce_dur = max(2, int(0.14 * self.fps))
        drop_h = 0.045  # 45 mm em metros
        bounce_h = 0.0015 # 1.5 mm em metros

        for fp in self.meta.footprints:
            ref = fp["ref"]
            spawn_f = self.spawn_timings.get(ref)
            if spawn_f is None:
                continue

            obj = bpy.data.objects.get(ref)
            if not obj:
                continue

            rest_loc = obj.location.copy()
            is_bot = (fp["layer"] == "B.Cu")
            z_dir = -1.0 if is_bot else 1.0

            land_f = int(spawn_f + fall_dur)
            settle_f = land_f + bounce_dur
            spawn_int = int(spawn_f)

            # 1. Antes do spawn: invisível e escala zero
            if spawn_int > 1:
                obj.scale = Vector((0, 0, 0))
                obj.hide_viewport = True
                obj.hide_render = True
                obj.keyframe_insert(data_path="scale", frame=1)
                obj.keyframe_insert(data_path="hide_viewport", frame=1)
                obj.keyframe_insert(data_path="hide_render", frame=1)
                for c in obj.children_recursive:
                    c.hide_viewport = True
                    c.hide_render = True
                    c.keyframe_insert(data_path="hide_viewport", frame=1)
                    c.keyframe_insert(data_path="hide_render", frame=1)

                if spawn_int - 1 > 1:
                    obj.keyframe_insert(data_path="scale", frame=spawn_int - 1)
                    obj.keyframe_insert(data_path="hide_viewport", frame=spawn_int - 1)
                    obj.keyframe_insert(data_path="hide_render", frame=spawn_int - 1)

            # 2. No frame de spawn: torna-se visível
            obj.scale = Vector((1, 1, 1))
            obj.hide_viewport = False
            obj.hide_render = False
            obj.keyframe_insert(data_path="scale", frame=spawn_int)
            obj.keyframe_insert(data_path="hide_viewport", frame=spawn_int)
            obj.keyframe_insert(data_path="hide_render", frame=spawn_int)
            for c in obj.children_recursive:
                c.hide_viewport = False
                c.hide_render = False
                c.keyframe_insert(data_path="hide_viewport", frame=spawn_int)
                c.keyframe_insert(data_path="hide_render", frame=spawn_int)

            # 3. Trajetória de queda com gravidade e estilo procedural
            for f in range(spawn_int, land_f + 1, 2):
                t = (f - spawn_int) / float(fall_dur)
                p = t * t  # Aceleração gravitacional
                cur_z = rest_loc.z + (1.0 - p) * drop_h * z_dir

                if self.style == "vortex":
                    radius = 0.015 * (1.0 - t)
                    theta = 3.5 * math.pi * (1.0 - t)
                    dx = radius * math.cos(theta)
                    dy = radius * math.sin(theta)
                elif self.style == "radial":
                    dir_x = (fp["x"] - self.meta.center_x) / max(1.0, self.meta.max_radius)
                    dir_y = (fp["y"] - self.meta.center_y) / max(1.0, self.meta.max_radius)
                    disp = 0.006 * (1.0 - t)
                    dx = dir_x * disp
                    dy = dir_y * disp
                else:
                    dx = 0.0
                    dy = 0.0

                obj.location = Vector((rest_loc.x + dx, rest_loc.y + dy, cur_z))
                obj.keyframe_insert(data_path="location", frame=f)

            # Impacto no resting position
            obj.location = rest_loc
            obj.keyframe_insert(data_path="location", frame=land_f)

            # 4. Rebote elástico amortecido
            bounce_mid = (land_f + settle_f) // 2
            obj.location = Vector((rest_loc.x, rest_loc.y, rest_loc.z + bounce_h * z_dir))
            obj.keyframe_insert(data_path="location", frame=bounce_mid)

            obj.location = rest_loc
            obj.keyframe_insert(data_path="location", frame=settle_f)

    def render_single_frame(self, frame_idx, output_png):
        total_frames = self._calculate_timeline()
        if frame_idx is None or frame_idx < 1 or frame_idx > total_frames:
            frame_idx = total_frames

        print("\n" + "="*60)
        print("📸 RENDERIZANDO QUADRO ESTÁTICO (PREVIEW DE ILUMINAÇÃO)")
        print("="*60)
        print(f"📁 Projeto PCB   : {os.path.basename(self.pcb_path)}")
        print(f"🖼️ Quadro       : #{frame_idx} de {total_frames}")
        print(f"⚙️ Motor Render  : {self.engine.upper()} (samples: {self.samples})")
        print(f"💡 Luz           : Intensidade {self.light_intensity}x")
        print(f"📺 Resolução     : {self.width}×{self.height}")
        print("="*60 + "\n")

        print("📦 Configurando cena e shaders no Blender...")
        self._setup_scene()
        self._animate_camera()
        self._animate_components()

        self.scene.frame_set(frame_idx)
        out_file = os.path.abspath(output_png)
        if not out_file.lower().endswith(".png"):
            out_file += ".png"
        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        self.scene.render.filepath = out_file

        print(f"⏳ Renderizando frame #{frame_idx}...")
        bpy.ops.render.render(write_still=True)
        print(f"\n✅ Quadro salvo com sucesso em: {out_file}\n")
        return out_file

    def generate(self, output_mp4, output_gif=None):
        temp_dir = tempfile.mkdtemp(prefix="kicad_bpy_anim_")
        try:
            total_frames = self._calculate_timeline()

            print("\n" + "="*60)
            print("🚀 INICIANDO RENDERIZAÇÃO DA ANIMAÇÃO 3D (BLENDER / BPY)")
            print("="*60)
            print(f"📁 Projeto PCB   : {os.path.basename(self.pcb_path)}")
            print(f"📐 Dimensões     : {self.meta.width:.1f} mm × {self.meta.height:.1f} mm")
            print(f"🧩 Componentes 3D: Top={len(self.meta.top_models)} | Bottom={len(self.meta.bot_models)}")
            print(f"🎨 Estilo        : {STYLE_DESCRIPTIONS.get(self.style, self.style)}")
            print(f"🔄 Modo          : {self.mode.upper()}")
            print(f"⚙️ Motor Render  : {self.engine.upper()} (samples: {self.samples})")
            print(f"📺 Resolução     : {self.width}×{self.height} @ {self.fps} fps")
            print(f"⏱️ Duração       : {total_frames} frames ({total_frames/self.fps:.1f} segundos)")
            print("="*60 + "\n")

            print("📦 Configurando cena, shaders e keyframes procedurais no Blender...")
            self._setup_scene()
            self._animate_camera()
            self._animate_components()

            if self.save_blend:
                blend_file = os.path.abspath(self.save_blend)
                os.makedirs(os.path.dirname(blend_file), exist_ok=True)
                bpy.ops.wm.save_as_mainfile(filepath=blend_file)
                print(f"💾 Cena Blender salva em: {blend_file}")

            # Renderização dos quadros
            self.scene.frame_start = 1
            self.scene.frame_end = total_frames

            print("\n⏳ Renderizando quadros...")
            for f in range(1, total_frames + 1):
                self.scene.frame_set(f)
                frame_png = f"{temp_dir}/frame_{f:04d}.png"
                self.scene.render.filepath = frame_png
                bpy.ops.render.render(write_still=True)
                if f % max(1, total_frames // 10) == 0 or f == total_frames:
                    pct = f / total_frames * 100.0
                    print(f"  Frame [{f:03d}/{total_frames:03d}] {pct:5.1f}% concluído")

            print("\n🎬 Codificando vídeo MP4 final com FFmpeg...")
            self._encode_video(temp_dir, total_frames, output_mp4)

            if output_gif:
                print("🖼️ Gerando GIF otimizado de preview...")
                self._encode_gif(output_mp4, output_gif)

            print("\n" + "-"*60)
            print("✅ ANIMAÇÃO CONCLUÍDA COM SUCESSO!")
            print(f"📹 Vídeo MP4 : {os.path.abspath(output_mp4)}")
            if output_gif:
                print(f"🎞️ GIF        : {os.path.abspath(output_gif)}")
            print("-"*60 + "\n")

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _encode_video(self, temp_dir, total_frames, output_mp4):
        os.makedirs(os.path.dirname(os.path.abspath(output_mp4)), exist_ok=True)
        cmd = [
            FFMPEG, "-y",
            "-framerate", str(self.fps),
            "-i", f"{temp_dir}/frame_%04d.png",
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

# ---------------------------------------------------------------------------
# Funções de Exportação GLB do KiCad
# ---------------------------------------------------------------------------
def export_kicad_glb(pcb_path, output_glb):
    print(f"📐 Exportando modelo 3D GLB via kicad-cli: {os.path.basename(pcb_path)}...")
    cmd = [
        KICAD_CLI, "pcb", "export", "glb",
        "--include-tracks",
        "--include-pads",
        "--include-silkscreen",
        "--include-soldermask",
        "--fuse-shapes",
        "-f",
        "-o", output_glb,
        pcb_path
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print(f"❌ Erro ao exportar GLB do KiCad:\n{res.stderr}", file=sys.stderr)
        sys.exit(1)
    print("✅ Modelo GLB exportado com sucesso!")

# ---------------------------------------------------------------------------
# Utilitários de Interface e Resolução de Trabalhos
# ---------------------------------------------------------------------------
def find_available_pcbs():
    found = glob.glob("**/*.kicad_pcb", recursive=True) + glob.glob("*.kicad_pcb")
    clean = [p for p in set(found) if not p.endswith(".bak") and ".history" not in p]
    return sorted(clean)

def prompt_terminal_interactive():
    print("\n" + "="*60)
    print("🛠️  GERADOR UNIVERSAL DE ANIMAÇÃO 3D DE PCB (BLENDER / BPY)")
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
    print("  [1] Ambas as faces com giro 3D esférico de 180° (Both) [Recomendado]")
    print("  [2] Apenas face superior (Top)")
    print("  [3] Apenas face inferior (Bottom)")
    mode_choices = {"1": "both", "2": "top", "3": "bottom"}
    m_choice = input("\nModo [1-3] (Padrão: 1): ").strip()
    mode = mode_choices.get(m_choice, "both")

    # 4. Motor de Render
    print("\n⚙️ Motor de renderização:")
    print("  [1] Blender EEVEE (Ultra rápido, PBR em tempo real) [Padrão]")
    print("  [2] Blender Cycles (Raytracing fotorrealista com GPU Metal)")
    eng_choice = input("\nMotor [1-2] (Padrão: 1): ").strip()
    engine = "cycles" if eng_choice == "2" else "eevee"

    # 5. Resolução
    print("\n📺 Resolução do vídeo:")
    print("  [1] 4K Ultra HD (3840×2160) [Qualidade Máxima]")
    print("  [2] 1080p Full HD (1920×1080) [Equilibrado]")
    print("  [3] 720p HD (1280×720) [Renderização Rápida]")
    res_choices = {"1": "4k", "2": "1080p", "3": "720p"}
    r_choice = input("\nResolução [1-3] (Padrão: 1): ").strip()
    resolution = res_choices.get(r_choice, "4k")

    # 6. FPS
    print("\n⏱️ Taxa de quadros:")
    print("  [1] 60 fps (Fluidez cinematográfica máxima) [Padrão]")
    print("  [2] 30 fps (Mais rápido para renderizar)")
    fps_choice = input("\nTaxa de quadros [1-2] (Padrão: 1): ").strip()
    fps = 30 if fps_choice == "2" else 60

    # 7. Salvar arquivo .blend
    save_blend_choice = input("\n💾 Deseja também salvar o projeto .blend gerado? (s/N) [Padrão: N]: ").strip().lower()
    save_blend = save_blend_choice == "s"

    # 8. GIF de Preview
    gif_choice = input("\n🎞️ Gerar também arquivos GIF de preview? (S/n) [Padrão: S]: ").strip().lower()
    make_gif = gif_choice != "n"

    # 9. Arquivos de Saída
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
        "engine": engine,
        "res": resolution,
        "fps": fps,
        "save_blend": save_blend,
        "output": out_dest,
        "gif": make_gif
    }

def resolve_jobs(pcb_path, style, resolution, fps, out_dest, make_gif, save_blend):
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
            blend_path = os.path.join(base_dir, f"{pcb_name}_{s}.blend") if save_blend else None
            jobs.append((s, mp4_path, gif_path, blend_path))
    else:
        if not out_dest:
            mp4_path = os.path.join(target_dir, f"{pcb_name}_{style}_{resolution}_{fps}fps.mp4")
        elif os.path.isdir(out_dest):
            mp4_path = os.path.join(out_dest, f"{pcb_name}_{style}_{resolution}_{fps}fps.mp4")
        else:
            mp4_path = out_dest

        gif_path = os.path.splitext(mp4_path)[0] + ".gif" if make_gif else None
        blend_path = os.path.splitext(mp4_path)[0] + ".blend" if save_blend else None
        jobs.append((style, mp4_path, gif_path, blend_path))

    return jobs

# ---------------------------------------------------------------------------
# Ponto de Entrada Principal
# ---------------------------------------------------------------------------
def main():
    # Suporte a argumentos passados após "--" quando executado via `blender -b -P script.py -- [args]`
    if "--" in sys.argv:
        raw_args = sys.argv[sys.argv.index("--") + 1:]
    else:
        raw_args = sys.argv[1:]

    parser = argparse.ArgumentParser(description="KiCad PCB Universal Assembly Animator (Blender / bpy Edition)")
    parser.add_argument("--pcb", help="Caminho do arquivo .kicad_pcb")
    parser.add_argument("--style", choices=["rain", "radial", "assembly", "vortex", "all"], default="rain", help="Estilo da animacao ou 'all' para gerar todos")
    parser.add_argument("--mode", choices=["both", "top", "bottom"], default="both", help="Faces a animar")
    parser.add_argument("--engine", choices=["eevee", "cycles"], default="eevee", help="Motor de renderizacao do Blender (padrao: eevee)")
    parser.add_argument("--samples", type=int, default=16, help="Numero de amostras de render (samples)")
    parser.add_argument("--light-intensity", type=float, default=1.0, help="Multiplicador de intensidade das luzes de estudio (padrao: 1.0)")
    parser.add_argument("--still-frame", type=int, nargs="?", const=-1, default=None, help="Renderizar apenas um frame estatico para preview de iluminacao (ex: --still-frame ou --still-frame 150)")
    parser.add_argument("--save-blend", action="store_true", help="Salvar arquivo(s) de projeto .blend")
    parser.add_argument("--output", "-o", help="Arquivo ou pasta de saida")
    parser.add_argument("--gif", action="store_true", help="Gerar arquivo(s) GIF de preview")
    parser.add_argument("--res", default="4k", help="Resolucao: 4k, 1080p, 720p ou WxH")
    parser.add_argument("--fps", type=int, default=60, help="Taxa de quadros (padrao: 60)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Executar no modo interativo pelo terminal")

    args = parser.parse_args(raw_args)

    # 1. Caso NÃO estejamos em um ambiente com `bpy` (executado por python normal do sistema):
    if not HAS_BPY:
        # Verifica se existe um virtualenv local com bpy
        script_dir = os.path.dirname(os.path.abspath(__file__))
        venv_py = os.path.join(script_dir, ".venv", "bin", "python")
        if os.path.exists(venv_py):
            # Transfere a execução diretamente para o .venv
            cmd = [venv_py, os.path.abspath(__file__)] + raw_args
            sys.exit(subprocess.call(cmd))

        # Verifica se uv está disponível para executar com bpy
        if UV_BIN:
            cmd = [UV_BIN, "run", "--python", "3.13", "--with", "bpy", "python", os.path.abspath(__file__)] + raw_args
            sys.exit(subprocess.call(cmd))

        # Verifica se o binário do Blender está disponível
        if BLENDER_BIN:
            cmd = [BLENDER_BIN, "--background", "--python", os.path.abspath(__file__), "--"] + raw_args
            sys.exit(subprocess.call(cmd))

        # Caso nenhum esteja presente, exibe instruções claras de configuração
        print("\n❌ Erro: A biblioteca 'bpy' ou o Blender não foram encontrados.", file=sys.stderr)
        print("\nPara utilizar a renderização 3D, escolha uma das opções abaixo:\n", file=sys.stderr)
        print("Opção 1 (Recomendada via venv com Python 3.13):", file=sys.stderr)
        print("  python3.13 -m venv .venv && source .venv/bin/activate && pip install bpy\n", file=sys.stderr)
        print("Opção 2 (Via uv):", file=sys.stderr)
        print("  uv run --python 3.13 --with bpy python kicad_pcb_rain_generator.py\n", file=sys.stderr)
        print("Opção 3 (Instalar Blender desktop no macOS):", file=sys.stderr)
        print("  brew install --cask blender\n", file=sys.stderr)
        sys.exit(1)

    # 2. Estamos em ambiente com `bpy` (Python standalone bpy ou Blender embutido):
    if not KICAD_CLI:
        print("❌ Erro: 'kicad-cli' não foi encontrado no sistema.", file=sys.stderr)
        sys.exit(1)
    if not FFMPEG:
        print("❌ Erro: 'ffmpeg' não foi encontrado no sistema.", file=sys.stderr)
        sys.exit(1)

    if len(raw_args) == 0 or args.interactive or not args.pcb:
        params = prompt_terminal_interactive()
        pcb_path = params["pcb"]
        style = params["style"]
        mode = params["mode"]
        engine = params["engine"]
        resolution = params["res"]
        fps = params["fps"]
        save_blend = params["save_blend"]
        out_dest = params["output"]
        make_gif = params["gif"]
        samples = args.samples
        light_intensity = args.light_intensity
    else:
        pcb_path = args.pcb
        style = args.style
        mode = args.mode
        engine = args.engine
        resolution = args.res
        fps = args.fps
        save_blend = args.save_blend
        out_dest = args.output
        make_gif = args.gif
        samples = args.samples
        light_intensity = args.light_intensity

    pcb_path = os.path.abspath(pcb_path)
    if not os.path.exists(pcb_path):
        print(f"❌ Erro: Arquivo PCB '{pcb_path}' não foi encontrado.", file=sys.stderr)
        sys.exit(1)

    # Parser da Placa
    pcb_meta = PCBMetaParser(pcb_path)

    # Exporta o GLB uma única vez para reutilizar em todos os estilos
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

        jobs = resolve_jobs(pcb_path, style, resolution, fps, out_dest, make_gif, save_blend)

        print("\n" + "="*60)
        print(f"📦 PLANEJAMENTO: {len(jobs)} ANIMAÇÃO(ÕES) A SEREM PROCESSADAS")
        print("="*60)
        for idx, (s, mp4, gif, blend) in enumerate(jobs, 1):
            print(f" [{idx}] {STYLE_DESCRIPTIONS.get(s, s)}")
            print(f"     MP4: {mp4}")
            if gif:
                print(f"     GIF: {gif}")
            if blend:
                print(f"     BLEND: {blend}")
        print("="*60)

        for idx, (s, mp4, gif, blend) in enumerate(jobs, 1):
            if len(jobs) > 1:
                print(f"\n{'#'*60}")
                print(f"🎬 EXECUTANDO TRABALHO [{idx}/{len(jobs)}]: {s.upper()}")
                print(f"{'#'*60}")

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
            print("\n" + "="*60)
            print("🎉 TODOS OS TRABALHOS EM LOTE FORAM CONCLUÍDOS COM SUCESSO!")
            print("="*60)
            for idx, (s, mp4, gif, blend) in enumerate(jobs, 1):
                print(f" [{idx}] {STYLE_DESCRIPTIONS.get(s, s)}:")
                print(f"     📹 {mp4}")
                if gif:
                    print(f"     🎞️ {gif}")
                if blend:
                    print(f"     💾 {blend}")
            print("="*60 + "\n")

    finally:
        if os.path.exists(temp_glb):
            try: os.remove(temp_glb)
            except OSError: pass

if __name__ == "__main__":
    main()
