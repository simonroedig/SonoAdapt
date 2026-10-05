import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os
import warnings
from matplotlib.lines import Line2D

warnings.filterwarnings('ignore')

# ==========================================
# CONFIGURATION
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)  # parent = SonoAdapt_Survey_Analysis

DATA_FILE = os.path.join(ROOT_DIR, "data.xlsx")
OUTLIERS_FILE = os.path.join(ROOT_DIR, "listOfManuallyIdentifiedOutliers.txt")

OUTPUT_MAIN_EFFECTS = os.path.join(SCRIPT_DIR, "main_effects")
OUTPUT_BREAKDOWN = os.path.join(SCRIPT_DIR, "main_effect_breakdown")

START_DATE = "2026-06-30"

# Configure fonts
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Segoe UI Emoji', 'Tahoma', 'DejaVu Sans']

# ==========================================
# MAPPINGS
# ==========================================
NOTIFICATION_TYPES = {
    '1': 'Earcon',
    '2': 'Short Speech',
    '3': 'Rich Speech'
}

SCENARIO_MAPPING = {
    'A': {'Social': 'Alone',       'Task': 'High mental',   'Soundscape': 'Quiet'},
    'B': {'Social': 'Interactive', 'Task': 'High mental',   'Soundscape': 'Speech'},
    'C': {'Social': 'Alone',       'Task': 'Low',           'Soundscape': 'Music'},
    'D': {'Social': 'Interactive', 'Task': 'High physical', 'Soundscape': 'Music'},
    'E': {'Social': 'Passive',     'Task': 'High physical', 'Soundscape': 'Quiet'},
    'F': {'Social': 'Passive',     'Task': 'Low',           'Soundscape': 'Speech'},
    'G': {'Social': 'Alone',       'Task': 'High physical', 'Soundscape': 'Speech'},
    'H': {'Social': 'Passive',     'Task': 'High mental',   'Soundscape': 'Music'},
    'I': {'Social': 'Interactive', 'Task': 'Low',           'Soundscape': 'Quiet'},
}

IV_PROPS = {
    'Asocial': {
        'order': ['Alone', 'Interactive', 'Passive'],
        'palette': {'Alone': '#6baed6', 'Interactive': '#3182bd', 'Passive': '#08519c'},
        'label': r"$A_{SOCIAL}$ (Social Setting)",
        'title_name': 'Social Setting'
    },
    'e_Task': {
        'order': ['High mental', 'Low', 'High physical'],
        'palette': {'High mental': '#fd8d3c', 'Low': '#e6550d', 'High physical': '#a63603'},
        'label': r"$D_{TASK}$ (Task Load)",  # CHANGED: E_TASK -> D_TASK
        'title_name': 'Task Load'
    },
    'CM': {
        'order': ['Music', 'Quiet', 'Speech'],
        'palette': {'Music': '#74c476', 'Quiet': '#31a354', 'Speech': '#006d2c'},
        'label': r"$C_M$ (Soundscape)",
        'title_name': 'Soundscape'
    }
}

DV_Y_LABELS = {
    'Social_Acceptability': [
        "Completely unacceptable (1)", "Unacceptable (2)", "Somewhat unacceptable (3)",
        "Neither acceptable nor unacceptable (4)", "Somewhat acceptable (5)",
        "Acceptable (6)", "Completely acceptable (7)"
    ],
    'Disruption': [
        "Not disruptive at all (1)", "Slightly disruptive (2)", "Somewhat disruptive (3)",
        "Moderately disruptive (4)", "Disruptive (5)", "Very disruptive (6)",
        "Extremely disruptive (7)"
    ],
    'Detectability': [
        "Very difficult to detect (1)", "Difficult to detect (2)", "Somewhat difficult to detect (3)",
        "Neither easy nor difficult to detect (4)", "Somewhat easy to detect (5)",
        "Easy to detect (6)", "Very easy to detect (7)"
    ]
}

