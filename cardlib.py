"""Load the model-card catalog and apply the shared estimate rule.

The fit labels are arithmetic on ballpark numbers. They are not benchmarks.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATALOG_PATH = ROOT / "data" / "catalog.json"

FIT_ORDER = ("likely", "tight", "partial_offload", "unlikely")
FIT_LABELS = {
    "likely": "Likely",
    "tight": "Tight",
    "partial_offload": "Partial offload",
    "unlikely": "Unlikely",
}


def load_catalog(path: Path | None = None) -> dict:
    catalog_path = Path(path) if path else CATALOG_PATH
    with catalog_path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("catalog root must be an object")
    return data


def classify(vram_gb: float, estimate_gb: float, rule: dict) -> str:
    """Classify one estimated model against one published VRAM size."""
    reserve = float(rule["reserve_gb"])
    likely_ratio = float(rule["likely_of_usable"])
    offload_ratio = float(rule["offload_of_vram"])
    usable = max(float(vram_gb) - reserve, 0.0)
    estimate = float(estimate_gb)
    if estimate <= usable * likely_ratio:
        return "likely"
    if estimate <= usable:
        return "tight"
    if estimate <= float(vram_gb) * offload_ratio:
        return "partial_offload"
    return "unlikely"


def synthetic_gpu(name: str, vram_gb: float) -> dict:
    shown = _fmt_gb(vram_gb).replace(" GB", "")
    return {
        "id": f"vram-{shown}",
        "name": name.strip() or f"Custom {shown} GB card",
        "vendor": "Custom entry",
        "vram_gb": float(vram_gb),
        "memory": "",
        "bus": "",
        "class_label": f"{shown} GB entered",
        "spec_note": "You entered this VRAM figure. This tool did not check it against a vendor spec.",
        "spec_url": "",
        "runtime_note": (
            "Runtime depends on the card vendor. NVIDIA hobby setups usually use a CUDA "
            "build of llama.cpp. AMD and Intel cards need a Vulkan, ROCm, or SYCL build."
        ),
        "capacity_notes": [
            f"Estimate: fit rows below use {shown} GB as the capacity in the shared rule.",
            "Estimate: match the exact VRAM on the box. Several GPU names ship in more than one size.",
            "Estimate: system RAM and disk columns are ballparks for a hobby PC, including the OS.",
        ],
    }


def rows_for(catalog: dict, vram_gb: float) -> list[dict]:
    rule = catalog["meta"]["fit_rule"]
    rows = []
    for model in catalog["models"]:
        fit = classify(vram_gb, model["vram_estimate_gb"], rule)
        rows.append({**model, "fit": fit})
    rows.sort(key=lambda row: (FIT_ORDER.index(row["fit"]), row["vram_estimate_gb"], row["name"], row["quant"]))
    return rows


def render_card(catalog: dict, gpu: dict) -> str:
    meta = catalog["meta"]
    rule = meta["fit_rule"]
    rows = rows_for(catalog, gpu["vram_gb"])
    counts = {key: 0 for key in FIT_ORDER}
    for row in rows:
        counts[row["fit"]] += 1

    lines = [
        meta["name"],
        "ESTIMATE — rounded ballparks. This repository did not measure tokens per second.",
        "",
        f"GPU: {gpu['name']}",
        f"Vendor: {gpu['vendor']}",
        f"Class: {gpu['class_label']}",
        f"Published VRAM: {_fmt_gb(gpu['vram_gb'])}"
        + (f" {gpu['memory']}" if gpu.get("memory") else "")
        + (f", {gpu['bus']}" if gpu.get("bus") else ""),
        f"Spec: {gpu['spec_note']}",
        f"Runtime: {gpu['runtime_note']}",
        "",
        "Capacity notes (estimates):",
    ]
    for note in gpu["capacity_notes"]:
        lines.append(f"- {note}")
    lines.extend(
        [
            "",
            "Fit rule (estimate): "
            f"usable = published VRAM - {rule['reserve_gb']:g} GB; "
            f"likely <= {rule['likely_of_usable']:g} of usable; "
            f"tight <= usable; "
            f"partial offload <= {rule['offload_of_vram']:g} x published VRAM; "
            "otherwise unlikely.",
            rule["context_note"],
            meta["estimate_basis"],
            "",
            "Counts: "
            + " · ".join(f"{counts[key]} {FIT_LABELS[key].lower()}" for key in FIT_ORDER),
            "",
            f"{'Fit':<16} {'Model':<36} {'Quant':<10} {'VRAM est.':>10} {'Disk est.':>10} {'RAM est.':>10}",
        ]
    )
    for row in rows:
        lines.append(
            f"{FIT_LABELS[row['fit']]:<16} "
            f"{_clip(row['name'], 36):<36} "
            f"{row['quant']:<10} "
            f"{_fmt_gb(row['vram_estimate_gb']):>10} "
            f"{_fmt_gb(row['disk_estimate_gb']):>10} "
            f"{_fmt_gb(row['system_ram_estimate_gb']):>10}"
        )
    lines.extend(["", "Start here:"])
    for link in meta["start_here"]:
        lines.append(f"- {link['label']}: {link['url']}")
        lines.append(f"  {link['note']}")
    lines.extend(["", meta["weights_note"], "", f"Catalog date: {meta['catalog_date']}. {meta['sample_label']}"])
    return "\n".join(lines) + "\n"


def find_gpu(catalog: dict, gpu_id: str) -> dict | None:
    key = gpu_id.strip().lower()
    for gpu in catalog["gpus"]:
        if gpu["id"] == key:
            return gpu
    return None


def _fmt_gb(value: float) -> str:
    number = round(float(value), 1)
    if number == int(number):
        return f"{int(number)} GB"
    return f"{number:.1f} GB"


def _clip(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"
