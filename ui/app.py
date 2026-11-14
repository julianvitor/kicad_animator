"""
KiCad Animator - Desktop Web App Runner (pywebview)
"""

import os
import sys
import re
import time
import json
import base64
import tempfile
import threading
import subprocess

try:
    import webview
except ImportError:
    webview = None

from core.config import get_best_python, KICAD_CLI, FFMPEG, BLENDER_BIN, HAS_BPY
from core.parser import find_available_pcbs, inspect_pcb_meta

if getattr(sys, "frozen", False):
    BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    ROOT_DIR = os.path.dirname(os.path.abspath(sys.executable))
    UI_HTML_PATH = os.path.join(BUNDLE_DIR, "ui", "index.html")
    MAIN_SCRIPT = None
    PYTHON_BIN = sys.executable
else:
    ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    MAIN_SCRIPT = os.path.join(ROOT_DIR, "main.py")
    UI_HTML_PATH = os.path.join(os.path.dirname(__file__), "index.html")
    PYTHON_BIN = get_best_python()

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0

class DesktopApi:
    def __init__(self):
        self._window = None
        self._active_proc = None

    def _set_window(self, window):
        self._window = window

    def _run_on_ui_thread(self, fn):
        if sys.platform == "win32" and self._window and hasattr(self._window, "native"):
            try:
                import clr
                from System import Func, Type
                if self._window.native.InvokeRequired:
                    res = [None]
                    def _wrapper():
                        res[0] = fn()
                    self._window.native.Invoke(Func[Type](_wrapper))
                    return res[0]
            except Exception:
                pass
        return fn()

    def get_initial_data(self):
        pcbs = find_available_pcbs(ROOT_DIR)
        default_pcb = pcbs[0] if pcbs else ""
        default_out = ""
        if default_pcb:
            base_dir = os.path.dirname(os.path.abspath(default_pcb))
            exports_dir = os.path.join(base_dir, "exports", "animacoes")
            default_out = exports_dir if os.path.exists(exports_dir) else base_dir

        last_preview_b64 = None
        last_preview_path = None
        tmp_dir = tempfile.gettempdir()
        candidates = [
            os.path.join(tmp_dir, "preview_gui_blender.png"),
            os.path.join(tmp_dir, "preview_gui_kicad.png"),
            os.path.join(tmp_dir, "test_blender_still.png"),
            os.path.join(tmp_dir, "test_kicad_still.png"),
            os.path.join(tmp_dir, "preview_iluminacao.png")
        ]
        for c in candidates:
            if os.path.exists(c):
                try:
                    with open(c, "rb") as f:
                        last_preview_b64 = base64.b64encode(f.read()).decode("utf-8")
                        last_preview_path = c
                        break
                except Exception:
                    pass

        return {
            "pcbs": pcbs,
            "default_output": default_out,
            "last_preview_b64": last_preview_b64,
            "last_preview_path": last_preview_path,
            "has_kicad": bool(KICAD_CLI),
            "has_blender": bool(HAS_BPY or BLENDER_BIN),
            "has_ffmpeg": bool(FFMPEG),
            "is_frozen": getattr(sys, "frozen", False)
        }

    def inspect_pcb(self, pcb_path):
        return inspect_pcb_meta(pcb_path)

    def browse_pcb_file(self):
        # 1. No macOS: AppleScript nativo
        if sys.platform == "darwin":
            try:
                scpt = 'POSIX path of (choose file with prompt "Selecione o arquivo da placa KiCad (.kicad_pcb)" of type {"kicad_pcb", "public.data"})'
                r = subprocess.run(["osascript", "-e", scpt], capture_output=True, text=True)
                if r.returncode == 0 and r.stdout.strip():
                    return r.stdout.strip()
            except Exception:
                pass

        # 2. Diálogo nativo do pywebview (executado na thread STA da UI no Windows)
        try:
            if self._window:
                kicad_dir = os.path.expanduser("~/Documents/KiCad")
                init_dir = kicad_dir if os.path.isdir(kicad_dir) else os.path.expanduser("~")
                res = self._run_on_ui_thread(
                    lambda: self._window.create_file_dialog(
                        webview.FileDialog.OPEN,
                        directory=init_dir,
                        file_types=("KiCad PCB (*.kicad_pcb)", "All files (*.*)")
                    )
                )
                if res and len(res) > 0:
                    return res[0]
                return None
        except Exception:
            pass

        # 3. Fallback universal Tkinter (Linux)
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            f_path = filedialog.askopenfilename(
                title="Selecione o arquivo da placa KiCad (.kicad_pcb)",
                filetypes=[("KiCad PCB", "*.kicad_pcb"), ("Todos os arquivos", "*.*")]
            )
            root.destroy()
            if f_path:
                return f_path
        except Exception:
            pass

        return None

    def browse_output_dir(self):
        # 1. No macOS: AppleScript nativo
        if sys.platform == "darwin":
            try:
                scpt = 'POSIX path of (choose folder with prompt "Selecione a pasta para exportação das animações")'
                r = subprocess.run(["osascript", "-e", scpt], capture_output=True, text=True)
                if r.returncode == 0 and r.stdout.strip():
                    return r.stdout.strip()
            except Exception:
                pass

        # 2. Diálogo nativo do pywebview (executado na thread STA da UI no Windows)
        try:
            if self._window:
                kicad_dir = os.path.expanduser("~/Documents/KiCad")
                init_dir = kicad_dir if os.path.isdir(kicad_dir) else os.path.expanduser("~")
                res = self._run_on_ui_thread(
                    lambda: self._window.create_file_dialog(
                        webview.FileDialog.FOLDER,
                        directory=init_dir
                    )
                )
                if res and len(res) > 0:
                    return res[0]
                return None
        except Exception:
            pass

        # 3. Fallback universal Tkinter (Linux)
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            d_path = filedialog.askdirectory(title="Selecione a pasta para exportação das animações")
            root.destroy()
            if d_path:
                return d_path
        except Exception:
            pass

        return None

    def open_path(self, path):
        if path and os.path.exists(path):
            try:
                if sys.platform == "win32":
                    os.startfile(os.path.normpath(path))
                elif sys.platform == "darwin":
                    subprocess.run(["open", path])
                else:
                    subprocess.run(["xdg-open", path])
                return True
            except Exception:
                pass
        return False

    def _parse_and_emit_progress(self, line):
        m = re.search(r"\[(\d+)/(\d+)\]\s+([\d\.]+)%", line)
        if m:
            cur, tot, pct = int(m.group(1)), int(m.group(2)), float(m.group(3))
            eta_m = re.search(r"ETA\s+([\d:]+)", line)
            fps_m = re.search(r"([\d\.]+)\s+fps", line)
            eta = eta_m.group(1) if eta_m else ""
            fps_val = fps_m.group(1) if fps_m else ""

            # Para animações com múltiplos quadros, reserva 0-95% para os quadros 3D
            # e 95-100% para o muxing do vídeo FFmpeg / GIF
            if tot > 1:
                scaled_pct = min(95.0, (cur / float(tot)) * 95.0)
            else:
                scaled_pct = (cur / float(tot)) * 100.0

            status_msg = f"Frame {cur}/{tot} ({pct:.1f}%)"
            if fps_val:
                status_msg += f" • {fps_val} fps"
            self._emit_js(f"window.onProgress({scaled_pct:.1f}, {json.dumps(status_msg)}, {json.dumps(eta)})")
        elif "Codificando vídeo MP4" in line:
            self._emit_js("window.onProgress(96, 'Codificando MP4...', '')")
        elif "Gerando GIF" in line:
            self._emit_js("window.onProgress(98, 'Gerando GIF...', '')")
        elif "CONCLUÍDO COM SUCESSO" in line or "CONCLUÍDA COM SUCESSO" in line or "Quadro salvo com sucesso" in line:
            self._emit_js("window.onProgress(100, 'Renderização concluída', '')")

    def render_still_frame(self, params):
        if self._active_proc:
            return {"status": "error", "message": "Já existe um processo em execução."}

        pcb = params.get("pcb")
        backend = params.get("backend", "blender")
        res = params.get("res", "1080p")
        preview_out = os.path.join(tempfile.gettempdir(), f"preview_gui_{backend}.png")

        if getattr(sys, "frozen", False):
            cmd = [sys.executable]
        else:
            cmd = [PYTHON_BIN, MAIN_SCRIPT]

        cmd += [
            "--backend", backend,
            "--pcb", pcb,
            "--still-frame", "90",
            "--res", res,
            "--output", preview_out
        ]

        if backend == "blender":
            cmd += [
                "--engine", params.get("blender_engine", "eevee"),
                "--samples", str(params.get("blender_samples", 32)),
                "--light-intensity", str(params.get("light_intensity", 1.0))
            ]
        else:
            cmd += [
                "--workers", str(params.get("kicad_workers", 8)),
                "--kicad-quality", params.get("kicad_quality", "basic")
            ]

        def runner():
            try:
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                env["PYTHONUTF8"] = "1"
                proc = subprocess.Popen(
                    cmd,
                    cwd=ROOT_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    env=env,
                    creationflags=NO_WINDOW
                )
                self._active_proc = proc

                for line in iter(proc.stdout.readline, ""):
                    if not line: break
                    clean = line.strip()
                    self._emit_log(clean)
                    self._parse_and_emit_progress(clean)

                proc.wait()
                rc = proc.returncode

                if rc == 0 and os.path.exists(preview_out):
                    with open(preview_out, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    self._emit_js(f"window.onPreviewComplete('{b64}', {json.dumps(preview_out)})")
                else:
                    self._emit_log(f"❌ Falha ao gerar preview (Código {rc}).")
                    self._emit_js(f"window.onRenderComplete(false, 'Falha ao gerar preview (Código {rc}).')")
            except Exception as e:
                self._emit_log(f"❌ Erro crítico: {e}")
                self._emit_js(f"window.onRenderComplete(false, {json.dumps(str(e))})")
            finally:
                self._active_proc = None

        threading.Thread(target=runner, daemon=True).start()
        return {"status": "started"}

    def start_full_render(self, params):
        if self._active_proc:
            return {"status": "error", "message": "Já existe um processo em execução."}

        pcb = params.get("pcb")
        backend = params.get("backend", "blender")
        style = params.get("style", "rain")
        mode = params.get("mode", "both")
        res = params.get("res", "1080p")
        fps = str(params.get("fps", 60))
        out_dest = params.get("output", "")

        if getattr(sys, "frozen", False):
            cmd = [sys.executable]
        else:
            cmd = [PYTHON_BIN, MAIN_SCRIPT]

        cmd += [
            "--backend", backend,
            "--pcb", pcb,
            "--style", style,
            "--mode", mode,
            "--res", res,
            "--fps", fps,
            "--output", out_dest
        ]

        if params.get("gif"):
            cmd.append("--gif")

        if backend == "blender":
            cmd += [
                "--engine", params.get("blender_engine", "eevee"),
                "--samples", str(params.get("blender_samples", 32)),
                "--light-intensity", str(params.get("light_intensity", 1.0))
            ]
            if params.get("save_blend"):
                cmd.append("--save-blend")
        else:
            cmd += [
                "--workers", str(params.get("kicad_workers", 8)),
                "--kicad-quality", params.get("kicad_quality", "basic")
            ]

        def runner():
            try:
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                env["PYTHONUTF8"] = "1"
                proc = subprocess.Popen(
                    cmd,
                    cwd=ROOT_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    env=env,
                    creationflags=NO_WINDOW
                )
                self._active_proc = proc

                for line in iter(proc.stdout.readline, ""):
                    if not line: break
                    clean = line.strip()
                    self._emit_log(clean)
                    self._parse_and_emit_progress(clean)

                proc.wait()
                rc = proc.returncode

                if rc == 0:
                    self._emit_js("window.onRenderComplete(true, 'Renderização concluída.')")
                else:
                    self._emit_js(f"window.onRenderComplete(false, 'Renderização com erro (código {rc}).')")
            except Exception as e:
                self._emit_log(f"❌ Erro na renderização: {e}")
                self._emit_js(f"window.onRenderComplete(false, {json.dumps(str(e))})")
            finally:
                self._active_proc = None

        threading.Thread(target=runner, daemon=True).start()
        return {"status": "started"}

    def cancel_render(self):
        if self._active_proc:
            try:
                self._active_proc.terminate()
                time.sleep(0.4)
                if self._active_proc and self._active_proc.poll() is None:
                    self._active_proc.kill()
                self._emit_log("🛑 Processo cancelado.")
            except Exception as e:
                self._emit_log(f"Erro ao cancelar: {e}")
            self._active_proc = None
            self._emit_js("window.onRenderComplete(false, 'Cancelado pelo usuário.')")
            return {"status": "cancelled"}
        return {"status": "idle"}

    def _emit_log(self, text):
        if self._window and text:
            safe = json.dumps(text)
            self._emit_js(f"window.onLog({safe})")

    def _emit_js(self, code):
        if self._window:
            try:
                self._window.evaluate_js(code)
            except Exception:
                pass

def launch_ui():
    if webview is None:
        print("❌ Erro: 'pywebview' não está disponível.", file=sys.stderr)
        sys.exit(1)

    api = DesktopApi()
    window = webview.create_window(
        title="KiCad Animator",
        url=UI_HTML_PATH,
        js_api=api,
        width=1180,
        height=860,
        min_size=(960, 700),
        background_color="#090d16"
    )
    api._set_window(window)
    webview.start(debug=False)
