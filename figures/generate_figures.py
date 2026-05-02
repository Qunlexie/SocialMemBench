"""
SocialMemBench figure generation.
Produces heatmap and bar chart from all-tier eval results.
"""
import json, os, collections
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns

RESULTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'results')
FIGURES_DIR = os.path.dirname(__file__)

# Small-tier networks (15 evaluated)
NETS_SMALL = [
    'grp_0d1e2f3a', 'grp_1a2b3c4d', 'grp_2b3c4d5e', 'grp_3c4d5e6f',
    'grp_4d5e6f7a', 'grp_5e6f7a8b', 'grp_6f7a8b9c', 'grp_7a8b9c0d',
    'grp_8b9c0d1e', 'grp_9c0d1e2f',
    'grp_a9b0c1d2', 'grp_c1d2e3f4', 'grp_d4e5f6a7', 'grp_e6f7a8b9', 'grp_f7a8b9c0',
]
# Medium-tier networks (14)
NETS_MEDIUM = [
    'grp_a0b1c2d3', 'grp_a1b2c3d4', 'grp_a3b4c5d6', 'grp_a5b6c7d8',
    'grp_b0c1d2e3', 'grp_b2c3d4e5', 'grp_b6c7d8e9', 'grp_c2d3e4f5',
    'grp_c3d4e5f6', 'grp_d2e3f4a5', 'grp_dba9214c', 'grp_e8f9a0b1',
    'grp_f2e3d4c5', 'grp_f9a0b1c2',
]
# Large-tier networks (10): 3 original + 7 new (15-30 personas)
NETS_LARGE = ['grp_b1c2d3e4', 'grp_e5f6a7b8', 'grp_f6g7h8i9',
              'grp_a4b5c6d7', 'grp_b8c9dae0', 'grp_c1d2e3f7', 'grp_d3e4f5a6',
              'grp_e7f8a9b1', 'grp_f1a2b3c5', 'grp_a6b7c8d9']

# DM-containing networks (4) — small-tier with departures
NETS_DM = ['grp_c6d7e8f9', 'grp_d7e8f9a0', 'grp_e3f4a5b6', 'grp_f4a5b6c7']

# All 38 evaluated networks
NETS_ALL = NETS_SMALL + NETS_MEDIUM + NETS_LARGE

NETS_BY_CONDITION = {
    'llm_gemini':  NETS_SMALL,                # small-tier only
    'llm_mini':    NETS_ALL + NETS_DM,        # 27 evaluated + 4 DM
    'naive_rag':   NETS_ALL + NETS_DM,
    'subject_rag': NETS_ALL + NETS_DM,
    'smg':         NETS_ALL + NETS_DM,
    'graphiti':    NETS_ALL + NETS_DM,
    'langmem':     NETS_ALL + NETS_DM,
    'mem0_local':  NETS_ALL + NETS_DM,
    'cognee':      NETS_ALL + NETS_DM,
}

# Condition metadata: (results_dir_name, display_label, group)
# Gemini is intentionally excluded from main figures — it lives in a separate
# reasoning-model comparison table (see paper §5.4).
CONDITIONS = [
    ('llm_mini',    'LLM-Mini\n(full context)',     'upper'),
    ('naive_rag',   'Uncompressed\nRetrieval',      'upper'),
    ('subject_rag', 'Subject-Mem',                  'probe'),
    ('smg',         'SMG',                          'probe'),
    ('graphiti',    'Graphiti',                     'deployed'),
    ('langmem',     'LangMem',                      'deployed'),
    ('mem0_local',  'Mem0',                         'deployed'),
    ('cognee',      'Cognee',                       'deployed'),
]

QUERY_MAP = {
    'Q1': 'SR', 'Q2': 'GD', 'Q3': 'MA', 'Q4': 'AP',
    'Q5': 'TM', 'Q6': 'NI', 'Q7': 'RE', 'Q8': 'TS',
    'Q9': 'DM',
}
CATEGORIES = ['SR', 'GD', 'MA', 'AP', 'TM', 'NI', 'RE', 'TS', 'DM']
CAT_LABELS  = ['SR\nSingle-contact', 'GD\nGroup decision',
               'MA\nMulti-contact', 'AP\nAttribution',
               'TM\nTheory of mind', 'NI\nNorm vs. indiv.',
               'RE\nRelational edge', 'TS\nTemporal shift',
               'DM\nDeparted member']

