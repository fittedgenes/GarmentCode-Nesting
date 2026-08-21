#!/usr/bin/env python3
"""
Create an evolution progression SVG from the top 6 generations with most improvement.
Adds labels, fitness values, and final metrics.
"""
import sys
import re
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))

import svgwrite
from lxml import etree

def parse_evolution_log(log_file):
    """Extract generation data (number, fitness, delta) from evolution log."""
    generations = {}
    with open(log_file, 'r') as f:
        for line in f:
            # Pattern: "Generation N: best X.XXXX (Δ +Y.YYYY) (from initial: +Z.ZZZZ)"
            match = re.search(r'Generation (\d+): best ([\d.]+) \(Δ ([+-][\d.]+)\)', line)
            if match:
                gen_num = int(match.group(1))
                fitness = float(match.group(2))
                delta = float(match.group(3))
                generations[gen_num] = {'fitness': fitness, 'delta': delta}
    return generations

def get_top_6_generators(generations):
    """Get 6 generations with largest improvement (delta)."""
    sorted_gens = sorted(generations.items(), key=lambda x: x[1]['delta'], reverse=True)
    top_6 = sorted_gens[:6]
    return sorted(top_6, key=lambda x: x[0])  # Sort by generation number for display

def load_svg_content(svg_file):
    """Load SVG content and return the viewBox and polygons."""
    tree = etree.parse(svg_file)
    root = tree.getroot()

    # Get viewBox
    viewbox = root.get('viewBox')
    width = root.get('width')
    height = root.get('height')

    # Extract all polygons
    ns = {'svg': 'http://www.w3.org/2000/svg'}
    polygons = root.findall('.//svg:polygon', ns)

    return viewbox, width, height, polygons

def create_evolution_viz(run_dir, output_file):
    """Create combined evolution visualization."""
    run_path = Path(run_dir)
    log_file = list(run_path.glob("evolution_log_*.txt"))[0]
    svgs_dir = run_path / "svgs"

    # Parse log
    generations = parse_evolution_log(log_file)
    top_6 = get_top_6_generators(generations)

    print(f"Top 6 generations by improvement:")
    for gen_num, data in top_6:
        print(f"  Gen {gen_num}: fitness={data['fitness']:.4f}, delta={data['delta']:.4f}")

    # Create output SVG with grid layout (2 rows x 3 cols)
    # Fabric dimensions: 800 cm x 140 cm, so aspect ratio is ~5.71:1
    cell_height = 120  # Height in pixels
    cell_width = int(cell_height * 5.71)  # Match 800:140 ratio
    grid_cols = 3
    grid_rows = 2
    padding = 30
    label_height = 60

    total_width = grid_cols * (cell_width + padding) + padding
    total_height = grid_rows * (cell_height + label_height + padding) + padding + 100  # Extra space for final metrics

    dwg = svgwrite.Drawing(output_file, size=(f"{total_width}px", f"{total_height}px"))
    dwg.add(dwg.rect(insert=(0, 0), size=(f"{total_width}px", f"{total_height}px"), fill="white"))

    # Add title
    title = dwg.text("Evolution Progress: Top 6 Generations by Improvement",
                     insert=(total_width/2, 25),
                     text_anchor="middle",
                     font_size="20",
                     font_weight="bold")
    dwg.add(title)

    # Add each SVG
    for idx, (gen_num, gen_data) in enumerate(top_6):
        row = idx // grid_cols
        col = idx % grid_cols

        x = padding + col * (cell_width + padding)
        y = padding + 30 + row * (cell_height + label_height + padding)

        svg_file = svgs_dir / f"gen_{gen_num:04d}.svg"
        if not svg_file.exists():
            print(f"  WARNING: {svg_file} not found")
            continue

        # Load SVG
        try:
            viewbox, width, height, polygons = load_svg_content(svg_file)

            # Create group for this generation
            g = dwg.g(id=f"gen_{gen_num}")

            # Add dashed bounding box (fabric boundary)
            g.add(dwg.rect(insert=(x, y), size=(cell_width, cell_height),
                          fill="white", stroke="black", stroke_width="2",
                          stroke_dasharray="5,5"))

            # Add scaled polygons
            if viewbox:
                vb_parts = viewbox.split()
                vb_width = float(vb_parts[2])
                vb_height = float(vb_parts[3])
                scale_x = cell_width / vb_width
                scale_y = cell_height / vb_height
                scale = min(scale_x, scale_y) * 0.9
            else:
                scale = 1

            for polygon in polygons:
                points_str = polygon.get('points')
                if points_str:
                    points = []
                    # Split by space, then by comma
                    coord_pairs = re.findall(r'([\d.-]+),([\d.-]+)', points_str)
                    for px_str, py_str in coord_pairs:
                        px = float(px_str) * scale + x + 10
                        py = float(py_str) * scale + y + 10
                        points.append((px, py))

                    if points:
                        g.add(dwg.polygon(points=points, fill="lightblue",
                                         stroke="darkblue", stroke_width="0.5"))

            dwg.add(g)

            # Add label below
            label_y = y + cell_height + 15
            label_text = f"Gen {gen_num}"
            dwg.add(dwg.text(label_text, insert=(x + cell_width/2, label_y),
                           text_anchor="middle", font_size="12", font_weight="bold"))

            fitness_text = f"F={gen_data['fitness']:.4f}"
            dwg.add(dwg.text(fitness_text, insert=(x + cell_width/2, label_y + 18),
                           text_anchor="middle", font_size="10"))

            delta_text = f"Δ={gen_data['delta']:+.4f}"
            dwg.add(dwg.text(delta_text, insert=(x + cell_width/2, label_y + 33),
                           text_anchor="middle", font_size="10", fill="red"))

        except Exception as e:
            print(f"  ERROR loading {svg_file}: {e}")

    # Add final metrics section
    final_y = padding + 30 + grid_rows * (cell_height + label_height + padding)
    final_gen_num = top_6[-1][0]
    final_fitness = top_6[-1][1]['fitness']

    dwg.add(dwg.text("Final Result", insert=(padding, final_y),
                    font_size="14", font_weight="bold"))
    dwg.add(dwg.text(f"Generation: {final_gen_num}", insert=(padding, final_y + 20),
                    font_size="11"))
    dwg.add(dwg.text(f"Best Fitness: {final_fitness:.4f}", insert=(padding, final_y + 38),
                    font_size="11"))
    dwg.add(dwg.text(f"Total Improvement: {generations[final_gen_num]['delta']:.4f} from initial",
                    insert=(padding, final_y + 56), font_size="11"))

    dwg.save()
    print(f"\nSVG saved to: {output_file}")

if __name__ == "__main__":
    run_dir = "nesting/experiments/runs/rand_0JVMGTZZ5G_20260617_150004"
    output_file = "evolution_progress_top6.svg"

    create_evolution_viz(run_dir, output_file)
