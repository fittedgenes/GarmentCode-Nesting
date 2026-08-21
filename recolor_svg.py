#!/usr/bin/env python3
"""
Recolor correlation heatmap SVG from coolwarm to custom pastel colors.
"""
import re
from lxml import etree
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.colors import Normalize

svg_path = "metrics_correlation_d65f4688.svg"

# Define colormaps
old_cmap = cm.get_cmap('coolwarm')  # Original
new_colors = ['#60b8f5', '#ffffff', '#ff8fa3']  # Baby Blue, White, Cotton Rose

# Create new colormap
from matplotlib.colors import LinearSegmentedColormap
new_cmap = LinearSegmentedColormap.from_list('custom', new_colors, N=256)

# Parse SVG
tree = etree.parse(svg_path)
root = tree.getroot()
ns = {'svg': 'http://www.w3.org/2000/svg'}

# Find all path elements (heatmap cells)
paths = root.findall('.//svg:path', ns)

norm = Normalize(vmin=-1, vmax=1)  # Color scale range

color_map = {}  # Cache for color conversions

for path in paths:
    style = path.get('style', '')

    # Extract fill color
    fill_match = re.search(r'fill: (#[0-9a-fA-F]{6})', style)
    if fill_match:
        old_color = fill_match.group(1)

        # Map old coolwarm color to new color
        if old_color not in color_map:
            # Convert hex to RGB
            rgb_old = tuple(int(old_color[i:i+2], 16)/255.0 for i in (1, 3, 5))

            # Find approximate value in old colormap (reverse lookup)
            # Coolwarm: blue (-1) to white (0) to red (+1)
            if rgb_old[0] > 0.9 and rgb_old[1] < 0.5:  # Red-ish
                val = 1.0
            elif rgb_old[0] < 0.5 and rgb_old[2] > 0.9:  # Blue-ish
                val = -1.0
            else:  # Middle
                val = 0.0

            # Get color from new colormap
            new_rgb = new_cmap(norm(val))[:3]
            new_hex = '#{:02x}{:02x}{:02x}'.format(int(new_rgb[0]*255), int(new_rgb[1]*255), int(new_rgb[2]*255))
            color_map[old_color] = new_hex

        # Replace color
        new_style = re.sub(r'fill: #[0-9a-fA-F]{6}', f'fill: {color_map[old_color]}', style)
        path.set('style', new_style)

# Save
tree.write(svg_path, encoding='utf-8', xml_declaration=True)
print(f"Recolored SVG saved to: {svg_path}")
