"""Hardware detection and quantization advice (B1.7).

Reads local, readily available signals (CPU count, platform, environment-var
RAM hint) and recommends a quantization level for a local model. No tools or
external commands are invoked; values the runtime cannot know are labelled
unknown rather than guessed.
"""

from __future__ import annotations

import os
import platform


def detect() -> dict:
    ram_gb = None
    raw = os.environ.get("KEEL_SYSTEM_RAM_GB", "")
    if raw:
        try:
            ram_gb = float(raw)
        except ValueError:
            ram_gb = None
    return {
        "os": platform.system(),
        "arch": platform.machine(),
        "cpu_count": os.cpu_count(),
        "ram_gb": ram_gb,
        "python": platform.python_version(),
    }


def advise_quantization(params_b: float, info: dict | None = None) -> dict:
    """Recommend a quantization level for a model of *params_b* billions."""
    info = info or detect()
    ram = info.get("ram_gb")
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
