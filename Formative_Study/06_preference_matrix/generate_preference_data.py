"""
Generate Preference Data (JSON) for the Preference Matrix
============================================================
Processes raw survey data to extract per-scenario preference summaries
(type + timing choices) and saves them as JSON files.

This must be run BEFORE generate_preference_matrix.py.

Outputs:
  - scenario_preferences_summary.json
  - scenario_preferences_summary_othersmerged.json

Originally: preferences.py (data extraction portion)
"""
import pandas as pd
import numpy as np
import os
import json

# ==========================================
# CONFIGURATION
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FINAL_DIR = os.path.dirname(SCRIPT_DIR)
DATA_FILE = os.path.join(FINAL_DIR, "data.xlsx")
OUTLIERS_FILE = os.path.join(FINAL_DIR, "listOfManuallyIdentifiedOutliers.txt")
OUTPUT_DIR = SCRIPT_DIR
START_DATE = "2026-06-30"

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def clean_version(x):
    if pd.isna(x): return x
    x_str = str(x)
    if 'No audio' in x_str: return 'None / No Audio'
    if 'Version 1' in x_str: return 'Earcon (V1)'
    if 'Version 2' in x_str: return 'Short Speech (V2)'
    if 'Version 3' in x_str: return 'Rich Speech (V3)'
    if 'Not applicable' in x_str: return 'N/A'
    return x


def get_timing_cat(x):
    x_str = str(x).lower()
    if 'immediat' in x_str: return 'Immediate'
    if 'other' in x_str: return 'Other'
    return 'Specific_Delay'


def get_final_preference(row, prefix):
    """Determine the final notification type (resolving 'Same' follow-ups)."""
    overall = row.get(f'{prefix}. Overall')
    follow = row.get(f'{prefix}. Timing Follow')

    overall_clean = clean_version(overall)

    if pd.isna(follow) or str(follow).strip() == '':
        return overall_clean

    follow_str = str(follow).lower()
    if 'same' in follow_str or 'previous' in follow_str:
        return overall_clean

    return clean_version(follow)


def main():
    # Load & filter data
    raw_df = pd.read_excel(DATA_FILE)
    df = raw_df.iloc[1:].reset_index(drop=True)
    df.columns = [str(c).replace('\xa0', ' ').strip() for c in df.columns]

    date_col = next((c for c in ['RecordedDate', 'StartDate'] if c in df.columns), None)
    if date_col:
        df['__temp_date'] = pd.to_datetime(df[date_col], errors='coerce', format='mixed')
        df = df[df['__temp_date'] >= pd.to_datetime(START_DATE)]

    if os.path.exists(OUTLIERS_FILE):
        with open(OUTLIERS_FILE, 'r') as f:
            outliers = [line.strip() for line in f if line.strip()]
        if 'ResponseId' in df.columns:
            df = df[~df['ResponseId'].isin(outliers)]

    print(f"Processing {len(df)} valid participants...")

    # Scenario mapping
    SCENARIO_PREFIXES = {
        'Scene_1_Home_Alone_Computer': 'A',
        'Scene_2_Home_Music': 'C',
        'Scene_3_Cooking_Dinner': 'G',
        'Scene_4_Study_Coffee_Shop': 'H',
        'Scene_5_Grocery_Shopping': 'F',
        'Scene_6_Cycle_City': 'E',
        'Scene_7_Team_Meeting': 'B',
        'Scene_8_Quiet_Friend_Over': 'I',
        'Scene_9_Tent': 'D'
    }

    all_results = {}

    for scene_name, prefix in SCENARIO_PREFIXES.items():
        overall_col = f'{prefix}. Overall'
        timing_col = f'{prefix}. Timing'
        follow_col = f'{prefix}. Timing Follow'

        if overall_col not in df.columns:
            continue

        scene_result = {"scenario_name": scene_name.replace('_', ' '), "macro_timing": {}, "micro_timing_delayed_breakdown": {}}

        # Macro timing: Immediate vs Delayed
        if timing_col in df.columns:
            for _, row in df.iterrows():
                timing_val = row.get(timing_col)
                if pd.isna(timing_val):
                    continue

                timing_cat = get_timing_cat(timing_val)
                final_pref = get_final_preference(row, prefix)

                if timing_cat == 'Immediate':
                    if 'Immediate' not in scene_result['macro_timing']:
                        scene_result['macro_timing']['Immediate'] = {}
                    d = scene_result['macro_timing']['Immediate']
                    d[final_pref] = d.get(final_pref, 0) + 1
                    d['Total'] = d.get('Total', 0) + 1
                else:
                    if 'Delayed' not in scene_result['macro_timing']:
                        scene_result['macro_timing']['Delayed'] = {}
                    d = scene_result['macro_timing']['Delayed']
                    d[final_pref] = d.get(final_pref, 0) + 1
                    d['Total'] = d.get('Total', 0) + 1

                    # Micro-timing breakdown
                    timing_str = str(timing_val)
                    if timing_str not in scene_result['micro_timing_delayed_breakdown']:
                        scene_result['micro_timing_delayed_breakdown'][timing_str] = {}
                    mt = scene_result['micro_timing_delayed_breakdown'][timing_str]
                    mt[final_pref] = mt.get(final_pref, 0) + 1
                    mt['Total'] = mt.get('Total', 0) + 1

        all_results[scene_name] = scene_result

    # Save JSON files
    json_path = os.path.join(OUTPUT_DIR, 'scenario_preferences_summary.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=4, ensure_ascii=False)
    print(f"Saved: {json_path}")

    # Also save "othersmerged" version (same data for this extraction)
    merged_path = os.path.join(OUTPUT_DIR, 'scenario_preferences_summary_othersmerged.json')
    with open(merged_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=4, ensure_ascii=False)
    print(f"Saved: {merged_path}")


if __name__ == "__main__":
    main()
