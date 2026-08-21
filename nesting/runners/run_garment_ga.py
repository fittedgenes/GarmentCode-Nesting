"""
Parametrized GA runner for all supported garments.

Usage:
    python -m nesting.runners.run_garment_ga --garment shirts
    python -m nesting.runners.run_garment_ga --garment trousers --reps 5

Supported garments: shirts, trousers, dagli, mao, marques, swim

All runs use:
    - allowed_rotations: [0, 180]
    - container_width_cm: 400
    - seam_allowance_cm: 0.001
    - population_weights: { elites: 0.25, offspring: 0, mutants: 0.5, randoms: 0.25 }
    - mutation_weights: { rotate: 1, swap: 1, inversion: 1, insertion: 1, scramble: 1, split: 1, design_params: 0 }

Per-garment container heights are defined in GARMENT_CONFIGS below.
"""

from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import nesting.config as config
from nesting.runners.run_experiments import run_ga_on_patterns

# Per-garment configuration: pattern file name, container height, and optional rotation overrides
GARMENT_CONFIGS: dict[str, dict] = {
    "shirts":   {"file": "shirts.json",   "container_height_cm": 40},
    "trousers": {"file": "trousers.json", "container_height_cm": 79},
    "dagli":    {"file": "dagli.json",    "container_height_cm": 60},
    "mao":      {"file": "mao.json",      "container_height_cm": 51,  "allowed_rotations": [0, 90, 180, 270]},
    "marques":  {"file": "marques.json",  "container_height_cm": 104},
    "swim":     {"file": "swim.json",     "container_height_cm": 57},
}

SHARED_OVERRIDES = dict(
    allowed_rotations=[0, 180],
    container_width_cm=400,
    seam_allowance_cm=0.001,
    population_weights={"elites": 0.25, "offspring": 0, "mutants": 0.5, "randoms": 0.25},
    mutation_weights={
        "rotate": 1, "swap": 1, "inversion": 1, "insertion": 1,
        "scramble": 1, "split": 1, "design_params": 0,
    },
)


def main(garment: str, reps: int = 10) -> None:
    if garment not in GARMENT_CONFIGS:
        available = ", ".join(GARMENT_CONFIGS)
        raise ValueError(f"Unknown garment '{garment}'. Available: {available}")

    garment_cfg = GARMENT_CONFIGS[garment]
    overrides = {**SHARED_OVERRIDES, "container_height_cm": garment_cfg["container_height_cm"]}
    if "allowed_rotations" in garment_cfg:
        overrides["allowed_rotations"] = garment_cfg["allowed_rotations"]
    config.load_config(**overrides)

    pattern_path = _repo_root / "nesting-assets" / garment_cfg["file"]
    if not pattern_path.exists():
        raise FileNotFoundError(f"Pattern file not found: {pattern_path}")

    base_out = _repo_root / "results" / f"{garment}_experiment"
    os.makedirs(base_out, exist_ok=True)

    print(f"Running GA on: {pattern_path}")
    print(f"Garment: {garment}  |  container height: {garment_cfg['container_height_cm']} cm")
    print(f"Repetitions: {reps}")

    for i in range(1, reps + 1):
        out_dir = base_out / f"run_{i:02d}"
        print(f"\n=== Starting repetition {i}/{reps} -> {out_dir} ===")
        run_ga_on_patterns([str(pattern_path)], output_dir=str(out_dir))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run GA nesting for a specific garment.")
    parser.add_argument(
        "--garment",
        required=True,
        choices=list(GARMENT_CONFIGS),
        help="Garment type to nest",
    )
    parser.add_argument(
        "--reps",
        type=int,
        default=int(os.getenv("GA_REPS", "10")),
        help="Number of repetitions (default: 10, overridable via GA_REPS env var)",
    )
    args = parser.parse_args()
    main(garment=args.garment, reps=args.reps)
