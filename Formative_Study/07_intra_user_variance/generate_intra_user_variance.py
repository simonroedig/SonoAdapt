"""
Generate Intra-User Variance Plots
=====================================
Creates two key plots showing how much participants change their notification
type preference across the 9 scenarios (Stage 2):

  1. Type variance bar chart (how many unique types each user chose)
  2. Speech profile bar chart (loyalty to Rich vs Short Speech)

Outputs:
  - 01_Stage2_Type_Variance.png
  - 02_Stage2_Speech_Profile.png

Originally: intraUserVariance.py
"""
import pandas as pd
import matplotlib.pyplot as plt
import os
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

SCENARIOS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def categorize_preference(val):
    """Maps free-text or standard Qualtrics responses to plotting categories."""
    if pd.isna(val):
        return None
    val_str = str(val).lower()

    if 'none' in val_str or 'no audio' in val_str or 'mute' in val_str:
        return 'No Audio'
    elif '1' in val_str or 'earcon' in val_str or 'sound' in val_str:
        return 'Version 1'  # Earcon
    elif '2' in val_str or 'short' in val_str:
        return 'Version 2'  # Short Speech
    elif '3' in val_str or 'rich' in val_str:
        return 'Version 3'  # Rich Speech
    return 'Other'


def get_final_stage3_choice(row, sc):
    """Calculate the final Stage 3 choice based on Timing logic."""
    overall_val = row.get(f"{sc}. Overall")
    follow_val = row.get(f"{sc}. Timing Follow")

    overall_cat = categorize_preference(overall_val)

    if pd.isna(follow_val) or str(follow_val).strip() == '':
        return overall_cat

    follow_str = str(follow_val).lower()

    if 'same' in follow_str or 'previous' in follow_str or 'immediate' in follow_str:
        return overall_cat

    follow_cat = categorize_preference(follow_val)

    if follow_cat == 'Other' or follow_cat is None:
        return overall_cat

    return follow_cat


def get_speech_profile(row):
    """Determines a user's loyalty to specific speech lengths."""
    choices = set(row.dropna().values)

    has_rich = 'Version 3' in choices
    has_short = 'Version 2' in choices

    if has_rich and has_short:
        return 'Speech Switcher\n(Uses Both)'
    elif has_rich:
        return 'Rich Speech Loyalist\n(Never Short)'
    elif has_short:
        return 'Short Speech Loyalist\n(Never Rich)'
    else:
        return 'No Speech Used\n(Only Earcon/Mute)'


