"""
KiCad Animator - Core Module
"""

from .config import (
    HAS_BPY,
    KICAD_CLI,
    FFMPEG,
    RES_MAP,
    ALL_STYLES,
    STYLE_DESCRIPTIONS,
    get_best_python,
    categorize_ref,
    categorize_signal_stage
)
from .parser import PCBMetaParser, find_available_pcbs, inspect_pcb_meta
from .jobs import resolve_jobs, prompt_terminal_interactive
from .progress import RenderProgressBar, format_time