GROUP_COLORS = {
    'upper':    '#3B82F6',   # blue
    'probe':    '#10B981',   # green
    'deployed': '#EF4444',   # red
}
GROUP_LABELS = {
    'upper':    'Upper bounds (not memory systems)',
    'probe':    'Research probes',
    'deployed': 'Deployed memory systems',
}


def load_data():
    """Load and aggregate per-category scores across small-tier networks."""
    data = {}   # {cond_key: {cat: mean_score}}
    means = {}  # {cond_key: overall_mean}

    for cond_key, label, group in CONDITIONS:
        cat_totals = collections.defaultdict(lambda: [0.0, 0])  # [sum, count]
        total_sum, total_count = 0.0, 0
        nets = NETS_BY_CONDITION.get(cond_key, NETS_SMALL)

        for net in nets:
            pf = os.path.join(RESULTS_DIR, cond_key, f'{net}.jsonl')
            if not os.path.exists(pf):
                continue
            for line in open(pf):
                d = json.loads(line)
                mapped = QUERY_MAP.get(d.get('query_type', ''))
                score = d.get('score', 0)
                if mapped:
                    cat_totals[mapped][0] += score
                    cat_totals[mapped][1] += 1
                    total_sum += score
                    total_count += 1

        if not total_count:
            continue

        data[cond_key] = {
            cat: (cat_totals[cat][0] / cat_totals[cat][1] if cat_totals[cat][1] else float('nan'))
            for cat in CATEGORIES
        }
        means[cond_key] = total_sum / total_count

    return data, means


def make_heatmap(data, means):
    """Heatmap: conditions (rows) × categories (columns) + mean column."""
    cond_keys = [c[0] for c in CONDITIONS if c[0] in data]
    labels    = [c[1] for c in CONDITIONS if c[0] in data]
    groups    = [c[2] for c in CONDITIONS if c[0] in data]

    cat_matrix  = np.array([[data[k].get(cat, float('nan')) for cat in CATEGORIES] for k in cond_keys])
    mean_col    = np.array([[means[k]] for k in cond_keys])
    full_matrix = np.hstack([cat_matrix, mean_col])

    n_rows = len(cond_keys)
    n_cols = len(CATEGORIES) + 1   # +1 for Mean column

    # Use two axes side-by-side: main heatmap | mean column
    fig, (ax, ax_mean) = plt.subplots(
        1, 2,
        figsize=(13, 5.5),
        gridspec_kw={'width_ratios': [len(CATEGORIES), 1], 'wspace': 0.05}
    )

    cmap = sns.diverging_palette(10, 133, as_cmap=True)

    # --- Main heatmap ---
    im = ax.imshow(cat_matrix, cmap=cmap, vmin=0, vmax=1, aspect='auto')

    for i in range(n_rows):
        for j in range(len(CATEGORIES)):
            val = cat_matrix[i, j]
            if not np.isnan(val):
                tc = 'white' if (val < 0.25 or val > 0.80) else 'black'
                ax.text(j, i, f'{val:.2f}', ha='center', va='center',
                        fontsize=8, color=tc, fontweight='bold')

    ax.set_xticks(range(len(CATEGORIES)))
    ax.set_xticklabels(CATEGORIES, fontsize=10, fontweight='bold')
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(labels, fontsize=9)
    ax.tick_params(axis='y', length=0)

    for i, (key, label, group) in enumerate([(c[0], c[1], c[2]) for c in CONDITIONS if c[0] in data]):
        ax.get_yticklabels()[i].set_color(GROUP_COLORS[group])

    # --- Mean column ---
    ax_mean.imshow(mean_col, cmap=cmap, vmin=0, vmax=1, aspect='auto')
    for i in range(n_rows):
        val = mean_col[i, 0]
        tc = 'white' if (val < 0.25 or val > 0.80) else 'black'
        ax_mean.text(0, i, f'{val:.3f}', ha='center', va='center',
                     fontsize=8, color=tc, fontweight='bold')

    ax_mean.set_xticks([0])
    ax_mean.set_xticklabels(['Mean'], fontsize=10, fontweight='bold')
    ax_mean.set_yticks([])
    ax_mean.tick_params(axis='x', length=0)

    # Separator lines between groups (both axes)
    boundaries = []
    prev = groups[0]
    for i, g in enumerate(groups[1:], 1):
        if g != prev:
            boundaries.append(i - 0.5)
        prev = g
    for b in boundaries:
        ax.axhline(y=b, color='black', linewidth=1.5, linestyle='--', alpha=0.6)
        ax_mean.axhline(y=b, color='black', linewidth=1.5, linestyle='--', alpha=0.6)

    # Colorbar attached to main axis
    cbar = plt.colorbar(im, ax=ax_mean, label='Score (0–1)', fraction=0.25, pad=0.18)
    cbar.ax.tick_params(labelsize=8)
    cbar.set_label('Score (0–1)', fontsize=9)

    # Legend below main axis
    patches = [mpatches.Patch(color=v, label=GROUP_LABELS[k]) for k, v in GROUP_COLORS.items()]
    ax.legend(handles=patches, loc='upper center', bbox_to_anchor=(0.5, -0.13),
              ncol=3, fontsize=9, frameon=False)

    ax.set_title('SocialMemBench: Score by Condition and Query Category\n'
                 '(27 networks across all tiers, question-weighted)',
                 fontsize=11, pad=12)

    plt.savefig(os.path.join(FIGURES_DIR, 'heatmap.pdf'), bbox_inches='tight', dpi=150)
    plt.savefig(os.path.join(FIGURES_DIR, 'heatmap.png'), bbox_inches='tight', dpi=150)
    print(f'Saved: heatmap.pdf / heatmap.png')
    plt.close()