LIKERT_MAP = {
    "Very difficult to detect": 1, "Difficult to detect": 2, "Somewhat difficult to detect": 3,
    "Neither easy nor difficult to detect": 4, "Somewhat easy to detect": 5, "Easy to detect": 6, "Very easy to detect": 7,
    "Not disruptive at all": 1, "Slightly disruptive": 2, "Somewhat disruptive": 3,
    "Moderately disruptive": 4, "Disruptive": 5, "Very disruptive": 6, "Extremely disruptive": 7,
    "Completely unacceptable": 1, "Unacceptable": 2, "Somewhat unacceptable": 3,
    "Neither acceptable nor unacceptable": 4, "Somewhat acceptable": 5, "Acceptable": 6,
    "Completely acceptable": 7, "Completely Acceptable": 7, "Completel Acceptable": 7,
}

# The 3 primary DV<->IV relationships
COMPARISON_RELATIONSHIPS = [
    {'dv': 'Disruption', 'iv': 'e_Task'},
    {'dv': 'Social_Acceptability', 'iv': 'Asocial'},
    {'dv': 'Detectability', 'iv': 'CM'}
]

# Combined plot colors (darker shades)
COMBINED_COLORS = {
    'Disruption': '#662506',
    'Social_Acceptability': '#08306b',
    'Detectability': '#00441b'
}

# Notification type visual properties
TYPES_ORDER = ['Earcon', 'Short Speech', 'Rich Speech']
TYPE_MARKERS = {'Earcon': 'o', 'Short Speech': 's', 'Rich Speech': '^'}
TYPE_COLORS = {'Earcon': '#ffb000', 'Short Speech': '#c466ff', 'Rich Speech': '#6a0dad'}

# LMM pairwise results - for Combined plots (Notification Type main effect)
NT_LMM_RESULTS = {
    'Disruption': {(0, 1): '***', (0, 2): '***', (1, 2): '***'},
    'Social_Acceptability': {(0, 1): '***', (0, 2): '***', (1, 2): 'ns'},
    'Detectability': {(0, 1): 'ns', (0, 2): '**', (1, 2): 'ns'}
}

# LMM pairwise results - for PrimaryAdvanced plots (IV condition main effect)
IV_LMM_RESULTS = {
    'Disruption': {
        'e_Task': {('High mental', 'Low'): '***', ('High mental', 'High physical'): '***', ('Low', 'High physical'): 'ns'},
    },
    'Social_Acceptability': {
        'Asocial': {('Alone', 'Passive'): 'ns', ('Alone', 'Interactive'): '***', ('Interactive', 'Passive'): '***'},
    },
    'Detectability': {
        'CM': {('Music', 'Quiet'): '***', ('Music', 'Speech'): '***', ('Quiet', 'Speech'): '***'},
    }
}


# ==========================================
# DATA LOADING
# ==========================================

def load_and_filter_data():
    print(f"Loading data from {DATA_FILE}...")
    df = pd.read_excel(DATA_FILE)
    raw_count = len(df)

    df['RecordedDate'] = pd.to_datetime(df['RecordedDate'], errors='coerce', format='mixed')
    df = df[df['RecordedDate'] >= pd.to_datetime(START_DATE)]

    if os.path.exists(OUTLIERS_FILE):
        with open(OUTLIERS_FILE, 'r') as f:
            outliers = [line.strip() for line in f if line.strip()]
        removed = df['ResponseId'].isin(outliers).sum()
        df = df[~df['ResponseId'].isin(outliers)]
        print(f"  Excluded {removed} outliers.")

    print(f"  Final dataset: {len(df)} participants (from {raw_count} raw)")
    return df


def find_column(columns, sc_key, keyword, t_id):
    keyword_lower = keyword.lower()
    for col in columns:
        col_str = str(col)
        if col_str.startswith(f"{sc_key}.") and keyword_lower in col_str.lower() and col_str.endswith(f"_{t_id}"):
            return col_str
    return None


