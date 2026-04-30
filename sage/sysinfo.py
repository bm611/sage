"""System resource helpers — RAM monitoring for safe model loading."""
import re
from dataclasses import dataclass

import psutil

# Reserve this much headroom for the OS, your editor, browser, etc. Loading
# a model that would leave less than this free is treated as risky — macOS
# starts heavily swapping (and eventually freezing) well before true OOM.
_SAFETY_MARGIN_BYTES = 2 * 1024**3


@dataclass
class MemInfo:
    total: int       # bytes
    available: int   # bytes
    used: int        # bytes
    percent: float   # 0..100

    @property
    def total_gb(self) -> float:
        return self.total / 1024**3

    @property
    def available_gb(self) -> float:
        return self.available / 1024**3

    @property
    def used_gb(self) -> float:
        return self.used / 1024**3


def get_memory() -> MemInfo:
    vm = psutil.virtual_memory()
    return MemInfo(total=vm.total, available=vm.available, used=vm.used, percent=vm.percent)


def fmt_gb(n_bytes: int | float | None) -> str:
    if n_bytes is None:
        return "?"
    return f"{n_bytes / 1024**3:.1f} GB"


def memory_status_markup() -> str:
    """One-line Rich markup summary of system memory."""
    m = get_memory()
    if m.percent >= 85:
        color = "red"
    elif m.percent >= 70:
        color = "yellow"
    else:
        color = "green"
    return (
        f"[dim]RAM:[/dim] [{color}]{m.available_gb:.1f} GB free[/{color}] "
        f"[dim]/ {m.total_gb:.0f} GB total ({m.percent:.0f}% used)[/dim]"
    )


_PARAM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[bB](?![a-zA-Z])")


def estimate_size_from_id(model_id: str) -> int | None:
    """
    Heuristic: parse '7B', '9b', '13B' etc. from a model id and assume
    ~Q4 quantization (~0.6 bytes per parameter) for the RAM estimate.
    Returns bytes, or None if no parameter count is found.
    """
    m = _PARAM_RE.search(model_id)
    if not m:
        return None
    try:
        billions = float(m.group(1))
    except ValueError:
        return None
    if billions <= 0 or billions > 1000:
        return None
    return int(billions * 1e9 * 0.6)


def would_exceed_ram(model_size_bytes: int | None) -> tuple[bool, MemInfo]:
    """
    Return (will_exceed_safe_limit, mem_info).

    Loading a model typically allocates ~its on-disk size in RAM (GGUF mmap)
    plus a working set for KV cache. We warn if loading would leave less
    than _SAFETY_MARGIN_BYTES free for the rest of the system.
    """
    m = get_memory()
    if model_size_bytes is None:
        return False, m
    return model_size_bytes + _SAFETY_MARGIN_BYTES > m.available, m
