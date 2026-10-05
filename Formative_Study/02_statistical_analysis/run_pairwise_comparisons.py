"""
Run All Pairwise LMM Comparisons
==================================
Re-fits LMMs with shifted reference levels to extract all pairwise
comparisons between factor levels (Notification Type, Social Setting,
Task Load, Soundscape) for each dependent variable.

Originally: calc.py + calc2.py (merged)
"""
import sys
import os
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import statsmodels.formula.api as smf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared_utils import load_and_filter_data, transform_to_long_format, get_data_paths


def main():
    data_file, outliers_file, _, _ = get_data_paths(__file__)

    df, _ = load_and_filter_data(data_file, outliers_file)
    model_data = transform_to_long_format(df).dropna(
        subset=['Disruption', 'Social_Acceptability', 'Detectability', 'Appropriateness', 'ResponseId']
    )

    # ============================
    # Part 1: Default reference levels (from calc.py)
    # ============================
    print("=" * 60)
    print("PAIRWISE COMPARISONS (Default Reference Levels)")
    print("=" * 60)

    for dv, ref_configs in [
        ("Disruption", {
            'Notification_Type': 'Earcon',
            'Asocial': 'Interactive',
            'e_Task': 'Low',
            'CM': 'Quiet'
        }),
        ("Social_Acceptability", {
            'Notification_Type': 'Earcon',
            'Asocial': 'Interactive',
            'e_Task': 'Low',
            'CM': 'Quiet'
        }),
        ("Detectability", {
            'Notification_Type': 'Earcon',
            'Asocial': 'Interactive',
            'e_Task': 'Low',
            'CM': 'Quiet'
        })
    ]:
        parts = []
        for iv, ref in ref_configs.items():
            parts.append(f"C({iv}, Treatment(reference='{ref}'))")
        formula = f"{dv} ~ " + " + ".join(parts)
        m = smf.mixedlm(formula, data=model_data, groups=model_data['ResponseId']).fit(reml=False)
        print(f'\n=== {dv} P-VALUES ===')
        print(m.pvalues)

    # ============================
    # Part 2: Rich vs Short Speech (from calc2.py)
    # ============================
    print("\n" + "=" * 60)
    print("RICH SPEECH vs SHORT SPEECH (Shifted Reference)")
    print("=" * 60)

    for dv in ['Disruption', 'Social_Acceptability', 'Detectability']:
        f = f"{dv} ~ C(Notification_Type, Treatment(reference='Short Speech')) + C(Asocial) + C(e_Task) + C(CM)"
        m = smf.mixedlm(f, data=model_data, groups=model_data['ResponseId']).fit(reml=False)
        p = m.pvalues["C(Notification_Type, Treatment(reference='Short Speech'))[T.Rich Speech]"]
        c = m.params["C(Notification_Type, Treatment(reference='Short Speech'))[T.Rich Speech]"]
        print(f"{dv}: Rich vs Short = {c:.3f} (p={p:.3e})")


if __name__ == '__main__':
    main()
