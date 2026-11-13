"""
KiCad Animator - Gerenciador de Barra de Progresso Unificada (CLI & Desktop UI)
"""

import sys
import time

def format_time(seconds):
    """Converte segundos em string de tempo HH:MM:SS ou MM:SS."""
    seconds = int(max(0, seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

class RenderProgressBar:
    """
    Barra de progresso de alta precisão para renderização de quadros.
    Suporta modo interativo TTY (atualização no mesmo lugar com \\r)
    e modo capturado por subprocess/pipe (logs limpos linha a linha para GUI Web).
    """
    def __init__(self, total, prefix="Renderizando", bar_width=24):
        self.total = max(1, total)
        self.prefix = prefix
        self.bar_width = bar_width
        self.current = 0
        self.start_time = time.time()
        self.last_print_time = 0.0
        self.is_tty = sys.stdout.isatty()

    def update(self, current=None, step=1, status=None):
        if current is not None:
            self.current = current
        else:
            self.current += step

        self.current = min(self.total, max(0, self.current))
        now = time.time()
        elapsed = now - self.start_time
        pct = (self.current / self.total) * 100.0

        fps = self.current / elapsed if elapsed > 0.05 else 0.0
        remaining_frames = self.total - self.current
        eta_sec = (remaining_frames / fps) if fps > 0 else 0
        eta_str = format_time(eta_sec)

        # Visualização da barra em blocos
        filled_len = int(round(self.bar_width * self.current / float(self.total)))
        bar = "█" * filled_len + "░" * (self.bar_width - filled_len)

        status_suffix = f" • {status}" if status else ""

        if self.is_tty:
            line = (
                f"\r⏳ {self.prefix}: [{bar}] {pct:5.1f}% | "
                f"[{self.current}/{self.total}] | "
                f"{fps:4.1f} fps | ETA {eta_str}{status_suffix}"
            )
            sys.stdout.write(line)
            sys.stdout.flush()
            if self.current >= self.total:
                sys.stdout.write("\n")
                sys.stdout.flush()
        else:
            # Em modo pipe/GUI, emite linha com informações estruturadas
            # Filtro para emitir no mínimo a cada ~0.15s ou em quadros-chave
            if (now - self.last_print_time >= 0.15) or self.current == self.total or self.current <= 1:
                self.last_print_time = now
                line = (
                    f"⏳ [{self.current}/{self.total}] {pct:5.1f}% | "
                    f"[{bar}] | {fps:4.1f} fps | ETA {eta_str}{status_suffix}\n"
                )
                sys.stdout.write(line)
                sys.stdout.flush()

    def close(self, message="Concluído"):
        if self.current < self.total:
            self.update(current=self.total)
        elapsed = time.time() - self.start_time
        avg_fps = self.total / elapsed if elapsed > 0 else 0.0
        if self.is_tty:
            print(f"✨ {self.prefix}: {message} em {format_time(elapsed)} ({avg_fps:.1f} fps médio)\n", flush=True)
        else:
            print(f"✨ [{self.total}/{self.total}] 100.0% | {self.prefix} {message} em {format_time(elapsed)} ({avg_fps:.1f} fps médio)\n", flush=True)
