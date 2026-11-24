"""Hardware detection and quantization advice (B1.7).

Reads local, readily available signals (CPU count, platform, environment-var
RAM hint) and recommends a quantization level for a local model. No tools or
external commands are invoked; values the runtime cannot know are labelled
unknown rather than guessed.
"""

from __future__ import annotations

import math
import os
import platform
from functools import lru_cache


@lru_cache(maxsize=1)
def _platform_facts() -> tuple[str, str, str, int | None]:
    """Cache process-lifetime platform facts (bounded to a single entry).

    ``platform.system()``/``machine()`` query the OS on every call; doing that
    once keeps repeated ``detect()`` calls cheap without ever growing a cache.
    """
    return (platform.system(), platform.machine(),
            platform.python_version(), os.cpu_count())


def _ram_hint() -> float | None:
    """Parse the RAM hint, treating unusable values as unknown."""
    raw = os.environ.get("KEEL_SYSTEM_RAM_GB", "")
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    # NaN/infinity/zero/negative must not be fed into quantization math.
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def detect() -> dict:
    system, machine, python, cpu_count = _platform_facts()
    return {
        "os": system,
        "arch": machine,
        "cpu_count": cpu_count,
        "ram_gb": _ram_hint(),
        "python": python,
    }


def advise_quantization(params_b: float, info: dict | None = None) -> dict:
    """Recommend a quantization level for a model of *params_b* billions."""
    info = info or detect()
    ram = info.get("ram_gb")
    if ram is not None and (not isinstance(ram, (int, float))
                            or not math.isfinite(ram) or ram <= 0):
        ram = None
    needed_fp16 = params_b * 2
    if ram is None:
        return {"quant": "Q4_K_M", "reason": "RAM unknown; conservative default"}
    if ram >= needed_fp16 + 4:
        return {"quant": "F16", "reason": f"{ram} GB RAM fits fp16 weights"}
    if ram >= params_b + 4:
        return {"quant": "Q8_0", "reason": "fits 8-bit weights"}
    if ram >= params_b * 0.6 + 2:
        return {"quant": "Q4_K_M", "reason": "fits 4-bit weights"}
    return {"quant": "Q3_K_S", "reason": "low RAM; aggressive 3-bit quantization"}
