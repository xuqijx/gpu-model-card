#!/usr/bin/env python3
"""Print an estimated consumer-GPU model card. Python stdlib plus cardlib."""

from __future__ import annotations

import argparse
import sys

import cardlib


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print an estimated model card for a consumer GPU id."
    )
    parser.add_argument(
        "gpu_id",
        nargs="?",
        help="catalog id, for example rtx-5080-16gb",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list catalog GPU ids and exit",
    )
    parser.add_argument(
        "--vram",
        type=float,
        help="build a card from an entered VRAM size in GB instead of a catalog id",
    )
    parser.add_argument(
        "--name",
        default="",
        help="display name used with --vram",
    )
    args = parser.parse_args(argv)

    try:
        catalog = cardlib.load_catalog()
    except (OSError, ValueError) as exc:
        print(f"Could not read catalog: {exc}", file=sys.stderr)
        return 1

    if args.list:
        for gpu in catalog["gpus"]:
            print(f"{gpu['id']:<28} {gpu['name']:<36} {gpu['vram_gb']:>4g} GB  {gpu['class_label']}")
        return 0

    if args.vram is not None:
        if args.vram <= 0 or args.vram > 128:
            print("VRAM must be between 0 and 128 GB.", file=sys.stderr)
            return 2
        gpu = cardlib.synthetic_gpu(args.name, args.vram)
        sys.stdout.write(cardlib.render_card(catalog, gpu))
        return 0

    if not args.gpu_id:
        parser.print_help(sys.stderr)
        print("\nTry: python3 cli.py --list", file=sys.stderr)
        return 2

    gpu = cardlib.find_gpu(catalog, args.gpu_id)
    if gpu is None:
        print(f"Unknown GPU id '{args.gpu_id}'.", file=sys.stderr)
        print("Try: python3 cli.py --list", file=sys.stderr)
        return 2

    sys.stdout.write(cardlib.render_card(catalog, gpu))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