def load_bootstrap_cis():
    """Load network-weighted means and 95% CIs from precomputed file."""
    ci_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'results', 'bootstrap_cis.json')
    if os.path.exists(ci_path):
        with open(ci_path) as f:
            return json.load(f)
    return {}


def make_bar_chart(means):
    """Horizontal bar chart showing the 4-tier performance story."""
    cis = load_bootstrap_cis()

    fig, ax = plt.subplots(figsize=(9, 5.5))

    # Reversed order: ceiling at top, deployed at bottom
    cond_keys = [c[0] for c in reversed(CONDITIONS) if c[0] in means]
    labels = [c[1].replace('\n', ' ') for c in reversed(CONDITIONS) if c[0] in means]
    groups = [c[2] for c in reversed(CONDITIONS) if c[0] in means]

    # Use network-weighted means from CIs file when available; fall back to q-weighted
    scores = [cis[k]['mean'] if k in cis else means[k] for k in cond_keys]
    xerr   = [cis[k]['half'] if k in cis else 0.0 for k in cond_keys]

    colors = [GROUP_COLORS[g] for g in groups]
    # Slightly lighter fill so dark CI lines read clearly on top
    bar_colors = [c + 'cc' if len(c) == 7 else c for c in colors]  # add alpha via hex
    y = list(range(len(cond_keys)))

    # Draw bars without error; overlay CI lines separately for cleaner look
    bars = ax.barh(y, scores, color=colors, height=0.55, alpha=0.75, edgecolor='none')

    # CI lines drawn as thin horizontal segments with tick marks
    for i, (sc, err) in enumerate(zip(scores, xerr)):
        if err > 0:
            ax.plot([sc - err, sc + err], [i, i], color='#222222', linewidth=1.5, solid_capstyle='round', zorder=4)
            ax.plot([sc - err, sc - err], [i - 0.12, i + 0.12], color='#222222', linewidth=1.5, zorder=4)
            ax.plot([sc + err, sc + err], [i - 0.12, i + 0.12], color='#222222', linewidth=1.5, zorder=4)

    # Score labels: place after CI upper bound (or bar end if no CI)
    for i, (score, err) in enumerate(zip(scores, xerr)):
        x_label = score + err + 0.013 if err > 0 else score + 0.013
        ax.text(x_label, i, f'{score:.3f}', va='center', ha='left', fontsize=8.5, fontweight='bold',
                color='#222222')

    # Blind-critic reference line
    ax.axvline(x=0.997, color='#888888', linestyle=':', linewidth=1.2, alpha=0.8)
    ax.text(0.997 + 0.004, len(cond_keys) - 0.6, 'Blind-critic\n0.997', va='top',
            ha='left', fontsize=7.5, color='#888888')

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9.5)
    ax.set_xlabel('Network-weighted Mean Score (0\u20131),  bars show 95% bootstrap CI', fontsize=10)
    ax.set_xlim(0, 1.12)
    ax.set_title('SocialMemBench: Overall Performance by Condition\n(27 networks, 10k bootstrap resamples over networks)',
                 fontsize=11, pad=10)
    ax.grid(axis='x', alpha=0.25, linestyle='--')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Separator lines
    boundaries = []
    prev_group = groups[0]
    for i, g in enumerate(groups[1:], 1):
        if g != prev_group:
            boundaries.append(i - 0.5)
        prev_group = g
    for b in boundaries:
        ax.axhline(y=b, color='black', linewidth=0.8, linestyle='--', alpha=0.35)

    # Legend
    patches = [mpatches.Patch(color=v, label=GROUP_LABELS[k]) for k, v in GROUP_COLORS.items()]
    ax.legend(handles=patches, loc='lower right', fontsize=9, frameon=False)

    plt.tight_layout()
    out = os.path.join(FIGURES_DIR, 'bar_chart.pdf')
    plt.savefig(out, bbox_inches='tight', dpi=150)
    plt.savefig(out.replace('.pdf', '.png'), bbox_inches='tight', dpi=150)
    print(f'Saved: {out}')
    plt.close()


