#!/usr/bin/env python3
"""Validate catalog shape and the shared estimate rule. Exits 0 on success."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cardlib  # noqa: E402

GPU_KEYS = {
    "id",
    "name",
    "vendor",
    "vram_gb",
    "memory",
    "bus",
    "class_label",
    "spec_note",
    "spec_url",
    "runtime_note",
    "capacity_notes",
}
MODEL_KEYS = {
    "id",
    "name",
    "params_label",
    "quant",
    "tag",
    "disk_estimate_gb",
    "vram_estimate_gb",
    "system_ram_estimate_gb",
    "estimate",
    "note",
    "model_card_url",
}

# Locked examples so a silent rule inversion fails the check.
EXPECT = {
    ("rtx-5080-16gb", "llama-3.1-8b-q4"): "likely",
    ("rtx-5080-16gb", "qwen2.5-14b-q4"): "likely",
    ("rtx-5080-16gb", "gemma-2-27b-q4"): "partial_offload",
    ("rtx-5080-16gb", "llama-3.3-70b-q4"): "unlikely",
    ("rtx-3060-12gb", "llama-3.1-8b-q8"): "tight",
    ("rtx-3060-12gb", "phi-4-q4"): "tight",
    ("rtx-4060-8gb", "llama-3.2-3b-q4"): "likely",
    ("rtx-4060-8gb", "llama-3.1-8b-q4"): "tight",
    ("rtx-4090-24gb", "qwen2.5-32b-q4"): "tight",
    ("rtx-5090-32gb", "qwen2.5-32b-q4"): "likely",
    ("rtx-5090-32gb", "llama-3.3-70b-q4"): "partial_offload",
}


def fail(message: str) -> None:
    print(f"check failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_url(value: str, label: str) -> None:
    if not (value.startswith("https://") or value.startswith("http://")):
        fail(f"{label} must be an http(s) URL, got {value!r}")


def main() -> int:
    catalog = cardlib.load_catalog()
    meta = catalog.get("meta")
    gpus = catalog.get("gpus")
    models = catalog.get("models")
    if not isinstance(meta, dict):
        fail("meta must be an object")
    if not isinstance(gpus, list) or not isinstance(models, list):
        fail("gpus and models must be arrays")

    disclaimer = str(meta.get("disclaimer", "")).lower()
    if "estimate" not in disclaimer:
        fail("meta.disclaimer must say these figures are estimates")
    if "benchmark" in disclaimer and "did not" not in disclaimer:
        fail("disclaimer must not claim benchmarks")
    basis = str(meta.get("estimate_basis", "")).lower()
    if "estimate" not in basis:
        fail("meta.estimate_basis must describe the estimate")
    sample = str(meta.get("sample_label", "")).lower()
    if "sample" not in sample:
        fail("meta.sample_label must identify the catalog as a sample")

    rule = meta.get("fit_rule")
    if not isinstance(rule, dict):
        fail("meta.fit_rule missing")
    for key in ("reserve_gb", "likely_of_usable", "offload_of_vram", "context_note"):
        if key not in rule:
            fail(f"fit_rule.{key} missing")
    if "estimate" not in str(rule["context_note"]).lower():
        fail("fit_rule.context_note must be labeled as an estimate")

    if len(gpus) < 8:
        fail(f"need at least 8 GPUs, found {len(gpus)}")
    if len(models) < 12:
        fail(f"need at least 12 models, found {len(models)}")

    gpu_ids = [gpu.get("id") for gpu in gpus]
    if len(gpu_ids) != len(set(gpu_ids)):
        fail("GPU ids must be unique")
    model_ids = [model.get("id") for model in models]
    if len(model_ids) != len(set(model_ids)):
        fail("model ids must be unique")

    vram_sizes = set()
    classes = set()
    for gpu in gpus:
        missing = GPU_KEYS - gpu.keys()
        if missing:
            fail(f"GPU {gpu.get('id')} missing {sorted(missing)}")
        if not isinstance(gpu["vram_gb"], (int, float)) or not (4 <= float(gpu["vram_gb"]) <= 48):
            fail(f"GPU {gpu['id']} has implausible vram_gb")
        if not gpu["id"] or gpu["id"] != str(gpu["id"]).lower():
            fail(f"GPU id {gpu['id']!r} must be lowercase")
        notes = gpu["capacity_notes"]
        if not isinstance(notes, list) or len(notes) < 2:
            fail(f"GPU {gpu['id']} needs capacity notes")
        for note in notes:
            if not str(note).startswith("Estimate:"):
                fail(f"GPU {gpu['id']} capacity note must start with 'Estimate:'")
        if gpu["spec_url"]:
            require_url(gpu["spec_url"], f"{gpu['id']} spec_url")
        vram_sizes.add(int(gpu["vram_gb"]))
        classes.add(gpu["class_label"])

    if 12 not in vram_sizes or 16 not in vram_sizes:
        fail("catalog must include both a 12GB and a 16GB consumer GPU")
    if "12GB class" not in classes or "16GB class" not in classes:
        fail("class labels must include 12GB class and 16GB class")

    for model in models:
        missing = MODEL_KEYS - model.keys()
        if missing:
            fail(f"model {model.get('id')} missing {sorted(missing)}")
        if model["estimate"] is not True:
            fail(f"model {model['id']} must set estimate true")
        for field in ("disk_estimate_gb", "vram_estimate_gb", "system_ram_estimate_gb"):
            value = model[field]
            if not isinstance(value, (int, float)) or float(value) <= 0:
                fail(f"model {model['id']} {field} must be a positive number")
        if float(model["vram_estimate_gb"]) + 0.05 < float(model["disk_estimate_gb"]) * 0.8:
            fail(f"model {model['id']} VRAM estimate is far below its disk estimate")
        if not model["quant"] or not model["name"]:
            fail(f"model {model['id']} needs a name and quant")
        require_url(model["model_card_url"], f"{model['id']} model_card_url")
        blob = " ".join(
            [
                model["name"],
                model["note"],
                str(model["vram_estimate_gb"]),
            ]
        ).lower()
        if "tokens/sec" in blob or "tok/s" in blob:
            fail(f"model {model['id']} must not claim a speed measurement")

    by_gpu = {gpu["id"]: gpu for gpu in gpus}
    by_model = {model["id"]: model for model in models}
    for (gpu_id, model_id), expected in EXPECT.items():
        got = cardlib.classify(
            by_gpu[gpu_id]["vram_gb"],
            by_model[model_id]["vram_estimate_gb"],
            rule,
        )
        if got != expected:
            fail(f"{gpu_id} + {model_id} classified {got}, expected {expected}")

    index = ROOT / "index.html"
    if not index.is_file():
        fail("index.html missing")
    html = index.read_text(encoding="utf-8").lower()
    for snippet in ("data/catalog.json", "vram est.", "disk est.", "system ram est.", "estimate"):
        if snippet not in html:
            fail(f"index.html must contain {snippet!r}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for marker in ("#english", "#zh-hans", "#zh-hant", "#ja", "简体中文", "繁體中文", "日本語"):
        if marker not in readme:
            fail(f"README language switch missing {marker}")

    if not (ROOT / "LICENSE").is_file():
        fail("LICENSE missing")
    if "MIT" not in (ROOT / "LICENSE").read_text(encoding="utf-8"):
        fail("LICENSE must be MIT")

    demo = ROOT / "docs" / "demo-rtx-5080-card.png"
    if not demo.is_file() or demo.stat().st_size < 10000:
        fail("docs/demo-rtx-5080-card.png missing or too small to be a real capture")

    proc = subprocess.run(
        [sys.executable, str(ROOT / "cli.py"), "rtx-5080-16gb"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        fail(f"cli.py exited {proc.returncode}: {proc.stderr.strip()}")
    output = proc.stdout
    for snippet in ("ESTIMATE", "VRAM est.", "Disk est.", "RAM est.", "Llama 3.1 8B Instruct", "Likely"):
        if snippet not in output:
            fail(f"cli output missing {snippet!r}")
    if "tokens per second" in output.lower() and "did not measure" not in output.lower():
        fail("cli output must not claim a speed measurement")

    print(
        f"ok: {len(gpus)} GPUs, {len(models)} models, "
        f"12GB and 16GB present, estimate labels held, cli exit 0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