# ==========================================
# PLOTTING FUNCTIONS
# ==========================================
def plot_variance(choices_df, title, filename):
    unique_counts = choices_df.apply(lambda row: row.dropna().nunique(), axis=1)
    counts = unique_counts.value_counts().sort_index()
    percentages = (counts / len(choices_df)) * 100

    one_style_users = percentages.get(1, 0)
    adaptable_users = 100 - one_style_users

    fig, ax = plt.subplots(figsize=(10, 6))

    color_map = {
        1: '#E8A0A0',
        2: '#A8D5BA',
        3: '#5BAE8A',
        4: '#2E7D5B',
    }
    bar_colors = [color_map.get(x, '#A8D5BA') for x in counts.index]
    bars = ax.bar(counts.index, percentages.values, color=bar_colors, edgecolor='black', linewidth=1.2)

    for bar in bars:
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, yval + 1, f'{yval:.1f}%',
                ha='center', va='bottom', fontsize=12, fontweight='bold')

    ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
    ax.set_xlabel("Number of Unique Types Chosen\n(No Audio, Earcon, Short Speech, Rich Speech)", fontsize=12, labelpad=15)
    ax.set_ylabel("Percentage of Participants (%)", fontsize=12, labelpad=10)

    x_labels = ["1 Style\n(Static)", "2 Styles", "3 Styles", "4 Styles\n(Highly Adaptive)"]
    ax.set_xticks(range(1, 5))
    ax.set_xticklabels(x_labels, fontsize=11)
    ax.set_ylim(0, percentages.max() + 18)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y', linestyle='--', alpha=0.7)

    bracket_bars = [i for i in counts.index if i > 1]
    if bracket_bars:
        max_bar_val = max(percentages.get(i, 0) for i in bracket_bars)
        bracket_y = max_bar_val + 8
        drop = 2

        bracket_left = min(bracket_bars) - 0.35
        bracket_right = max(bracket_bars) + 0.35

        ax.plot([bracket_left, bracket_right], [bracket_y, bracket_y], color='#333333', lw=1.8, zorder=4)
        ax.plot([bracket_left, bracket_left], [bracket_y, bracket_y - drop], color='#333333', lw=1.8, zorder=4)
        mid_cap_x = 3
        ax.plot([mid_cap_x, mid_cap_x], [bracket_y, bracket_y - drop], color='#333333', lw=1.8, zorder=4)
        ax.plot([bracket_right, bracket_right], [bracket_y, bracket_y - drop], color='#333333', lw=1.8, zorder=4)

        mid_x = (bracket_left + bracket_right) / 2
        ax.text(mid_x, bracket_y + 2, f"~{adaptable_users:.0f}% adapt across scenarios",
                ha='center', va='bottom', fontsize=11, fontweight='bold', color='#2E7D5B',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#E8F5E9', edgecolor='#2E7D5B', lw=1.5))

    out_path = os.path.join(OUTPUT_DIR, filename)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close(fig)


def plot_speech_profile(choices_df, title, filename):
    profiles = choices_df.apply(get_speech_profile, axis=1)
    profile_counts = profiles.value_counts()
    profile_pcts = (profile_counts / len(choices_df)) * 100

    order = [
        'Rich Speech Loyalist\n(Never Short)',
        'Short Speech Loyalist\n(Never Rich)',
        'Speech Switcher\n(Uses Both)',
        'No Speech Used\n(Only Earcon/Mute)'
    ]
    plot_data = [profile_pcts.get(cat, 0) for cat in order]

    profile_colors = ['#694487', '#AF7AC5', '#9B59B6', '#A6A6A6']

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(order, plot_data, color=profile_colors, edgecolor='black', linewidth=1.2)

    for bar in bars:
        yval = bar.get_height()
        if yval > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, yval + 1, f'{yval:.1f}%',
                    ha='center', va='bottom', fontsize=12, fontweight='bold')

    ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
    ax.set_ylabel("Percentage of Participants (%)", fontsize=12, labelpad=10)
    ax.set_ylim(0, max(plot_data) + 15)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y', linestyle='--', alpha=0.7)

    out_path = os.path.join(OUTPUT_DIR, filename)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close(fig)

    print(f"\n--- {filename} STATS ---")
    for cat in order:
        print(f"{cat.replace(chr(10), ' ')}: {profile_pcts.get(cat, 0):.1f}%")


# ==========================================
# MAIN SCRIPT
# ==========================================
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Loading data from {DATA_FILE}...")

    try:
        raw_df = pd.read_excel(DATA_FILE)
        df = raw_df.iloc[1:].reset_index(drop=True)
        df.columns = [str(c).replace('\xa0', ' ').strip() for c in df.columns]
    except Exception as e:
        print(f"Error loading file: {e}")
        return

    # Filter by Date and Outliers
    date_col = next((c for c in ['RecordedDate', 'StartDate', 'EndDate'] if c in df.columns), None)
    if date_col:
        df['temp_date'] = pd.to_datetime(df[date_col], errors='coerce', format='mixed')
        df = df[df['temp_date'] >= pd.to_datetime(START_DATE)]

    if os.path.exists(OUTLIERS_FILE):
        with open(OUTLIERS_FILE, 'r', encoding='utf-8') as f:
            outliers = [line.strip() for line in f if line.strip()]
        if 'ResponseId' in df.columns:
            df = df[~df['ResponseId'].isin(outliers)]

    # DATA EXTRACTION (STAGE 2)
    stage2_choices = pd.DataFrame()

    for sc in SCENARIOS:
        if f"{sc}. Overall" in df.columns:
            stage2_choices[f"{sc}_Overall"] = df[f"{sc}. Overall"].apply(categorize_preference)

    # Filter out users who didn't answer enough scenarios
    scenarios_answered = stage2_choices.apply(lambda row: row.notna().sum(), axis=1)
    valid_idx = scenarios_answered >= 5

    valid_stage2 = stage2_choices[valid_idx].copy()

    print(f"Total valid participants to analyze: {len(valid_stage2)}")

    # GENERATE PLOTS
    print("\nGenerating Stage 2 (Initial Choice) Plots...")
    plot_variance(valid_stage2,
                  "Intra-User Type Variance (Stage 2):\nDo participants stick to one favorite, or adapt to the context?",
                  "01_Stage2_Type_Variance.png")

    plot_speech_profile(valid_stage2,
                        "Intra-User Speech Type Variance (Stage 2):\nDo participants stick to one favorite, or adapt to the context?",
                        "02_Stage2_Speech_Profile.png")

    print(f"\nSuccessfully generated 2 plots in {OUTPUT_DIR}/")


if __name__ == '__main__':
    main()