def make_tier_curve():
    """Line plot: mean score by tier for each condition. Highlights the U-shape."""
    NETS_SMALL_LOCAL = NETS_SMALL + NETS_DM  # 14 small (10 + 4 DM)
    NETS_MEDIUM_LOCAL = NETS_MEDIUM
    NETS_LARGE_LOCAL = NETS_LARGE

    def per_tier_mean(cond, networks):
        s = []
        for nid in networks:
            pf = os.path.join(RESULTS_DIR, cond, f'{nid}.jsonl')
            if not os.path.exists(pf): continue
            for line in open(pf):
                if line.strip(): s.append(json.loads(line).get('score', 0))
        return np.mean(s) if s else float('nan')

    fig, ax = plt.subplots(figsize=(9, 5.2))
    tiers = ['Small\n(3-6)', 'Medium\n(7-14)', 'Large\n(15-30)']
    x = [0, 1, 2]

    style_by_group = {
        'upper': {'linestyle': '-', 'linewidth': 2.4, 'marker': 'o', 'markersize': 8},
        'probe': {'linestyle': '--', 'linewidth': 2.0, 'marker': 's', 'markersize': 7},
        'deployed': {'linestyle': ':', 'linewidth': 1.8, 'marker': '^', 'markersize': 6},
    }

    label_map = {
        'llm_gemini': 'LLM-Gemini (small only)',
        'llm_mini': 'LLM-Mini (full ctx)',
        'naive_rag': 'Uncompressed retrieval',
        'subject_rag': 'Subject-Mem',
        'smg': 'SMG',
        'graphiti': 'Graphiti',
        'langmem': 'LangMem',
        'mem0_local': 'Mem0',
        'cognee': 'Cognee',
    }

    for cond_key, label, group in CONDITIONS:
        if cond_key == 'llm_gemini':
            # Small only, no medium/large
            m_s = per_tier_mean(cond_key, NETS_SMALL[:10])  # gemini only ran on small-tier (10 nets, no DM)
            ax.plot([0], [m_s], color=GROUP_COLORS[group], **style_by_group[group],
                    label=label_map[cond_key])
            continue
        m_s = per_tier_mean(cond_key, NETS_SMALL_LOCAL)
        m_m = per_tier_mean(cond_key, NETS_MEDIUM_LOCAL)
        m_l = per_tier_mean(cond_key, NETS_LARGE_LOCAL)
        ax.plot(x, [m_s, m_m, m_l], color=GROUP_COLORS[group],
                **style_by_group[group], label=label_map[cond_key],
                alpha=0.9)

    ax.set_xticks(x)
    ax.set_xticklabels(tiers, fontsize=10)
    ax.set_ylabel('Question-weighted mean score', fontsize=11)
    ax.set_xlabel('Network-size tier', fontsize=11)
    ax.set_title('SocialMemBench: Performance Across Network-Size Tiers\n(U-shape across all conditions: medium-tier is the difficult middle)',
                 fontsize=11, pad=10)
    ax.set_ylim(0, 0.78)
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Legend grouped by class
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, labels, loc='upper right', fontsize=8.5, frameon=True, framealpha=0.9, ncol=1)

    plt.tight_layout()
    out = os.path.join(FIGURES_DIR, 'tier_curve.pdf')
    plt.savefig(out, bbox_inches='tight', dpi=150)
    plt.savefig(out.replace('.pdf', '.png'), bbox_inches='tight', dpi=150)
    print(f'Saved: {out}')
    plt.close()


if __name__ == '__main__':
    data, means = load_data()
    print('Loaded data for:', list(data.keys()))
    print('Overall means:', {k: f'{v:.3f}' for k, v in means.items()})
    make_heatmap(data, means)
    make_bar_chart(means)
    make_tier_curve()
    print('Done.')
