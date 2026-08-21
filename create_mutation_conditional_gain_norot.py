#!/usr/bin/env python3
"""
Create mutation conditional gain (no rotation) visualization styled like Figure4.
"""
import matplotlib.pyplot as plt
import numpy as np

# Data from the plot
mutations_left = ['swap', 'inversion', 'scramble', 'insertion', 'design_params', 'split']
mean_fitness_left = [0.019, 0.017, 0.016, 0.015, 0.011, 0.009]
sample_counts = [3818, 5062, 5284, 5507, 17468, 13391]

mutations_right = ['swap', 'inversion', 'scramble', 'insertion', 'design_params', 'split']
avg_gain_successes = [2.959, 3.543, 3.512, 3.541, 8.134, 4.946]

# Color scheme - saturated pastel colors from Figure4
colors_map = {
    'split': '#f08080',           # Cotton Rose
    'design_params': '#d99fef',   # Pink Orchid
    'insertion': '#6ee7de',       # Electric Aqua
    'inversion': '#ff8fa3',       # Cotton Rose
    'scramble': '#ffc57a',        # Powder Petal
    'rotate': '#60b8f5',          # Baby Blue Ice
    'swap': '#7fe8c5'             # Celadon
}

colors_left = [colors_map[m] for m in mutations_left]
colors_right = [colors_map[m] for m in mutations_right]

# Bar height and layout
bar_height = 0.7
fig_width = 15
fig_height = 3.5

# Function to format labels
def format_label(label):
    return label.replace('_', ' ')

# ===== CREATE FIGURE =====
fig, axes = plt.subplots(1, 2, figsize=(fig_width, fig_height))

# Left plot: Mean Fitness Gain with sample counts
ax = axes[0]
y_pos = np.arange(len(mutations_left))
bars = ax.barh(y_pos, mean_fitness_left, height=bar_height, color=colors_left)
ax.set_yticks(y_pos)
ax.set_yticklabels([format_label(m) for m in mutations_left], fontsize=11)
ax.set_xlabel('Mean Fitness Gain', fontsize=12)
ax.set_xlim(0, 0.03)
ax.grid(axis='x', alpha=0.3)

# Add labels with sample counts
for i, (bar, val, n) in enumerate(zip(bars, mean_fitness_left, sample_counts)):
    ax.text(val + 0.0003, i, f'{val:.3f} (n={n:,})', va='center', fontsize=9, ha='left')

# Right plot: (Avg. Gain × #Successes) / #Runs
ax = axes[1]
y_pos = np.arange(len(mutations_right))
bars = ax.barh(y_pos, avg_gain_successes, height=bar_height, color=colors_right)
ax.set_yticks(y_pos)
ax.set_yticklabels([format_label(m) for m in mutations_right], fontsize=11)
ax.set_xlabel('(Avg. Gain × #Successes) / #Runs', fontsize=12)
ax.set_xlim(0, 9)
ax.grid(axis='x', alpha=0.3)

# Add value labels
for i, (bar, val) in enumerate(zip(bars, avg_gain_successes)):
    ax.text(val + 0.15, i, f'{val:.3f}', va='center', fontsize=11)

plt.tight_layout()
plt.savefig('mutation_conditional_gain_norot_styled.png', dpi=300, bbox_inches='tight')
print("Styled plot saved to: mutation_conditional_gain_norot_styled.png")
