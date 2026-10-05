"""
Generate Per-Scenario Preference Bar Charts (Stage 2 — Immediate Choice)
=========================================================================
Creates 9 bar charts (one per scenario) showing the distribution of
notification type preferences at Stage 2 (the immediate, in-scenario choice
WITHOUT timing consideration), along with the top two stated reasons.

Outputs:
  - Scenario_1_Home_Alone_Computer.png ... Scenario_9_Tent.png

Originally: furtherPlots4.py
"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.patches import Patch
from collections import Counter
import os
import re
import warnings
warnings.filterwarnings('ignore')

# ==========================================
# CONFIGURATION
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FINAL_DIR = os.path.dirname(SCRIPT_DIR)
DATA_FILE = os.path.join(FINAL_DIR, "data.xlsx")
OUTLIERS_FILE = os.path.join(FINAL_DIR, "listOfManuallyIdentifiedOutliers.txt")
OUTPUT_DIR = SCRIPT_DIR
START_DATE = "2026-06-30"

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Segoe UI Emoji', 'Tahoma', 'DejaVu Sans']

# Colors for Notification Formats
COLORS = {
    'No Audio': '#A6A6A6',      # Grey
    'Earcon': '#FFC300',        # Yellow
    'Short Speech': '#AF7AC5',  # Light Purple
    'Rich Speech': '#694487'    # Dark Purple
}

# Colors for Top Reasons (Distinct from formats)
REASON_COLORS = {
    'Focus & Mental Effort': '#27AE60',        # Green
    'Desire for Information': '#2980B9',       # Blue
    'Acoustic Environment': '#D35400',         # Orange
    'Social Appropriateness': '#16A085',       # Teal
    'Physical Safety & Awareness': '#C0392B',  # Red
    'Other': '#7F8C8D'                         # Grey-Blue
}

# Mapped to your specific 1-9 numbering
SCENARIOS = {
    'A': (1, 'Home Alone Computer'),
    'C': (2, 'Home Music'),
    'G': (3, 'Cooking Dinner'),
    'H': (4, 'Study Coffee Shop'),
    'F': (5, 'Grocery Shopping'),
    'E': (6, 'Cycle City'),
    'B': (7, 'Team Meeting'),
    'I': (8, 'Quiet Friend Over'),
    'D': (9, 'Tent')
}

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def categorize_overall_preference(val):
    """Maps Qualtrics overall preference responses to our clean categories."""
    if pd.isna(val):
        return None
    val_str = str(val).lower()

    if 'none' in val_str or 'no audio' in val_str or 'mute' in val_str:
        return 'No Audio'
    elif '1' in val_str or 'earcon' in val_str or 'sound' in val_str:
        return 'Earcon'
    elif '2' in val_str:
        return 'Short Speech'
    elif '3' in val_str:
        return 'Rich Speech'
    return None


def clean_and_map_reason(raw_reason):
    """Strips text in parentheses and maps to a clean standard category name."""
    clean = re.sub(r'\(.*?\)', '', str(raw_reason)).strip().lower()

    if 'focus' in clean or 'mental' in clean: return 'Focus & Mental Effort'
    if 'information' in clean: return 'Desire for Information'
    if 'acoustic' in clean: return 'Acoustic Environment'
    if 'social' in clean: return 'Social Appropriateness'
    if 'safety' in clean or 'physical' in clean: return 'Physical Safety & Awareness'
    if 'other' in clean: return 'Other'

    return None


# ==========================================
# MAIN SCRIPT
# ==========================================
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Load Data
    print(f"Loading data from {DATA_FILE}...")
    try:
        raw_df = pd.read_excel(DATA_FILE)
        df = raw_df.iloc[1:].reset_index(drop=True)
        df.columns = [str(c).replace('\xa0', ' ').strip() for c in df.columns]
    except Exception as e:
        print(f"Error loading file: {e}")
        return

    # 2. Apply Date Filter
    date_col = next((c for c in ['RecordedDate', 'StartDate', 'EndDate'] if c in df.columns), None)
    if date_col:
        df['temp_date'] = pd.to_datetime(df[date_col], errors='coerce', format='mixed')
        df = df[df['temp_date'] >= pd.to_datetime(START_DATE)]

    # 3. Apply Outliers Filter
    if os.path.exists(OUTLIERS_FILE):
        with open(OUTLIERS_FILE, 'r', encoding='utf-8') as f:
            outliers = [line.strip() for line in f if line.strip()]
        if 'ResponseId' in df.columns:
            df = df[~df['ResponseId'].isin(outliers)]

    print(f"Total valid participants: {len(df)}")

    # 4. Generate a plot for each scenario
    for letter, (num, name) in SCENARIOS.items():
        pref_col = f"{letter}. Overall"
        reason_col = f"{letter}. Overall Why"

        if pref_col not in df.columns:
            print(f"Warning: Column '{pref_col}' not found. Skipping Scenario {num}.")
            continue

        # --- PROCESS PREFERENCES ---
        mapped_series = df[pref_col].apply(categorize_overall_preference).dropna()
        counts = mapped_series.value_counts().to_dict()

        for fmt in COLORS.keys():
            if fmt not in counts:
                counts[fmt] = 0

        sorted_counts = dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))
        labels = list(sorted_counts.keys())
        values = list(sorted_counts.values())
        bar_colors = [COLORS[lbl] for lbl in labels]

        # --- PROCESS REASONS ---
        top_reasons = []
        if reason_col in df.columns:
            all_reasons = []
            for val in df[reason_col].dropna():
                items = re.split(r',(?!\s)', str(val))
                for item in items:
                    clean_item = item.strip()
                    if clean_item:
                        mapped_reason = clean_and_map_reason(clean_item)
                        if mapped_reason:
                            all_reasons.append(mapped_reason)

            # Count and get top 2
            top_reasons = Counter(all_reasons).most_common(2)

        # --- GENERATE PLOT ---
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.set_axisbelow(True)

        bars = ax.bar(labels, values, color=bar_colors, edgecolor='black', linewidth=1.2, zorder=3)

        for bar in bars:
            yval = bar.get_height()
            if yval > 0:
                ax.text(bar.get_x() + bar.get_width()/2, yval + 0.3, str(int(yval)),
                        ha='center', va='bottom', fontsize=12, fontweight='bold')

        # Formatting
        ax.set_title(f"Overall Preferred Version\n(Scenario {num}: {name})", fontsize=14, weight='bold', pad=15)
        ax.set_ylabel("Number of Participants", fontsize=12, weight='bold', labelpad=10)

        # Increase Y-Axis height significantly to make room for the legend box
        max_val = max(values) if values else 10
        ax.set_ylim(0, max_val + (max_val * 0.35) + 1)
        ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))

        ax.set_xticklabels(labels, fontsize=11, weight='bold')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(axis='y', linestyle='--', alpha=0.7, zorder=0)

        # --- ADD TOP REASONS LEGEND ---
        if top_reasons:
            legend_elements = []
            for reason, r_count in top_reasons:
                r_color = REASON_COLORS.get(reason, '#333333')
                legend_elements.append(Patch(facecolor=r_color, edgecolor='black', label=f"{reason} (n={r_count})"))

            ax.legend(handles=legend_elements, title="Top Two Reasons for Choice:",
                      loc='upper center', frameon=True, facecolor='#F8F9F9',
                      edgecolor='#BDC3C7', fontsize=10, title_fontproperties={'weight':'bold'})

        # Save
        safe_name = name.replace(" ", "_").replace("/", "_")
        out_path = os.path.join(OUTPUT_DIR, f"Scenario_{num}_{safe_name}.png")
        plt.tight_layout()
        plt.savefig(out_path, dpi=300)
        plt.close()

        print(f"Saved plot: {out_path}")


if __name__ == '__main__':
    main()