def transform_to_long_format(df):
    print("Transforming to long format...")
    long_data = []
    df.columns = [str(c).replace('\xa0', ' ').strip() for c in df.columns]

    for _, row in df.iterrows():
        response_id = row.get('ResponseId', 'Unknown')
        for sc_key, sc_attrs in SCENARIO_MAPPING.items():
            for t_id, t_name in NOTIFICATION_TYPES.items():

                col_detect = find_column(df.columns, sc_key, 'detect', t_id)
                col_disrupt = find_column(df.columns, sc_key, 'disrupt', t_id)
                col_social = find_column(df.columns, sc_key, 'social', t_id)

                val_detect = row.get(col_detect, pd.NA) if col_detect else pd.NA
                val_disrupt = row.get(col_disrupt, pd.NA) if col_disrupt else pd.NA
                val_social = row.get(col_social, pd.NA) if col_social else pd.NA

                if isinstance(val_detect, str): val_detect = LIKERT_MAP.get(val_detect.strip(), val_detect)
                if isinstance(val_disrupt, str): val_disrupt = LIKERT_MAP.get(val_disrupt.strip(), val_disrupt)
                if isinstance(val_social, str): val_social = LIKERT_MAP.get(val_social.strip(), val_social)

                if pd.isna(val_detect) and pd.isna(val_disrupt) and pd.isna(val_social):
                    continue

                long_data.append({
                    'ResponseId': response_id,
                    'Notification_Type': t_name,
                    'Scenario': sc_key,
                    'Asocial': sc_attrs['Social'],
                    'e_Task': sc_attrs['Task'],
                    'CM': sc_attrs['Soundscape'],
                    'Detectability': pd.to_numeric(val_detect, errors='coerce'),
                    'Disruption': pd.to_numeric(val_disrupt, errors='coerce'),
                    'Social_Acceptability': pd.to_numeric(val_social, errors='coerce'),
                })

    return pd.DataFrame(long_data)


# ==========================================
# SIGNIFICANCE ANNOTATION HELPER
# ==========================================

def add_stat_annotation(ax, x1, x2, y, h, text):
    """Draw a bracket between x1 and x2 at height y with label text."""
    ax.plot([x1, x1, x2, x2], [y, y+h, y+h, y], lw=1.5, c='k')
    ax.text((x1+x2)*.5, y+h, text, ha='center', va='bottom', color='k', weight='bold')


# ==========================================
# PLOT 1: BREAKDOWN PLOTS (per-condition)
# -> 9 plots into main_effect_breakdown/
# ==========================================

def generate_breakdown_plots(long_df):
    print(f"\n--- Generating 9 breakdown plots -> {OUTPUT_BREAKDOWN}/ ---")
    sns.set_theme(style="whitegrid")
    ticks_1_to_7 = [1, 2, 3, 4, 5, 6, 7]
    notification_order = TYPES_ORDER

    count = 0
    for rel in COMPARISON_RELATIONSHIPS:
        dv = rel['dv']
        iv = rel['iv']
        iv_config = IV_PROPS[iv]

        for condition in iv_config['order']:
            plot_df = long_df[long_df[iv] == condition].dropna(subset=[dv])
            if plot_df.empty:
                continue

            condition_color = iv_config['palette'][condition]

            plt.figure(figsize=(9, 6))

            ax = sns.boxplot(
                data=plot_df, x='Notification_Type', y=dv,
                order=notification_order, color=condition_color,
                showmeans=False
            )

            # Means + connecting line
            means = plot_df.groupby('Notification_Type')[dv].mean().reindex(notification_order)
            stds = plot_df.groupby('Notification_Type')[dv].std().reindex(notification_order)

            x_coords = range(len(notification_order))
            ax.plot(x_coords, means.values, color='black', linestyle='--', linewidth=1.5, zorder=4)

            for tick, t_name in enumerate(notification_order):
                if pd.notna(means[t_name]):
                    mean_val = means[t_name]
                    std_val = stds[t_name]

                    # WHITE edge on markers
                    ax.scatter(tick, mean_val, marker=TYPE_MARKERS[t_name], color=TYPE_COLORS[t_name],
                               s=90, edgecolors='white', zorder=5, alpha=1.0)

                    ax.text(tick, 7.2, f"M={mean_val:.2f}\nSD={std_val:.2f}",
                            horizontalalignment='center', size='small', color='black', weight='bold')

            plt.title(f"{dv.replace('_', ' ')} by Notification Type\n({iv_config['title_name']}: {condition})", fontsize=14, fontname='Segoe UI Emoji')
            plt.xlabel("Notification Type", fontsize=12)
            plt.ylabel(dv.replace('_', ' '), fontsize=12)

            plt.yticks(ticks=ticks_1_to_7, labels=[str(i) for i in ticks_1_to_7], fontsize=10)
            plt.ylim(0.5, 7.7)

            plt.tight_layout()
            filename = os.path.join(OUTPUT_BREAKDOWN, f"{dv.replace('_', '')}_{condition.replace(' ', '')}.png")
            plt.savefig(filename, dpi=300)
            plt.close()
            count += 1
            print(f"  > {os.path.basename(filename)}")

    print(f"  -> {count} breakdown plots saved.")


