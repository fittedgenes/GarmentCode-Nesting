#!/usr/bin/env python3
"""
Process evolution SVGs to add consistent piece coloring and extract metrics.
Saves metrics for each generation and creates colored SVG copies.
"""
import sys
import re
import csv
from pathlib import Path
from lxml import etree

sys.path.insert(0, str(Path(__file__).parent))

# Color palette - 20 distinct colors for up to 20 pieces
COLORS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8",
    "#F7DC6F", "#BB8FCE", "#85C1E2", "#F8B88B", "#ABEBC6",
    "#D7BDE2", "#FAD7A0", "#A3E4D7", "#F5B7B1", "#D5F4E6",
    "#FADBD8", "#D5F4E6", "#EBDEF0", "#FCF3CF", "#D6EAF8"
]

def extract_piece_ids(svg_file):
    """Extract piece IDs from SVG file (polygon order)."""
    tree = etree.parse(svg_file)
    root = tree.getroot()
    ns = {'svg': 'http://www.w3.org/2000/svg'}
    polygons = root.findall('.//svg:polygon', ns)
    return len(polygons)

def parse_evolution_log(log_file):
    """Extract per-generation metrics from evolution log."""
    generations = {}
    current_gen = None

    with open(log_file, 'r') as f:
        for line in f:
            # Pattern: "Generation N: best X.XXXX (Δ +Y.YYYY)"
            match = re.search(r'Generation (\d+): best ([\d.]+)', line)
            if match:
                gen_num = int(match.group(1))
                fitness = float(match.group(2))
                generations[gen_num] = {'fitness': fitness}

    return generations

def add_colors_to_svg(svg_file, output_file, piece_colors):
    """Add consistent colors to polygon pieces in SVG."""
    tree = etree.parse(svg_file)
    root = tree.getroot()
    ns = {'svg': 'http://www.w3.org/2000/svg'}

    polygons = root.findall('.//svg:polygon', ns)

    for idx, polygon in enumerate(polygons):
        color_idx = idx % len(piece_colors)
        if color_idx not in piece_colors:
            piece_colors[color_idx] = COLORS[color_idx % len(COLORS)]

        # Update fill color
        polygon.set('fill', piece_colors[color_idx])
        polygon.set('stroke', 'darkblue')
        polygon.set('stroke-width', '0.3')

    tree.write(output_file, encoding='utf-8', xml_declaration=True)

def process_run(run_dir):
    """Process a single evolution run."""
    run_path = Path(run_dir)
    log_file = list(run_path.glob("evolution_log_*.txt"))[0]
    svgs_dir = run_path / "svgs"
    colored_svgs_dir = run_path / "svgs_colored"

    if not colored_svgs_dir.exists():
        colored_svgs_dir.mkdir()

    # Parse metrics
    generations = parse_evolution_log(log_file)

    # Assign consistent colors to pieces (same for all generations)
    num_pieces = extract_piece_ids(svgs_dir / "gen_0001.svg")
    piece_colors = {i: COLORS[i % len(COLORS)] for i in range(num_pieces)}

    # Process each generation SVG
    metrics_list = []
    for gen_num in sorted(generations.keys()):
        svg_file = svgs_dir / f"gen_{gen_num:04d}.svg"
        colored_svg = colored_svgs_dir / f"gen_{gen_num:04d}.svg"

        if svg_file.exists():
            add_colors_to_svg(svg_file, colored_svg, piece_colors)

            # Extract metric (fitness is bb_with_rest_length)
            # For now just save generation number and fitness
            metrics_list.append({
                'generation': gen_num,
                'fitness_bb_with_rest': generations[gen_num]['fitness'],
                'num_pieces': num_pieces
            })

            print(f"  Gen {gen_num}: {generations[gen_num]['fitness']:.4f}")

    # Save metrics CSV
    metrics_file = run_path / "generation_metrics.csv"
    if metrics_list:
        with open(metrics_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['generation', 'fitness_bb_with_rest', 'num_pieces'])
            writer.writeheader()
            writer.writerows(metrics_list)
        print(f"\nMetrics saved to: {metrics_file}")

    print(f"Colored SVGs saved to: {colored_svgs_dir}")
    return metrics_file

if __name__ == "__main__":
    # Find the latest run
    runs_dir = Path("nesting/experiments/runs")
    latest_run = max([d for d in runs_dir.glob("rand_0JVMGTZZ5G_*") if d.is_dir()],
                     key=lambda d: d.stat().st_mtime)

    print(f"Processing: {latest_run.name}")
    print("Extracting metrics...\n")
    process_run(latest_run)
