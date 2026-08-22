# FittedGenes: Domain-Aware Sewing Pattern Layout Optimization

**[Vision, Modeling, and Visualization (VMV) 2026](https://www.dgcv.org/gcpr-vmv-2026/)**
Ayşegül Barlas, Maria Korosteleva

📄 Paper *(Eurographics Digital Library link — to be added)* · 📄 Supplementary material *(to be added)*

Two-dimensional cutting and packing aims to arrange pieces on a larger surface without overlap while
minimizing material waste. Traditional nesting research assumes piece geometries are **fixed**. In this
work we make the garment design itself a variable of the nesting optimization: panel geometry is
modified under domain-aware constraints, preserving *fit* while allowing *appearance* to vary within
designer-set bounds.

We present an evolutionary nesting framework that embeds these modifications directly into a genetic
algorithm, with two novel mutation operators:

* **Split mutations** — a panel is divided into stitchable sub-panels along a construction-aware cut
  line (cuts never bisect darts; skirt cuts run parallel to the hemline normal). The reconstructed
  panel has the same outline, so a split changes where seams fall, not the silhouette.
* **Design-parameter mutations** — GarmentCode's decoupling of *body* from *design* parameters is
  exploited to regenerate panel geometry (flare, hem length, neckline depth, …) within a user-defined
  margin. Body measurements never enter the search space, so every returned layout fits the same wearer.

Alongside these we introduce **Cross-Stitch Crossover (CSX)**, a variable-length OX variant that
respects split integrity and design-parameter consistency, and a **policy-based objective** that
generalizes the classical strip-packing criterion (strip / bounding box / concave hull notions of
"used" fabric).

## Results

Evaluated on 98 patterns from [GarmentCodeData](https://igl.ethz.ch/projects/GarmentCodeData/) — proposed
here as a new benchmark for garment nesting — plus the 7 garment instances of the standard
[ESICUP](https://www.euro-online.org/websites/esicup/) set. 5 runs per pattern, averaged.

| Method          |   F ↓  |  η_B ↑ |   Φ ↑  |  η_H ↑ |
|-----------------|-------:|-------:|-------:|-------:|
| GA (sticky)     | 141.43 |  80.34 | 1.6266 |  84.37 |
| GA (lex.)       | 140.33 |  80.24 | 1.6270 |  84.33 |
| **NE (full)**   | **137.27** | **80.48** | **1.6332** | **84.39** |
| 2-Exchange      | 164.27 |  77.17 | 1.5664 |  82.59 |
| Random Search   | 152.69 |  76.32 | 1.5723 |  82.05 |

*F* is occupied strip length (cm), *η_B* / *η_H* are bounding-box and concave-hull fill rates (%), and
Φ = η_B + (L_max − F)/L_max is the combined objective.

Both proposed operators are individually necessary and mutually complementary: together they improve
fill rate by **2.32 percentage points**, reduce rest length by **12.06 cm (7.90%)**, and raise Φ by
**2.40%** over the permutation-only baseline. Notably, naive evolution (mutation only, no crossover)
outperforms the full GA, implying a rugged loss landscape.

## What is in this repository

This repository extends [GarmentCode](https://github.com/maria-korosteleva/GarmentCode) (Korosteleva &
Sorkine-Hornung), which supplies the parametric sewing-pattern representation the mutation operators
act on. The nesting contribution lives entirely under [`nesting/`](nesting/):

| Path | Contents |
|------|----------|
| `nesting/search/` | GA / naive evolution (`evolution.py`), chromosome encoding, mutation and crossover operators (`operations.py`), 2-exchange and random-search baselines, simulated annealing |
| `nesting/placement/` | Decoders: bottom-left heuristic and the NFP-based placement engine with its scoring policies |
| `nesting/core/` | Layout representation, geometry helpers, parameter handling |
| `nesting/data/` | Pattern loading, panel↔design-parameter mapping, path extraction |
| `nesting/runners/` | Experiment runners, including the master runner used for the paper |
| `nesting/analysis/` | Figure and table generation, mutation-effectiveness and metric-correlation analysis |
| `nesting/gui/` | Interactive nesting GUI (NiceGUI) |
| `nesting-assets/` | Benchmark pattern list, ESICUP instance specs, default body/design parameters |

Everything else (`pygarment/`, `assets/`, `docs/`) is upstream GarmentCode — see
[Upstream GarmentCode](#upstream-garmentcode) below.

## Installation

Follow the GarmentCode [installation instructions](docs/Installation.md) (Python 3.9, `system.json`
from `system.template.json`). The simulator is only needed for 3D draping — the nesting pipeline
itself does not require it.

```bash
conda env create -f environment.yaml
conda activate garment
```

## Quick start

Launch the nesting GUI on its own:

```bash
python -m nesting.gui        # http://localhost:8082
```

It loads the pattern named in `nesting/config.py` by default; you can also upload an external pattern
JSON. To use body and design parameters (and therefore design-parameter mutations), point
`default_pattern_path`, `default_design_param_path` and `default_body_param_path` in `SystemConfig` at
your files.

Or start from the GarmentCode configurator and hand the pattern over:

```bash
python gui.py               # design a garment, then click NEST in the left toolbar
```

The search may run for several minutes and the page will appear to disconnect while it does — do not
close the tab; it refreshes itself with the final layout. See [docs/Running_nesting.md](docs/Running_nesting.md).

## Reproducing the paper

All experiment settings are dataclasses in [`nesting/config.py`](nesting/config.py); the named
configurations (`ga_sticky`, `ga_lexicographic`, `ne_full`, `ne_no_rotations`, `ne_no_splits`,
`ne_no_params`, `ne_no_splits_no_params`, `two_exchange`, `random_search`, …) are defined in
`nesting/runners/run_all_experiments.py`.

```bash
# Main benchmark: 98 GarmentCodeData patterns × 5 runs (Tables 1 and 2)
python -m nesting.runners.run_all_experiments garmentcode \
    --patterns-file nesting-assets/patterns_paper98.txt --n-runs 5

# ESICUP garment instances (Section 5.4); specs live in nesting-assets/
python -m nesting.runners.run_all_experiments esicup --n-runs 5

# Decoder / placement-policy comparison
python -m nesting.runners.run_all_experiments decoder_comparison \
    --patterns-dir nesting-assets/pattern_files --n-patterns 1700

# NFP edge-sampling sweep
python -m nesting.runners.run_all_experiments nfp_sweep \
    --patterns-file nesting-assets/patterns_paper98.txt
```

Results are written to `nesting/experiments/runs_fresh/` as one CSV per group. Runs already present in
a CSV are skipped, so an interrupted sweep can simply be re-launched. Per-mutation, per-generation
data for the mutation-effectiveness figures is logged to `mutation_data.csv` for the `ne_full` and
`ne_no_rotations` configurations.

Then build every figure and LaTeX table:

```bash
python -m nesting.analysis.generate_results \
    --runs-dir nesting/experiments/runs_fresh \
    --stats-file nesting-assets/pattern_stats_98.csv \
    --output-dir nesting/experiments/results
```

**Benchmark details.** The 98 patterns are listed in `nesting-assets/patterns_paper98.txt` (sampled
with a fixed seed from the 3,450 patterns in `nesting-assets/pattern_files/`). GarmentCode runs use a
1 cm seam allowance on a 140 cm-wide fabric. ESICUP instances keep their native coordinate units, each
with its own fabric width, and use a seam allowance of 0.001 native units — exactly zero causes
degenerate NFP geometry.

A single run takes a median of ~9 minutes on an M3 MacBook Pro (8 GB); runtime is driven by panel
count rather than generation count, from a couple of minutes for 4-panel patterns to ~45 minutes for
20-panel ones.

## Citation

```bibtex
@inproceedings{FittedGenes2026,
  author    = {Barlas, Ay{\c{s}}eg{\"u}l and Korosteleva, Maria},
  title     = {{FittedGenes}: Domain-Aware Sewing Pattern Layout Optimization},
  booktitle = {Vision, Modeling, and Visualization},
  year      = {2026},
  publisher = {The Eurographics Association},
}
```

If you use the underlying pattern representation or the GarmentCodeData-derived benchmark, please also
cite the GarmentCode papers:

```bibtex
@article{GarmentCode2023,
  author = {Korosteleva, Maria and Sorkine-Hornung, Olga},
  title = {{GarmentCode}: Programming Parametric Sewing Patterns},
  year = {2023},
  issue_date = {December 2023},
  publisher = {Association for Computing Machinery},
  address = {New York, NY, USA},
  volume = {42},
  number = {6},
  doi = {10.1145/3618351},
  journal = {ACM Transaction on Graphics},
  note = {SIGGRAPH ASIA 2023 issue},
  numpages = {16},
  keywords = {sewing patterns, garment modeling}
}
```

```bibtex
@inproceedings{GarmentCodeData:2024,
  author = {Korosteleva, Maria and Kesdogan, Timur Levent and Kemper, Fabian and Wenninger, Stephan and Koller, Jasmin and Zhang, Yuhan and Botsch, Mario and Sorkine-Hornung, Olga},
  title = {{GarmentCodeData}: A Dataset of 3{D} Made-to-Measure Garments With Sewing Patterns},
  booktitle={Computer Vision -- ECCV 2024},
  year = {2024},
  keywords = {sewing patterns, garment reconstruction, dataset},
}
```

## Upstream GarmentCode

This fork tracks [maria-korosteleva/GarmentCode](https://github.com/maria-korosteleva/GarmentCode), the
official implementation of *GarmentCode: Programming Parametric Sewing Patterns* and *GarmentCodeData*.
An online configurator demo is available at [garmentcode.ethz.ch](https://garmentcode.ethz.ch/).

Upstream documentation, unchanged here:

1. [Installation](docs/Installation.md)
2. [Running the configurator](docs/Running_garmentcode.md)
3. [Running data generation (warp)](docs/Running_data_generation.md)
4. [Running nesting](docs/Running_nesting.md)
5. [Running the old Maya + Qualoth tools](docs/Running_Maya_Qualoth.md)
6. [Dataset documentation](https://www.research-collection.ethz.ch/handle/20.500.11850/673889)

[PyGarment](pygarment/) is the core upstream library (Edge, Panel, Component, Interface, the edge
factory and operators); `assets/garment_programs/` holds garment components written with it, and
`assets/design_params/`, `assets/bodies/` hold design and body-measurement presets. Body measurement
extraction lives in a separate repository:
[GarmentMeasurements](https://github.com/mbotsch/GarmentMeasurements).

## Contact

Questions about the nesting method or this repository: please open an issue here.
Questions about GarmentCode itself belong on the
[upstream issue tracker](https://github.com/maria-korosteleva/GarmentCode/issues).

## License

MIT — see [LICENSE](LICENSE). GarmentCode is © Maria Korosteleva.
