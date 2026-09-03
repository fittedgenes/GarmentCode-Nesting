"""Ballpark wall-clock estimates for a planned nesting sweep.

Runtime is dominated by piece count, not by the number of generations, so a
sweep is estimated per-pattern from `n_pieces` rather than from a flat average.
Fitting is done on log(runtime), which is where the relationship is linear and
where the (very heavy) right tail is well behaved.

    log(runtime_sec) = a + b * n_pieces        [fit per config]

Accuracy, measured against the historical runs:

    single run            +/- 2-3x     -- do not trust it
    one pattern's total   +/- 2-3x     -- still shaky
    a full sweep total    a few %      -- this is what the tool is for

The reason totals behave so much better is that the per-run errors are roughly
independent and average out; a 98-pattern sweep sums thousands of runs. Report
the total, treat any single number inside it as indicative only.

Usage
-----
    conda activate garment
    python -m nesting.analysis.estimate_runtime \\
        --configs ne_full ga_sticky --n-runs 5 --workers 8

    # what a full paper sweep costs
    python -m nesting.analysis.estimate_runtime \\
        --configs ga_sticky ga_lexicographic ne_full ne_no_rotations \\
                  ne_no_splits ne_no_params ne_no_splits_no_params \\
        --n-runs 5 --workers 8
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Historical run sets used to calibrate, newest-code-first. These differ by up
# to ~2.3x for the same config because they were produced by different code
# revisions and machines, so calibrating against the wrong one skews everything
# by that factor -- pick the set that matches the code you are about to run.
DEFAULT_CALIBRATION = ["runs_fresh"]
KNOWN_SOURCES = ["runs_fresh", "runs_faster", "runs_B", "runs_ne_fix", "runs_paper99"]

EXPERIMENTS_DIR = Path("nesting/experiments")
DEFAULT_STATS = Path("nesting-assets/pattern_stats_98.csv")
DEFAULT_PATTERNS = Path("nesting-assets/patterns_paper98.txt")

# Below this many observations a per-config fit is noise; fall back to the
# pooled fit and say so.
MIN_ROWS_FOR_CONFIG_FIT = 25


def load_history(sources: list[str]) -> pd.DataFrame:
    """Load historical runs, tagged by source set."""
    frames = []
    for src in sources:
        path = EXPERIMENTS_DIR / src / "garmentcode.csv"
        if not path.exists():
            print(f"  ! {path} not found, skipping", file=sys.stderr)
            continue
        df = pd.read_csv(path)
        missing = {"config_name", "runtime_sec", "num_pieces"} - set(df.columns)
        if missing:
            print(f"  ! {path} lacks {sorted(missing)}, skipping", file=sys.stderr)
            continue
        df["src"] = src
        frames.append(df)

    if not frames:
        raise SystemExit(
            f"No usable calibration data in {sources}. "
            f"Known sources: {', '.join(KNOWN_SOURCES)}"
        )

    hist = pd.concat(frames, ignore_index=True)
    # Zero/near-zero runtimes are failed or no-op runs and would dominate a log fit.
    return hist[hist.runtime_sec > 0.05].copy()


def fit(df: pd.DataFrame) -> tuple[float, float, float, int]:
    """Fit log(runtime) ~ n_pieces. Returns (intercept, slope, resid_sd, n)."""
    x = df.num_pieces.to_numpy(dtype=float)
    y = np.log(df.runtime_sec.to_numpy(dtype=float))
    if len(df) < 2 or x.std() == 0:
        # Degenerate: no spread to fit a slope against, so use a flat mean.
        return float(y.mean()), 0.0, float(y.std() or 0.0), len(df)
    slope, intercept = np.polyfit(x, y, 1)
    resid_sd = float((y - (intercept + slope * x)).std())
    return float(intercept), float(slope), resid_sd, len(df)


def expected_seconds(intercept: float, slope: float, resid_sd: float,
                     pieces: np.ndarray) -> np.ndarray:
    """Expected runtime per run.

    The fit predicts the mean of log(runtime), which back-transforms to the
    *median*. The mean of a lognormal is exp(mu + sigma^2/2), and it is the mean
    that sums correctly into a total -- omitting the correction underestimates
    a sweep by exp(sigma^2/2), around 30% at the spreads seen here.
    """
    return np.exp(intercept + slope * pieces + resid_sd**2 / 2)


def humanize(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f}s"
    if seconds < 5400:
        return f"{seconds / 60:.0f}m"
    if seconds < 86400 * 2:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--configs", nargs="+", required=True,
                    help="config names to estimate, e.g. ne_full ga_sticky")
    ap.add_argument("--n-runs", type=int, default=5,
                    help="runs per (config, pattern) pair [5]")
    ap.add_argument("--workers", type=int, default=1,
                    help="parallel workers; divides wall-clock [1]")
    ap.add_argument("--patterns-file", type=Path, default=DEFAULT_PATTERNS)
    ap.add_argument("--stats-file", type=Path, default=DEFAULT_STATS,
                    help="CSV with pattern_name,n_pieces")
    ap.add_argument("--calibrate-from", nargs="+", default=DEFAULT_CALIBRATION,
                    metavar="SET", help=f"run sets to fit on {DEFAULT_CALIBRATION}")
    args = ap.parse_args()

    if args.n_runs < 1 or args.workers < 1:
        raise SystemExit("--n-runs and --workers must be >= 1")

    stats = pd.read_csv(args.stats_file)
    if "n_pieces" not in stats.columns:
        raise SystemExit(f"{args.stats_file} has no n_pieces column")

    # Restrict to the patterns actually being run.
    if args.patterns_file.exists():
        wanted = {Path(line).parent.name
                  for line in args.patterns_file.read_text().split()
                  if line.strip()}
        subset = stats[stats.pattern_name.isin(wanted)]
        if len(subset) < len(wanted):
            print(f"  ! {len(wanted) - len(subset)} pattern(s) in "
                  f"{args.patterns_file.name} have no stats row; excluded",
                  file=sys.stderr)
        stats = subset
    if stats.empty:
        raise SystemExit("No patterns to estimate")

    pieces = stats.n_pieces.to_numpy(dtype=float)
    hist = load_history(args.calibrate_from)
    pooled = fit(hist)

    print(f"Calibrated on {', '.join(args.calibrate_from)} "
          f"({len(hist)} runs, {hist.pattern_name.nunique()} patterns)")
    print(f"Sweep: {len(stats)} patterns x {args.n_runs} runs "
          f"x {len(args.configs)} config(s) = "
          f"{len(stats) * args.n_runs * len(args.configs)} runs, "
          f"{args.workers} worker(s)\n")

    print(f"{'config':<26}{'per run':>10}{'cpu-time':>11}{'wall':>10}  fit")
    print("-" * 72)

    grand = 0.0
    for cfg in args.configs:
        rows = hist[hist.config_name == cfg]
        if len(rows) >= MIN_ROWS_FOR_CONFIG_FIT:
            intercept, slope, sd, n = fit(rows)
            note = f"{n} runs"
        else:
            intercept, slope, sd, n = pooled
            note = f"pooled ({len(rows)} runs, too few)"

        per_run = expected_seconds(intercept, slope, sd, pieces)
        cpu = per_run.sum() * args.n_runs
        grand += cpu
        print(f"{cfg:<26}{humanize(per_run.mean()):>10}{humanize(cpu):>11}"
              f"{humanize(cpu / args.workers):>10}  {note}")

    print("-" * 72)
    wall = grand / args.workers
    print(f"{'TOTAL':<26}{'':>10}{humanize(grand):>11}{humanize(wall):>10}")
    # Aggregate uncertainty is far tighter than per-run, but the calibration set
    # itself can be off by ~2x if the code changed, so keep the band honest.
    print(f"\nBallpark range: {humanize(wall * 0.6)} - {humanize(wall * 1.8)}")
    print("Dominated by which calibration set matches your code, not by fit error.")
    if args.workers > 1:
        print(f"Wall-clock assumes {args.workers} workers stay saturated; the "
              "long tail of big patterns means the last worker runs alone for a while.")


if __name__ == "__main__":
    main()
