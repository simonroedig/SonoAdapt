"""
Compute Per-Scenario Descriptive Means
========================================
Generates per-scenario descriptive means for each Notification Type × Dimension.
Outputs both a readable table and JSON files (Likert means + normalized costs).

Originally: compute_per_scenario_means.py
"""
import sys
import os
import json
import warnings
warnings.filterwarnings('ignore')

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared_utils import load_and_filter_data, transform_to_long_format, get_data_paths

# Taguchi L9 scenario definitions
SCENARIOS = [
    {"scenario_id": 1, "description": "Coding at home in a quiet apartment",
     "social_setting": "Alone", "task_load": "High mental", "soundscape": "Quiet"},
    {"scenario_id": 2, "description": "Listening to music on the couch at home",
     "social_setting": "Alone", "task_load": "Low", "soundscape": "Music"},
    {"scenario_id": 3, "description": "Cooking dinner alone with a podcast on",
     "social_setting": "Alone", "task_load": "High physical", "soundscape": "Speech"},
    {"scenario_id": 4, "description": "Studying alone in a café with background music",
     "social_setting": "Passive", "task_load": "High mental", "soundscape": "Music"},
    {"scenario_id": 5, "description": "Grocery shopping with store announcements",
     "social_setting": "Passive", "task_load": "Low", "soundscape": "Speech"},
    {"scenario_id": 6, "description": "Cycling alone through a street with minor traffic",
     "social_setting": "Passive", "task_load": "High physical", "soundscape": "Quiet"},
    {"scenario_id": 7, "description": "Team meeting, actively contributing",
     "social_setting": "Interactive", "task_load": "High mental", "soundscape": "Speech"},
    {"scenario_id": 8, "description": "Having a friend over, she briefly checks her phone",
     "social_setting": "Interactive", "task_load": "Low", "soundscape": "Quiet"},
    {"scenario_id": 9, "description": "Setting up a tent with friends",
     "social_setting": "Interactive", "task_load": "High physical", "soundscape": "Music"},
]


def main():
    data_file, outliers_file, script_dir, final_dir = get_data_paths(__file__)

    df, _ = load_and_filter_data(data_file, outliers_file)
    long_df = transform_to_long_format(df).dropna(
        subset=['Disruption', 'Social_Acceptability', 'Detectability', 'ResponseId']
    )

    print(f"Total observations: {len(long_df)}")
    print(f"Unique participants: {long_df['ResponseId'].nunique()}")
    print()

    dvs = ['Disruption', 'Social_Acceptability', 'Detectability']
    nt_types = ['Earcon', 'Short Speech', 'Rich Speech']

    results = []

    print("=" * 100)
    print("PER-SCENARIO DESCRIPTIVE MEANS (7-point Likert scale)")
    print("=" * 100)

    for sc in SCENARIOS:
        sid = sc['scenario_id']
        mask = (
            (long_df['Asocial'] == sc['social_setting']) &
            (long_df['e_Task'] == sc['task_load']) &
            (long_df['CM'] == sc['soundscape'])
        )
        sc_data = long_df[mask]

        print(f"\n--- Scenario {sid}: {sc['description']} ---")
        print(f"    [{sc['social_setting']} | {sc['task_load']} | {sc['soundscape']}]")
        print(f"    Observations: {len(sc_data)}")

        scenario_json = {
            "scenario_id": sid,
            "description": sc['description'],
            "factors": {
                "social_setting": sc['social_setting'],
                "task_load": sc['task_load'],
                "soundscape": sc['soundscape']
            },
            "likert_means": {}
        }

        for dv in dvs:
            dv_key = dv.lower()
            scenario_json["likert_means"][dv_key] = {}
            row = []
            for nt in nt_types:
                vals = sc_data[sc_data['Notification_Type'] == nt][dv]
                mean_val = round(vals.mean(), 2)
                sd_val = round(vals.std(), 2)
                n = len(vals)
                nt_key = nt.lower().replace(' ', '_')
                scenario_json["likert_means"][dv_key][nt_key] = mean_val
                row.append(f"{nt}: M={mean_val}, SD={sd_val}, n={n}")
            print(f"    {dv:25s}: {' | '.join(row)}")

        results.append(scenario_json)

    # Save JSON (raw Likert means)
    output_path = os.path.join(final_dir, 'perScenarioLikertMeans.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
    print(f"\n\nJSON saved to: {output_path}")

    # Normalized Costs (0 = min cost, 1 = max cost)
    normalized_results = []
    for sc_json in results:
        norm_sc = {
            "scenario_id": sc_json["scenario_id"],
            "description": sc_json["description"],
            "factors": sc_json["factors"],
            "costs": {}
        }
        means = sc_json["likert_means"]

        norm_sc["costs"]["disruption_cost"] = {
            nt: round((v - 1) / 6, 2) for nt, v in means["disruption"].items()
        }
        norm_sc["costs"]["social_cost"] = {
            nt: round((7 - v) / 6, 2) for nt, v in means["social_acceptability"].items()
        }
        norm_sc["costs"]["masking_cost"] = {
            nt: round((7 - v) / 6, 2) for nt, v in means["detectability"].items()
        }

        normalized_results.append(norm_sc)

    norm_output_path = os.path.join(final_dir, 'perScenarioNormalizedCosts.json')
    with open(norm_output_path, 'w', encoding='utf-8') as f:
        json.dump(normalized_results, f, indent=4, ensure_ascii=False)
    print(f"JSON saved to: {norm_output_path}")


if __name__ == '__main__':
    main()
