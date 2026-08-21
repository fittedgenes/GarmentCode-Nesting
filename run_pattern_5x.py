#!/usr/bin/env python3
"""
Run rand_0JVMGTZZ5G pattern 5 times with container_width_cm=800 and current GA config.
"""
import sys
import copy
import yaml
from pathlib import Path

# Add GarmentCode to path
sys.path.insert(0, str(Path(__file__).parent))

from nesting.data.path_extractor import PatternPathExtractor
from nesting.core.layout import Container
from nesting.search.evolution import Evolution
from nesting.analysis.metastatistics import MetaStatistics
from assets.bodies.body_params import BodyParameters
from nesting import config

def main():
    pattern_name = "rand_0JVMGTZZ5G"
    spec_path = Path(f"nesting-assets/pattern_files/{pattern_name}/{pattern_name}_specification.json")

    if not spec_path.exists():
        print(f"ERROR: Pattern file not found: {spec_path}")
        sys.exit(1)

    # Configure: set container width to 800cm
    config.ACTIVE.container_width_cm = 800

    print(f"Running {pattern_name} with container_width_cm=800")
    print(f"Config: {config.ACTIVE.selected_decoder}, {config.ACTIVE.selected_fitness_metric}")
    print(f"Population: {config.ACTIVE.population_size}, Generations: {config.ACTIVE.num_generations}")
    print(f"Running 5 times...\n")

    # Load pattern pieces once
    extractor = PatternPathExtractor(spec_path)
    pieces_list = extractor.get_all_panel_pieces(samples_per_edge=config.ACTIVE.samples_per_edge)
    pieces = {}
    for pid, piece in pieces_list.items():
        p = copy.deepcopy(piece)
        p.add_seam_allowance(config.ACTIVE.seam_allowance_cm)
        p.translation = (0, 0)
        pieces[str(pid)] = p

    # Load design params from YAML
    design_params = None
    dp_path = spec_path.parent / f"{pattern_name}_design_params.yaml"
    if dp_path.exists():
        with open(dp_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        design_params = data.get("design")

    # Load body params from YAML
    body_params = None
    bp_path = spec_path.parent / f"{pattern_name}_body_measurements.yaml"
    if bp_path.exists():
        body_params = BodyParameters(bp_path)

    for run_num in range(1, 6):
        print(f"{'='*60}")
        print(f"Run {run_num}/5")
        print(f"{'='*60}")

        container = Container(config.ACTIVE.container_width_cm, config.ACTIVE.container_height_cm)
        run_tag = MetaStatistics._get_default_run_tag()
        config_hash = config.get_stable_hash()[:8]

        evolution = Evolution(
            copy.deepcopy(pieces),
            container,
            num_generations=config.ACTIVE.num_generations,
            population_size=config.ACTIVE.population_size,
            mutation_rate=config.ACTIVE.mutation_rate,
            enable_dynamic_stopping=config.ACTIVE.enable_dynamic_stopping,
            early_stop_window=config.ACTIVE.early_stop_window,
            early_stop_tolerance=config.ACTIVE.early_stop_tolerance,
            enable_extension=config.ACTIVE.enable_extension,
            extend_window=config.ACTIVE.extend_window,
            extend_threshold=config.ACTIVE.extend_threshold,
            max_generations=config.ACTIVE.max_generations,
            design_params=design_params,
            body_params=body_params,
            pattern_name=pattern_name,
            run_tag=run_tag,
            config_hash=config_hash,
        )

        evolution.run()
        log_dir = evolution.log_path.parent
        print(f"\nRun {run_num} complete. Results saved to: {log_dir}\n")

if __name__ == "__main__":
    main()
