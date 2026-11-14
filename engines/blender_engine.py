"""
KiCad Animator - Motor de Renderização Blender 3D (bpy Headless)
"""

import os
import sys
import math
import random
import shutil
import tempfile
import subprocess

from core.config import (
    HAS_BPY, KICAD_CLI, FFMPEG, RES_MAP, STYLE_DESCRIPTIONS, categorize_ref
)
from core.progress import RenderProgressBar

if HAS_BPY:
    import bpy
    from mathutils import Vector

def export_kicad_glb(pcb_path, output_glb):
    """Exporta a placa KiCad para um arquivo 3D GLB unificado com camadas completas."""
    print(f"📐 Exportando modelo 3D GLB via kicad-cli: {os.path.basename(pcb_path)}...", flush=True)
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
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        print(f"❌ Erro ao exportar GLB do KiCad:\n{res.stderr}", file=sys.stderr, flush=True)
        sys.exit(1)
    print("✅ Modelo GLB exportado com sucesso!", flush=True)

class BlenderPCBAnimator:
    def __init__(self, pcb_path, glb_path, pcb_meta, style="rain", mode="both", fps=60,
                 resolution="1080p", engine="eevee", samples=32, light_intensity=1.0, save_blend=None):
        if not HAS_BPY:
            raise RuntimeError("O módulo 'bpy' não está disponível no ambiente Python atual.")

        self.pcb_path = os.path.abspath(pcb_path)
        self.glb_path = os.path.abspath(glb_path)
        self.meta = pcb_meta
        self.style = style.lower()
        self.mode = mode.lower()
        self.fps = fps
        self.engine = engine.lower()
        self.samples = samples
        self.light_intensity = light_intensity
        self.save_blend = save_blend

        if resolution in RES_MAP:
            self.width, self.height = RES_MAP[resolution]
        else:
            w, h = resolution.lower().split("x")
            self.width, self.height = int(w), int(h)

        self.scene = None
        self.cam_obj = None
        self.target = None
        self.comp_roots = []
        self.board_objs = []
        self.total_frames = 0
        self.gpu_info = "Detectando..."

    def _setup_scene(self):
        # Reinicia a cena com cena vazia
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.scene = bpy.context.scene

        # Configurações de Aceleração por Hardware GPU
        self.gpu_info = "CPU (Fallback)"
        try:
            bpy.context.preferences.system.use_gpu_subdivision = True
        except Exception:
            pass

        sys_backend = getattr(bpy.context.preferences.system, "gpu_backend", "GPU")

        # Configura e ativa dispositivos GPU em Cycles e EEVEE
        prefs = bpy.context.preferences.addons.get("cycles")
        if prefs:
            cprefs = prefs.preferences
            cprefs.get_devices()
            for device_type in ("METAL", "CUDA", "OPTIX", "HIP", "ONEAPI"):
                try:
                    cprefs.compute_device_type = device_type
                    gpus = [d for d in cprefs.devices if d.type == device_type]
                    if gpus:
                        for d in cprefs.devices:
                            d.use = (d.type == device_type)
                        gpu_names = ", ".join([d.name for d in gpus])
                        self.gpu_info = f"{gpu_names} [{device_type}]"
                        break
                except Exception:
                    pass

        # Configurações do Motor de Render
        if self.engine == "cycles":
            self.scene.render.engine = "CYCLES"
            self.scene.cycles.device = "GPU"
            self.scene.cycles.samples = self.samples
            self.scene.cycles.use_denoising = True
        else:
            self.scene.render.engine = "BLENDER_EEVEE"
            if self.gpu_info == "CPU (Fallback)":
                self.gpu_info = f"Hardware Rasterization ({sys_backend})"

        self.scene.render.resolution_x = self.width
        self.scene.render.resolution_y = self.height
        self.scene.render.resolution_percentage = 100
        self.scene.render.fps = self.fps
        self.scene.render.image_settings.file_format = "PNG"

        # Gerenciamento de Cores Profissional AgX
        self.scene.view_settings.view_transform = "AgX"
        self.scene.view_settings.look = "AgX - Base Contrast"
        self.scene.view_settings.exposure = -0.55

        # Fundo de Estúdio Dark Slate (#0b1120)
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

        # Desvincula container raiz criado pelo importador glTF (ex: Node_0)
        # mantendo matrizes de mundo para que componentes e camadas da placa fiquem no nível raiz da cena
        gltf_roots = [
            obj for obj in bpy.data.objects
            if obj.parent is None and obj.type == "EMPTY" and any(
                ("pcb" in (c.data.name.lower() if c.data else "") or "soldermask" in (c.data.name.lower() if c.data else ""))
                for c in obj.children
            )
        ]
        for root in gltf_roots:
            for child in list(root.children):
                mat = child.matrix_world.copy()
                child.parent = None
                child.matrix_world = mat
            bpy.data.objects.remove(root, do_unlink=True)

        # Localiza o mesh da placa PCB para obter centro e dimensões exatas em metros
        pcb_mesh_objs = [obj for obj in bpy.data.objects if obj.type == "MESH" and obj.data and "_pcb" in obj.data.name.lower()]
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
            self.board_thick = max(0.0004, max_z - min_z)
        else:
            self.board_center = Vector((self.meta.center_x / 1000.0, -self.meta.center_y / 1000.0, 0.0008))
            self.board_w = self.meta.width / 1000.0
            self.board_h = self.meta.height / 1000.0
            self.board_thick = 0.0016

        # Centraliza todos os objetos da raiz no ponto (0, 0, 0)
        root_objs = [obj for obj in bpy.data.objects if obj.parent is None]
        for obj in root_objs:
            obj.location -= self.board_center
        bpy.context.view_layer.update()

        self._setup_lighting_and_materials()
        self._setup_camera()

    def _setup_lighting_and_materials(self):
        self.target = bpy.data.objects.new("CamTarget", None)
        self.scene.collection.objects.link(self.target)
        self.target.location = Vector((0, 0, 0))

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
        add_light("KeyLight", Vector((diag * 1.5, -diag * 1.6, diag * 1.8)), diag * 1.8, 2.2 * base_scale, (1.0, 0.97, 0.94))
        add_light("FillLight", Vector((-diag * 1.6, -diag * 1.2, diag * 1.3)), diag * 2.2, 1.0 * base_scale, (0.88, 0.93, 1.0))
        add_light("RimLight", Vector((0.0, diag * 1.9, diag * 1.4)), diag * 2.0, 1.5 * base_scale, (1.0, 1.0, 1.0))
        add_light("BotLight", Vector((diag * 1.2, -diag * 1.3, -diag * 1.6)), diag * 2.2, 0.9 * base_scale, (0.9, 0.94, 1.0))

        # Ajuste de micro-camadas para visibilidade perfeita das trilhas de cobre
        for obj in bpy.data.objects:
            if obj.type == "MESH" and obj.data:
                dname = obj.data.name.lower()
                if "soldermask" in dname and len(obj.data.vertices) > 0:
                    avg_z = sum(v.co.z for v in obj.data.vertices) / len(obj.data.vertices)
                    if avg_z > 0.0:
                        obj.location.z -= 0.000030
                    else:
                        obj.location.z += 0.000030

        # Calibração e Correção de Materiais PBR
        for obj in bpy.data.objects:
            if obj.type == "MESH" and obj.data:
                dname = obj.data.name.lower()
                for slot in obj.material_slots:
                    mat = slot.material
                    if not mat or not mat.node_tree:
                        continue

                    # Força blend_method OPAQUE nas camadas da placa
                    if any(k in dname for k in ["pcb", "soldermask", "silkscreen", "pad", "copper", "track", "via"]):
                        mat.blend_method = "OPAQUE"
                        for n in mat.node_tree.nodes:
                            if n.type == "BSDF_PRINCIPLED":
                                if "Alpha" in n.inputs:
                                    n.inputs["Alpha"].default_value = 1.0

                    for n in mat.node_tree.nodes:
                        if n.type == "BSDF_PRINCIPLED":
                            if "soldermask" in dname:
                                cur_col = n.inputs["Base Color"].default_value
                                cr, cg, cb = cur_col[0], cur_col[1], cur_col[2]
                                if cr < 0.06 and cg < 0.06 and cb < 0.06:
                                    mask_col = (0.012, 0.012, 0.012, 1.0)
                                elif cr > 0.70 and cg > 0.70 and cb > 0.70:
                                    mask_col = (0.850, 0.850, 0.850, 1.0)
                                elif cb > cg * 1.2 and cb > cr * 1.2:
                                    mask_col = (0.005, 0.020, 0.080, 1.0)
                                elif cr > cg * 1.2 and cr > cb * 1.2:
                                    mask_col = (0.080, 0.008, 0.008, 1.0)
                                elif cr > 0.15 and cb > 0.15 and cg < 0.10:
                                    mask_col = (0.040, 0.008, 0.060, 1.0)
                                elif cr > 0.15 and cg > 0.15 and cb < 0.05:
                                    mask_col = (0.120, 0.100, 0.010, 1.0)
                                else:
                                    mask_col = (0.003, 0.035, 0.012, 1.0)

                                n.inputs["Base Color"].default_value = mask_col
                                if "Roughness" in n.inputs:
                                    n.inputs["Roughness"].default_value = 0.38
                                if "Specular IOR Level" in n.inputs:
                                    n.inputs["Specular IOR Level"].default_value = 0.40
                            elif "silkscreen" in dname:
                                n.inputs["Base Color"].default_value = (0.80, 0.80, 0.80, 1.0)
                                if "Roughness" in n.inputs:
                                    n.inputs["Roughness"].default_value = 0.75
                                if "Specular IOR Level" in n.inputs:
                                    n.inputs["Specular IOR Level"].default_value = 0.20
                            elif any(k in dname for k in ["copper", "track", "via"]):
                                n.inputs["Base Color"].default_value = (0.60, 0.34, 0.15, 1.0)
                                if "Metallic" in n.inputs:
                                    n.inputs["Metallic"].default_value = 0.82
                                if "Roughness" in n.inputs:
                                    n.inputs["Roughness"].default_value = 0.28
                            elif "pad" in dname:
                                n.inputs["Base Color"].default_value = (0.65, 0.65, 0.68, 1.0)
                                if "Metallic" in n.inputs:
                                    n.inputs["Metallic"].default_value = 0.82
                                if "Roughness" in n.inputs:
                                    n.inputs["Roughness"].default_value = 0.35
                                if "Specular IOR Level" in n.inputs:
                                    n.inputs["Specular IOR Level"].default_value = 0.30
                            elif "pcb" in dname:
                                n.inputs["Base Color"].default_value = (0.015, 0.025, 0.010, 1.0)
                                if "Roughness" in n.inputs:
                                    n.inputs["Roughness"].default_value = 0.50

        # Suavização de reflexos em plásticos claros de componentes
        for mat in bpy.data.materials:
            if not mat.node_tree:
                continue
            mname = mat.name.lower()
            for n in mat.node_tree.nodes:
                if n.type == "BSDF_PRINCIPLED":
                    if "led" in mname:
                        if "Emission Strength" in n.inputs:
                            n.inputs["Emission Strength"].default_value = 1.8
                    else:
                        col = n.inputs["Base Color"].default_value
                        if col[0] > 0.6 and col[1] > 0.6 and col[2] > 0.6:
                            if "Roughness" in n.inputs:
                                n.inputs["Roughness"].default_value = max(0.55, n.inputs["Roughness"].default_value)
                            if "Specular IOR Level" in n.inputs:
                                n.inputs["Specular IOR Level"].default_value = min(0.25, n.inputs["Specular IOR Level"].default_value)

    def _setup_camera(self):
        cam_data = bpy.data.cameras.new("MainCam")
        cam_data.lens = 50
        cam_data.clip_start = 0.01
        cam_data.clip_end = 5.0
        cam_data.dof.use_dof = False

        self.cam_obj = bpy.data.objects.new("MainCam", cam_data)
        self.scene.collection.objects.link(self.cam_obj)
        self.scene.camera = self.cam_obj

        tt = self.cam_obj.constraints.new(type="TRACK_TO")
        tt.target = self.target
        tt.track_axis = "TRACK_NEGATIVE_Z"
        tt.up_axis = "UP_Y"

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
        else:
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

            self.spawn_timings[ref] = max(0.0, spawn)

        return self.total_frames

    def _animate_camera(self):
        dist = self.cam_dist

        def set_cam(frame, elev_deg, azim_deg, d=dist):
            elev = math.radians(elev_deg)
            azim = math.radians(azim_deg)
            cx = d * math.cos(elev) * math.sin(azim)
            cy = -d * math.cos(elev) * math.cos(azim)
            cz = d * math.sin(elev)
            self.cam_obj.location = Vector((cx, cy, cz))
            self.cam_obj.keyframe_insert(data_path="location", frame=frame)

        if self.mode == "both":
            set_cam(1, -38.0, 25.0)
            set_cam(self.act1_end, -36.0, 32.0)
            set_cam(int(self.act1_end + 0.35 * (self.act2_end - self.act1_end)), 0.0, 65.0, dist * 1.06)
            set_cam(self.act2_end, 36.0, 32.0)
            set_cam(self.act3_end, 38.0, 24.0)
            set_cam(self.total_frames, 39.5, 20.0)
        elif self.mode == "top":
            set_cam(1, 35.0, 28.0)
            set_cam(self.act3_end, 38.0, 23.0)
            set_cam(self.total_frames, 40.0, 18.0)
        else:
            set_cam(1, -35.0, 28.0)
            set_cam(self.act1_end, -38.0, 23.0)
            set_cam(self.total_frames, -40.0, 18.0)

    def _animate_components(self):
        pcb_keywords = ("pcb", "soldermask", "silkscreen", "pad", "copper", "track", "via")
        self.comp_roots = []
        self.board_objs = []
        for obj in bpy.data.objects:
            if obj.parent is None and obj.type in ("MESH", "EMPTY") and obj != self.cam_obj and obj != self.target:
                oname = obj.name.lower()
                dname = obj.data.name.lower() if (obj.type == "MESH" and obj.data) else ""
                if any(k in oname or k in dname for k in pcb_keywords):
                    self.board_objs.append(obj)
                else:
                    self.comp_roots.append(obj)

        fall_frames = int(0.35 * self.fps)
        bounce_frames = int(0.14 * self.fps)

        for obj in self.comp_roots:
            orig_loc = obj.location.copy()
            orig_scale = obj.scale.copy()
            obj_z = obj.location.z

            is_bottom = obj_z < 0.0

            if is_bottom and self.mode == "top":
                continue
            if not is_bottom and self.mode == "bottom":
                continue

            # Prioriza tempo pré-calculado pelo footprint KiCad se disponível
            if hasattr(self, "spawn_timings") and obj.name in self.spawn_timings and self.spawn_timings[obj.name] is not None:
                spawn_f = self.spawn_timings[obj.name]
            else:
                obj_x = obj.location.x
                obj_y = obj.location.y
                if self.style == "rain":
                    norm = (obj_x - (-self.board_w / 2.0)) / max(0.01, self.board_w)
                elif self.style == "radial":
                    dist = math.hypot(obj_x, obj_y)
                    norm = dist / max(0.01, math.hypot(self.board_w / 2.0, self.board_h / 2.0))
                elif self.style == "assembly":
                    cat = categorize_ref(obj.name)
                    norm_x = (obj_x - (-self.board_w / 2.0)) / max(0.01, self.board_w)
                    if cat == 1:
                        norm = 0.0 + 0.30 * norm_x
                    elif cat == 2:
                        norm = 0.35 + 0.30 * norm_x
                    else:
                        norm = 0.70 + 0.30 * norm_x
                elif self.style == "vortex":
                    dist = math.hypot(obj_x, obj_y)
                    norm_r = dist / max(0.01, math.hypot(self.board_w / 2.0, self.board_h / 2.0))
                    norm_x = (obj_x - (-self.board_w / 2.0)) / max(0.01, self.board_w)
                    norm = 0.6 * norm_x + 0.4 * norm_r
                else:
                    norm = (obj_x - (-self.board_w / 2.0)) / max(0.01, self.board_w)

                norm = max(0.0, min(1.0, norm))
                jitter = random.uniform(-4.0, 4.0)

                if is_bottom:
                    if self.mode == "both":
                        spawn_f = 15.0 + norm * (self.act1_end - 45.0) + jitter
                    else:
                        spawn_f = 20.0 + norm * (self.act1_end - 40.0) + jitter
                else:
                    if self.mode == "both":
                        spawn_f = self.act2_end + 15.0 + norm * (self.act3_end - self.act2_end - 45.0) + jitter
                    else:
                        spawn_f = 20.0 + norm * (self.act3_end - 40.0) + jitter

            spawn_f = max(1.0, spawn_f)
            land_f = spawn_f + fall_frames
            bounce_f = land_f + bounce_frames

            sign = -1.0 if is_bottom else 1.0
            drop_height = max(0.05, min(0.12, self.board_w * 0.7))

            # 1. Invisível desde o frame 1 até imediatamente antes do spawn
            obj.scale = Vector((0.0, 0.0, 0.0))
            obj.keyframe_insert(data_path="scale", frame=1)
            if int(spawn_f - 1) > 1:
                obj.keyframe_insert(data_path="scale", frame=int(spawn_f - 1))

            # 2. Posição no ar e visibilidade no frame de spawn
            spawn_loc = orig_loc + Vector((0, 0, sign * drop_height))
            if self.style == "vortex":
                v_radius = min(0.035, self.board_w * 0.3)
                v_theta = 3.5 * math.pi
                spawn_loc += Vector((v_radius * math.cos(v_theta), v_radius * math.sin(v_theta), 0))

            obj.location = spawn_loc
            obj.scale = orig_scale
            obj.keyframe_insert(data_path="scale", frame=int(spawn_f))
            obj.keyframe_insert(data_path="location", frame=int(spawn_f))

            # 3. Pouso na placa
            obj.location = orig_loc
            obj.keyframe_insert(data_path="location", frame=int(land_f))

            # 4. Rebote elástico
            bounce_height = 0.0025
            obj.location = orig_loc + Vector((0, 0, sign * bounce_height))
            mid_bounce = int((land_f + bounce_f) / 2.0)
            obj.keyframe_insert(data_path="location", frame=mid_bounce)

            # 5. Repouso final no lugar exato da montagem
            obj.location = orig_loc
            obj.keyframe_insert(data_path="location", frame=int(bounce_f))
            obj.keyframe_insert(data_path="location", frame=self.total_frames)
            obj.keyframe_insert(data_path="scale", frame=self.total_frames)

    def render_single_frame(self, frame_idx, out_file):
        total_frames = self._calculate_timeline()
        if frame_idx is None or frame_idx < 0:
            frame_idx = int(self.act3_end + (self.total_frames - self.act3_end) * 0.5) if self.mode != "bottom" else int(self.act1_end * 0.8)

        pbar = RenderProgressBar(1, prefix="Blender Preview")
        pbar.update(0, status="Configurando cena e shaders no Blender...")
        print("📦 Configurando cena e shaders no Blender...", flush=True)
        self._setup_scene()
        self._animate_camera()
        self._animate_components()

        print("\n" + "="*60, flush=True)
        print("📸 RENDERIZANDO QUADRO ESTÁTICO (BLENDER / BPY)", flush=True)
        print("="*60, flush=True)
        print(f"📁 Projeto PCB   : {os.path.basename(self.pcb_path)}", flush=True)
        print(f"🖼️ Quadro       : #{frame_idx} de {total_frames}", flush=True)
        print(f"⚙️ Motor Render  : {self.engine.upper()} (samples: {self.samples})", flush=True)
        print(f"🚀 Aceleração GPU: {self.gpu_info}", flush=True)
        print(f"💡 Luz           : Intensidade {self.light_intensity:.1f}x", flush=True)
        print(f"📺 Resolução     : {self.width}×{self.height}", flush=True)
        print("="*60 + "\n", flush=True)

        os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
        self.scene.render.filepath = os.path.abspath(out_file)
        self.scene.frame_set(frame_idx)

        pbar.update(0, status=f"Renderizando quadro #{frame_idx}...")
        print(f"⏳ Renderizando frame #{frame_idx}...", flush=True)
        bpy.ops.render.render(write_still=True)
        pbar.update(1, status="Finalizado")
        pbar.close("Preview gerado")
        print(f"\n✅ Quadro salvo com sucesso em: {out_file}\n", flush=True)
        return out_file

    def generate(self, output_mp4, output_gif=None):
        temp_dir = tempfile.mkdtemp(prefix="kicad_bpy_anim_")
        try:
            total_frames = self._calculate_timeline()

            print("📦 Configurando cena, shaders e keyframes procedurais no Blender...", flush=True)
            self._setup_scene()
            self._animate_camera()
            self._animate_components()

            print("\n" + "="*60, flush=True)
            print("🚀 INICIANDO RENDERIZAÇÃO DA ANIMAÇÃO 3D (BLENDER / BPY)", flush=True)
            print("="*60, flush=True)
            print(f"📁 Projeto PCB   : {os.path.basename(self.pcb_path)}", flush=True)
            print(f"📐 Dimensões     : {self.meta.width:.1f} mm × {self.meta.height:.1f} mm", flush=True)
            print(f"🧩 Componentes 3D: Top={len(self.meta.top_models)} | Bottom={len(self.meta.bot_models)}", flush=True)
            print(f"🎨 Estilo        : {STYLE_DESCRIPTIONS.get(self.style, self.style)}", flush=True)
            print(f"🔄 Modo          : {self.mode.upper()}", flush=True)
            print(f"⚙️ Motor Render  : {self.engine.upper()} (samples: {self.samples})", flush=True)
            print(f"🚀 Aceleração GPU: {self.gpu_info}", flush=True)
            print(f"📺 Resolução     : {self.width}×{self.height} @ {self.fps} fps", flush=True)
            print(f"⏱️ Duração       : {total_frames} frames ({total_frames/self.fps:.1f} segundos)", flush=True)
            print("="*60 + "\n", flush=True)

            if self.save_blend:
                blend_file = os.path.abspath(self.save_blend)
                os.makedirs(os.path.dirname(blend_file), exist_ok=True)
                bpy.ops.wm.save_as_mainfile(filepath=blend_file)
                print(f"💾 Cena Blender salva em: {blend_file}", flush=True)

            self.scene.frame_start = 1
            self.scene.frame_end = total_frames

            print("\n⏳ Renderizando quadros da animação...", flush=True)
            pbar = RenderProgressBar(total_frames, prefix="Blender Render")
            for f in range(1, total_frames + 1):
                self.scene.frame_set(f)
                frame_png = f"{temp_dir}/frame_{f:04d}.png"
                self.scene.render.filepath = frame_png
                bpy.ops.render.render(write_still=True)
                pbar.update(current=f)
            pbar.close("Todos os quadros renderizados")

            print("\n🎬 Codificando vídeo MP4 final com FFmpeg...", flush=True)
            self._encode_video(temp_dir, total_frames, output_mp4)

            if output_gif:
                print("🖼️ Gerando GIF otimizado de preview...", flush=True)
                self._encode_gif(output_mp4, output_gif)

            print("\n" + "-"*60, flush=True)
            print("✅ ANIMAÇÃO CONCLUÍDA COM SUCESSO!", flush=True)
            print(f"📹 Vídeo MP4 : {os.path.abspath(output_mp4)}", flush=True)
            if output_gif:
                print(f"🎞️ GIF        : {os.path.abspath(output_gif)}", flush=True)
            print("-"*60 + "\n", flush=True)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _encode_video(self, temp_dir, total_frames, output_mp4):
        os.makedirs(os.path.dirname(os.path.abspath(output_mp4)), exist_ok=True)
        cmd = [
            FFMPEG, "-y",
            "-framerate", str(self.fps),
            "-i", os.path.join(temp_dir, "frame_%04d.png").replace("\\", "/"),
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