# ==========================================
# PLOT 2: COMBINED PLOTS (across conditions)
# -> 3 plots into main_effects/
# ==========================================

def generate_combined_plots(long_df):
    print(f"\n--- Generating 3 Combined plots -> {OUTPUT_MAIN_EFFECTS}/ ---")
    sns.set_theme(style="whitegrid")
    ticks_1_to_7 = [1, 2, 3, 4, 5, 6, 7]
    notification_order = TYPES_ORDER

    for rel in COMPARISON_RELATIONSHIPS:
        dv = rel['dv']
        iv = rel['iv']
        iv_config = IV_PROPS[iv]

        plot_df = long_df.dropna(subset=[dv])
        if plot_df.empty:
            continue

        plt.figure(figsize=(9, 6))
        combined_color = COMBINED_COLORS[dv]

        ax = sns.boxplot(
            data=plot_df, x='Notification_Type', y=dv,
            order=notification_order, color=combined_color,
            showmeans=False
        )

        means = plot_df.groupby('Notification_Type')[dv].mean().reindex(notification_order)
        stds = plot_df.groupby('Notification_Type')[dv].std().reindex(notification_order)

        x_coords = range(len(notification_order))
        ax.plot(x_coords, means.values, color='black', linestyle='--', linewidth=1.5, zorder=4)

        for tick, t_name in enumerate(notification_order):
            if pd.notna(means[t_name]):
                mean_val = means[t_name]
                std_val = stds[t_name]

                # WHITE edge on markers
                ax.scatter(tick, mean_val, marker=TYPE_MARKERS[t_name], color=TYPE_COLORS[t_name],
                           s=90, edgecolors='white', zorder=5, alpha=1.0)

                ax.text(tick, 7.2, f"M={mean_val:.2f}\nSD={std_val:.2f}",
                        horizontalalignment='center', size='small', color='black', weight='bold')

        # Significance brackets - SKIP 'ns'
        y_max = 8.0
        if dv in NT_LMM_RESULTS:
            sig_height = 8.0
            step = 0.5
            for (i, j), sig_text in NT_LMM_RESULTS[dv].items():
                if sig_text == 'ns':
                    continue  # Do NOT render ns brackets
                add_stat_annotation(ax, i, j, sig_height, 0.1, sig_text)
                sig_height += step
                y_max = max(y_max, sig_height + 0.4)

        plt.title(f"{dv.replace('_', ' ')} by Notification Type\n(Combined across {iv_config['title_name']}s)", fontsize=14, fontname='Segoe UI Emoji')
        plt.xlabel("Notification Type", fontsize=12)
        plt.ylabel(dv.replace('_', ' '), fontsize=12)

        plt.yticks(ticks=ticks_1_to_7, labels=[str(i) for i in ticks_1_to_7], fontsize=10)
        plt.ylim(0.5, y_max)

        plt.tight_layout()
        filename = os.path.join(OUTPUT_MAIN_EFFECTS, f"{dv.replace('_', '')}_Combined.png")
        plt.savefig(filename, dpi=300)
        plt.close()
        print(f"  > {os.path.basename(filename)}")


# ==========================================
# PLOT 3: PRIMARY ADVANCED INLINE PLOTS
# -> 3 plots + 1 legend into main_effects/
# ==========================================

