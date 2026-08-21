#!/usr/bin/env python3
"""
Recreate Figure 4: Mutation effectiveness visualization with the paper's data.
Saved as two separate figures (top and bottom rows).
"""
import matplotlib.pyplot as plt
import numpy as np

# Data from the figure
mutations = ['split', 'design_params', 'insertion', 'inversion', 'scramble', 'rotate', 'swap']

# Top left: Improvement Rate (%)
improvement_rate = [16.8, 12.3, 7.0, 6.2, 6.1, 4.8, 4.6]

# Top right: Mean Fitness Gain
mean_fitness_gain_negative = [-0.104, -0.100, -0.089, -0.104, -0.100, -0.091, -0.133]

# Bottom left: Mean Fitness Gain with sample counts
mean_fitness_gain_positive = [0.020, 0.018, 0.017, 0.017, 0.017, 0.014, 0.009]
sample_counts = [2222, 3003, 3385, 2971, 2302, 6403, 8635]
mutations_bl = ['swap', 'inversion', 'insertion', 'scramble', 'rotate', 'design_params', 'split']

# Bottom right: (Avg. Gain × #Successes) / #Runs
avg_gain_successes = [2.648, 3.231, 3.482, 3.030, 2.333, 5.420, 4.726]
mutations_br = ['swap', 'inversion', 'insertion', 'scramble', 'rotate', 'design_params', 'split']

# Color scheme - pastel palette with increased saturation
colors_map = {
    'split': '#f08080',           # Cotton Rose - warm red/pink
    'design_params': '#d99fef',   # Pink Orchid - saturated purple
    'insertion': '#6ee7de',       # Electric Aqua - vibrant cyan
    'inversion': '#ff8fa3',       # Cotton Rose - saturated pink
    'scramble': '#ffc57a',        # Powder Petal - warm cream/orange
    'rotate': '#60b8f5',          # Baby Blue Ice - saturated blue
    'swap': '#7fe8c5'             # Celadon - saturated green
}

colors_tl = [colors_map[m] for m in mutations]
colors_bl = [colors_map[m] for m in mutations_bl]
colors_br = [colors_map[m] for m in mutations_br]

# BAR HEIGHT
bar_height = 0.7

# Function to format labels (remove underscores)
def format_label(label):
    return label.replace('_', ' ')

# ===== TOP ROW =====
fig_top, axes_top = plt.subplots(1, 2, figsize=(14, 3))

# Top left: Improvement Rate
ax = axes_top[0]
y_pos = np.arange(len(mutations))
bars = ax.barh(y_pos, improvement_rate, height=bar_height, color=colors_tl)
ax.set_yticks(y_pos)
ax.set_yticklabels([format_label(m) for m in mutations], fontsize=11)
ax.set_xlabel('Improvement Rate (%)', fontsize=12)
ax.set_xlim(0, 20)
ax.grid(axis='x', alpha=0.3)
# Add percentage labels
for i, (bar, val) in enumerate(zip(bars, improvement_rate)):
    ax.text(val + 0.1, i, f'{val}%', va='center', fontsize=11)

# Top right: Mean Fitness Gain (negative values)
ax = axes_top[1]
y_pos = np.arange(len(mutations))
mutations_tr = list(reversed(mutations))
colors_tr = list(reversed(colors_tl))
mean_fitness_tr = list(reversed(mean_fitness_gain_negative))
bars = ax.barh(y_pos, mean_fitness_tr, height=bar_height, color=colors_tr)
ax.set_yticks(y_pos)
ax.set_yticklabels([format_label(m) for m in mutations_tr], fontsize=10)
ax.set_xlabel('Mean Fitness Gain', fontsize=12)
ax.set_xlim(-0.16, 0)
ax.axvline(x=0, color='red', linestyle='--', linewidth=2, label='No Change')
ax.grid(axis='x', alpha=0.3)
ax.legend(loc='lower right', fontsize=10)
# Add value labels - consistent with other plots
for i, (bar, val) in enumerate(zip(bars, mean_fitness_tr)):
    ax.text(val - 0.003, i, f'{val:.3f}', va='center', ha='right', fontsize=10)

plt.tight_layout()
plt.savefig('Figure4_top_row.png', dpi=300, bbox_inches='tight')
print("Top row saved to: Figure4_top_row.png")
plt.close()

# ===== BOTTOM ROW =====
fig_bottom, axes_bottom = plt.subplots(1, 2, figsize=(14, 3))

# Bottom left: Mean Fitness Gain with sample counts
ax = axes_bottom[0]
y_pos = np.arange(len(mutations_bl))
bars = ax.barh(y_pos, mean_fitness_gain_positive, height=bar_height, color=colors_bl)
ax.set_yticks(y_pos)
ax.set_yticklabels([format_label(m) for m in mutations_bl], fontsize=10)
ax.set_xlabel('Mean Fitness Gain', fontsize=12)
ax.set_xlim(0, 0.025)
ax.grid(axis='x', alpha=0.3)
# Add labels with sample counts - positioned close to bar
for i, (bar, val, n) in enumerate(zip(bars, mean_fitness_gain_positive, sample_counts)):
    ax.text(val + 0.0003, i, f'{val:.3f} (n={n:,})', va='center', fontsize=9, ha='left')

# Bottom right: (Avg. Gain × #Successes) / #Runs
ax = axes_bottom[1]
y_pos = np.arange(len(mutations_br))
bars = ax.barh(y_pos, avg_gain_successes, height=bar_height, color=colors_br)
ax.set_yticks(y_pos)
ax.set_yticklabels([format_label(m) for m in mutations_br], fontsize=10)
ax.set_xlabel('(Avg. Gain × #Successes) / #Runs', fontsize=12)
ax.set_xlim(0, 6)
ax.grid(axis='x', alpha=0.3)
# Add value labels
for i, (bar, val) in enumerate(zip(bars, avg_gain_successes)):
    ax.text(val + 0.05, i, f'{val:.3f}', va='center', fontsize=11)

plt.tight_layout()
plt.savefig('Figure4_bottom_row.png', dpi=300, bbox_inches='tight')
print("Bottom row saved to: Figure4_bottom_row.png")
