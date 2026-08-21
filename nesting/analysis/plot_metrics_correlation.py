#!/usr/bin/env python3
"""
Plot pairwise correlation heatmap across nesting quality metrics.
Reads final_metrics.csv (one row per run) and computes Pearson correlations
between all numeric result columns.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

try:
    from nesting import config as nesting_config
except Exception:
    nesting_config = None


METRICS = [
    "rest_length_cm",
    "usage_bb",
    "concave_hull_area",
    "concave_hull_utilization",
    "bb_area",
    "bb_cc_area",
    "bb_with_rest_length",
]

METRIC_LABELS = {
    "rest_length_cm": "Rest Length (cm)",
    "usage_bb": "BB Utilization",
    "concave_hull_area": "Concave Hull Area",
    "concave_hull_utilization": "Hull Utilization",
    "bb_area": "BB Area",
    "bb_cc_area": "BB+CC Area",
    "bb_with_rest_length": "BB w/ Rest",
}


def _resolve_final_metrics_csv() -> Path:
    candidates = []
    if nesting_config and hasattr(nesting_config, "AGGREGATE_DIR"):
        candidates.append(Path(nesting_config.AGGREGATE_DIR) / "final_metrics.csv")
    candidates.append(Path("nesting/experiments/aggregate/final_metrics.csv"))
    candidates.append(Path("experiments/aggregate/final_metrics.csv"))
    for p in candidates:
        if p.exists() and p.stat().st_size > 50:
            return p
    return candidates[0]


def load_metrics(csv_file: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_file)
    available = [c for c in METRICS if c in df.columns]
    if not available:
        raise ValueError(f"None of the expected metric columns found. Got: {list(df.columns)}")
    for col in available:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[available].dropna()


def plot_correlation_heatmap(df: pd.DataFrame, save_path=None) -> None:
    corr = df.corr(method="pearson")

    # Rename for display
    labels = [METRIC_LABELS.get(c, c) for c in corr.columns]
    corr.columns = labels
    corr.index = labels

    # Mask upper triangle for a cleaner look
    mask = np.triu(np.ones_like(corr, dtype=bool), k=1)

    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(
        corr,
        mask=mask,
        annot=True,
        fmt=".2f",
        cmap="coolwarm",
        center=0,
        vmin=-1,
        vmax=1,
        linewidths=0.5,
        ax=ax,
        annot_kws={"size": 14},
        cbar_kws={"label": "Pearson r", "shrink": 0.8},
    )
    ax.set_title("Pairwise Correlation of Nesting Quality Metrics", fontsize=18, fontweight="bold")
    plt.xticks(rotation=30, ha="right", fontsize=13)
    plt.yticks(rotation=0, fontsize=13)
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
        print(f"Heatmap saved to: {save_path}")
    else:
        plt.show()
    plt.close()


def print_top_correlations(df: pd.DataFrame, n: int = 10) -> None:
    corr = df.corr(method="pearson")
    pairs = (
        corr.where(np.tril(np.ones(corr.shape), k=-1).astype(bool))
        .stack()
        .reset_index()
    )
    pairs.columns = ["metric_a", "metric_b", "r"]
    pairs["abs_r"] = pairs["r"].abs()
    pairs = pairs.sort_values("abs_r", ascending=False)

    print(f"\nTop {n} correlations (by |r|):")
    for _, row in pairs.head(n).iterrows():
        direction = "+" if row["r"] > 0 else "-"
        print(f"  {direction}{row['abs_r']:.3f}  {row['metric_a']}  ↔  {row['metric_b']}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Plot pairwise correlation heatmap of nesting metrics")
    parser.add_argument("--config-hash", default=None, help="Filter to a specific config hash")
    parser.add_argument("--pattern", default=None, help="Filter to a specific pattern name")
    parser.add_argument("--output", default=None, help="Output PNG path (default: auto-named)")
    args = parser.parse_args()

    csv_path = _resolve_final_metrics_csv()
    print(f"Using metrics file: {csv_path}")
    if not csv_path.exists() or csv_path.stat().st_size <= 50:
        print("final_metrics.csv missing or empty. Run experiments to generate data.")
        sys.exit(0)

    raw = pd.read_csv(csv_path)
    if args.config_hash:
        raw = raw[raw["config_hash"] == args.config_hash]
        print(f"Filtered to config_hash={args.config_hash} → {len(raw)} runs")
    if args.pattern:
        raw = raw[raw["pattern_name"] == args.pattern]
        print(f"Filtered to pattern={args.pattern} → {len(raw)} runs")

    available = [c for c in METRICS if c in raw.columns]
    for col in available:
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    df = raw[available].dropna()
    print(f"Loaded {len(df)} runs with {len(df.columns)} metrics: {list(df.columns)}")

    print_top_correlations(df)

    if args.output:
        out = Path(args.output)
    elif args.config_hash:
        out = Path(f"metrics_correlation_{args.config_hash}.png")
    elif args.pattern:
        out = Path(f"metrics_correlation_{args.pattern}.png")
    else:
        out = Path("metrics_correlation_heatmap.png")

    plot_correlation_heatmap(df, save_path=out)
    print("\nDone!")


if __name__ == "__main__":
    main()