def generate_primary_advanced_plots(long_df):
    print(f"\n--- Generating 3 PrimaryAdvanced inline plots -> {OUTPUT_MAIN_EFFECTS}/ ---")
    sns.set_theme(style="whitegrid")
    ticks_1_to_7 = [1, 2, 3, 4, 5, 6, 7]

    for rel in COMPARISON_RELATIONSHIPS:
        dv = rel['dv']
        iv = rel['iv']
        iv_config = IV_PROPS[iv]

        # Use ALL data (Overall across notification types)
        plot_df = long_df.dropna(subset=[dv])
        if plot_df.empty:
            continue

        means_overall = plot_df.groupby(iv)[dv].mean()
        stds_overall = plot_df.groupby(iv)[dv].std()

        y_max = 8.8  # room for significance bars

        plt.figure(figsize=(9, 6))

        ax = sns.boxplot(
            data=plot_df, x=iv, y=dv,
            order=iv_config['order'], palette=iv_config['palette'],
            showmeans=False
        )

        # Plot individual notification type means as markers (inline = all at same x)
        for tick, label in enumerate(iv_config['order']):
            label_df = plot_df[plot_df[iv] == label]
            for n_type in TYPES_ORDER:
                type_mean = label_df[label_df['Notification_Type'] == n_type][dv].mean()
                if pd.notna(type_mean):
                    # WHITE edge on markers
                    ax.scatter(tick, type_mean, marker=TYPE_MARKERS[n_type], color=TYPE_COLORS[n_type],
                               s=80, edgecolors='white', zorder=5, alpha=0.9)

        # Significance brackets - SKIP 'ns'
        labels = iv_config['order']
        sig_height = 7.7
        step = 0.5

        if dv in IV_LMM_RESULTS and iv in IV_LMM_RESULTS[dv]:
            sig_dict = IV_LMM_RESULTS[dv][iv]
            for (g1, g2), sig_text in sig_dict.items():
                if sig_text == 'ns':
                    continue  # Do NOT render ns brackets
                if g1 in labels and g2 in labels:
                    i = labels.index(g1)
                    j = labels.index(g2)
                    if i > j:
                        i, j = j, i
                    add_stat_annotation(ax, i, j, sig_height, 0.1, sig_text)
                    sig_height += step
                    y_max = max(y_max, sig_height + 0.4)

        # M/SD annotations
        for tick, label in enumerate(iv_config['order']):
            if label in means_overall.index:
                mean_val = means_overall[label]
                std_val = stds_overall[label]
                ax.text(tick, 7.3, f"M={mean_val:.2f}\nSD={std_val:.2f}",
                        horizontalalignment='center', verticalalignment='center', size='small', color='black', weight='bold')

        plt.title(f"{dv.replace('_', ' ')} by {iv_config['title_name']}", fontsize=14, fontname='Segoe UI Emoji')
        plt.xlabel(iv_config['label'], fontsize=12)
        plt.ylabel(dv.replace('_', ' '), fontsize=12)

        plt.yticks(ticks=ticks_1_to_7, labels=DV_Y_LABELS.get(dv, ticks_1_to_7), fontsize=10)
        plt.ylim(0.5, y_max)

        plt.tight_layout()
        filename = os.path.join(OUTPUT_MAIN_EFFECTS, f"PrimaryAdvanced_Overall_{iv}_vs_{dv.replace(' ', '')}_inline.png")
        plt.savefig(filename, dpi=300)
        plt.close()
        print(f"  > {os.path.basename(filename)}")

    # Standalone legend - WHITE edge on markers
    print("  Generating standalone legend...")
    fig_leg = plt.figure(figsize=(3, 2))
    legend_elements = [
        Line2D([0], [0], marker=TYPE_MARKERS[t], color='w', label=t,
               markerfacecolor=TYPE_COLORS[t], markersize=9, markeredgecolor='white')
        for t in TYPES_ORDER
    ]
    fig_leg.legend(handles=legend_elements, loc='center', title="Notification Types")
    legend_path = os.path.join(OUTPUT_MAIN_EFFECTS, "PrimaryAdvanced_Legend_Standalone.png")
    fig_leg.savefig(legend_path, dpi=300, bbox_inches='tight')
    plt.close(fig_leg)
    print(f"  > PrimaryAdvanced_Legend_Standalone.png")


# ==========================================
# MAIN
# ==========================================

def main():
    os.makedirs(OUTPUT_MAIN_EFFECTS, exist_ok=True)
    os.makedirs(OUTPUT_BREAKDOWN, exist_ok=True)

    df = load_and_filter_data()
    long_df = transform_to_long_format(df)

    generate_breakdown_plots(long_df)
    generate_combined_plots(long_df)
    generate_primary_advanced_plots(long_df)

    print("\n" + "=" * 50)
    print("ALL 15 PLOTS + LEGEND GENERATED SUCCESSFULLY")
    print("=" * 50)


if __name__ == "__main__":
    main()
