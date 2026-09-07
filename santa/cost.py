"""Preset → $/hour. Verified 2026-09-07 against https://docs.nebius.com/compute/resources/pricing.

H100 NVLink (gpu-h100-sxm) is billed per GPU-hour; CPU/RAM are included in that rate.
cpu-e2 (Intel Ice Lake) is billed per vCPU-hour + GiB-hour from the preset name.
"""

from __future__ import annotations

import re
from typing import NamedTuple

# GPU-hour, from June 1 2026 (USD). Source: docs.nebius.com/compute/resources/pricing
H100_ON_DEMAND_USD = 3.85
H100_PREEMPTIBLE_USD = 2.15

# Non-GPU Intel Ice Lake (cpu-e2) and AMD Epyc Genoa (cpu-d3) — same USD rates.
CPU_USD_PER_HOUR = 0.012
RAM_USD_PER_GIB_HOUR = 0.0032

_PRESET_GPU = re.compile(r"(\d+)gpu-", re.I)
_PRESET_CPU = re.compile(r"(\d+)vcpu-", re.I)
_PRESET_RAM = re.compile(r"-(\d+)gb", re.I)


class Rate(NamedTuple):
    usd_per_hour: float
    on_demand_usd_per_hour: float


def parse_preset(preset: str) -> tuple[int, int, int]:
    """Return ``(gpus, vcpus, ram_gib)`` parsed from a Nebius preset name."""
    gpus = int(m.group(1)) if (m := _PRESET_GPU.search(preset)) else 0
    vcpus = int(m.group(1)) if (m := _PRESET_CPU.search(preset)) else 0
    ram = int(m.group(1)) if (m := _PRESET_RAM.search(preset)) else 0
    return gpus, vcpus, ram


def hourly_rate(platform: str, preset: str, *, preemptible: bool = False) -> Rate:
    """USD per hour for one instance of ``platform``/``preset``."""
    gpus, vcpus, ram = parse_preset(preset)
    plat = platform.lower()
    if plat.startswith("gpu-h100"):
        on_demand = H100_ON_DEMAND_USD * max(gpus, 1)
        preempt = H100_PREEMPTIBLE_USD * max(gpus, 1)
        return Rate(
            usd_per_hour=preempt if preemptible else on_demand,
            on_demand_usd_per_hour=on_demand,
        )
    # cpu-e2 and other CPU platforms: vCPU + RAM
    on_demand = vcpus * CPU_USD_PER_HOUR + ram * RAM_USD_PER_GIB_HOUR
    return Rate(usd_per_hour=on_demand, on_demand_usd_per_hour=on_demand)


def cost_usd(
    platform: str,
    preset: str,
    seconds: float,
    *,
    preemptible: bool = False,
) -> float:
    """Cost for ``seconds`` of runtime. Partial hours are billed proportionally (1 s unit)."""
    rate = hourly_rate(platform, preset, preemptible=preemptible)
    return round(rate.usd_per_hour * (seconds / 3600.0), 6)


def on_demand_cost_usd(platform: str, preset: str, seconds: float) -> float:
    rate = hourly_rate(platform, preset, preemptible=False)
    return round(rate.on_demand_usd_per_hour * (seconds / 3600.0), 6)
