"""
KiCad Animator - Parser de Placa (.kicad_pcb)
"""

import os
import re
import math
import glob
from core.config import categorize_ref

class PCBMetaParser:
    def __init__(self, pcb_path):
        self.pcb_path = os.path.abspath(pcb_path)
        with open(self.pcb_path, "r", encoding="utf-8", errors="ignore") as f:
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

            # Ignora pontos de teste, furos mecânicos e fiduciais
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

def find_available_pcbs(root_dir=None):
    base = root_dir or os.getcwd()
    found = glob.glob(os.path.join(base, "**/*.kicad_pcb"), recursive=True) + glob.glob(os.path.join(base, "*.kicad_pcb"))
    parent_dir = os.path.dirname(os.path.abspath(base))
    jardim_pcb = os.path.join(parent_dir, "jardim", "hardware", "jardim.kicad_pcb")
    if os.path.exists(jardim_pcb):
        found.append(jardim_pcb)

    clean = [os.path.abspath(p) for p in set(found) if not p.endswith(".bak") and ".history" not in p]
    return sorted(clean)

def inspect_pcb_meta(pcb_path):
    if not pcb_path or not os.path.exists(pcb_path):
        return None
    try:
        p = PCBMetaParser(pcb_path)
        return {
            "width": p.width,
            "height": p.height,
            "top": len(p.top_models),
            "bottom": len(p.bot_models),
            "total_models": len(p.top_models) + len(p.bot_models)
        }
    except Exception:
        return None
