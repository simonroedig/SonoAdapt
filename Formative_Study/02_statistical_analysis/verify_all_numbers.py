"""
Verify All Numbers Cited in the Thesis
========================================
Cross-checks every statistical number cited in the LaTeX thesis
against the actual data. Reports means, pairwise betas, and p-values.

Originally: verify_all.py
"""
import sys
import os
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import statsmodels.formula.api as smf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared_utils import load_and_filter_data, transform_to_long_format, get_data_paths


def fit_lmm(dv, long_df, ref_overrides=None):
    """Fit LMM with optional reference level overrides."""
    refs = {
        'Notification_Type': 'Earcon',
        'Asocial': 'Alone',
        'e_Task': 'High mental',
        'CM': 'Music'
    }
    if ref_overrides:
        refs.update(ref_overrides)

    parts = []
    for iv, ref in refs.items():
        parts.append(f"C({iv}, Treatment(reference='{ref}'))")
    formula = f"{dv} ~ " + " + ".join(parts)
    m = smf.mixedlm(formula, data=long_df, groups=long_df['ResponseId']).fit(reml=False)
    return m


def get_coef(model, iv, ref, level):
    key = f"C({iv}, Treatment(reference='{ref}'))[T.{level}]"
    return model.params[key], model.pvalues[key]


def sig_label(p, threshold=0.0167):
    if p < 0.001: return '***'
    if p < 0.01: return '**'
    if p < threshold: return '*'
    return 'ns'


def main():
    data_file, outliers_file, _, _ = get_data_paths(__file__)

    df, _ = load_and_filter_data(data_file, outliers_file)
    long_df = transform_to_long_format(df).dropna(
        subset=['Disruption', 'Social_Acceptability', 'Detectability', 'Appropriateness', 'ResponseId']
    )

    print("=" * 70)
    print("1. OVERALL MEANS BY NOTIFICATION TYPE")
    print("=" * 70)
    for dv in ['Disruption', 'Social_Acceptability', 'Detectability']:
        print(f"\n--- {dv} ---")
        for nt in ['Earcon', 'Short Speech', 'Rich Speech']:
            vals = long_df[long_df['Notification_Type'] == nt][dv]
            print(f"  {nt}: M={vals.mean():.2f}, SD={vals.std():.2f}")

    print("\n" + "=" * 70)
    print("2. DISRUPTION BY TASK LOAD (Overall)")
    print("=" * 70)
    for task in ['High mental', 'Low', 'High physical']:
        vals = long_df[long_df['e_Task'] == task]['Disruption']
        print(f"  {task}: M={vals.mean():.2f}")
    print("\n  By Notification Type:")
    for task in ['High mental', 'Low', 'High physical']:
        for nt in ['Earcon', 'Short Speech', 'Rich Speech']:
            vals = long_df[(long_df['e_Task'] == task) & (long_df['Notification_Type'] == nt)]['Disruption']
            print(f"    {task} / {nt}: M={vals.mean():.2f}")

    print("\n" + "=" * 70)
    print("3. SOCIAL ACCEPTABILITY BY SOCIAL SETTING (Overall)")
    print("=" * 70)
    for soc in ['Alone', 'Passive', 'Interactive']:
        vals = long_df[long_df['Asocial'] == soc]['Social_Acceptability']
        print(f"  {soc}: M={vals.mean():.2f}")
    print("\n  By Notification Type:")
    for soc in ['Alone', 'Passive', 'Interactive']:
        for nt in ['Earcon', 'Short Speech', 'Rich Speech']:
            vals = long_df[(long_df['Asocial'] == soc) & (long_df['Notification_Type'] == nt)]['Social_Acceptability']
            print(f"    {soc} / {nt}: M={vals.mean():.2f}")

    print("\n" + "=" * 70)
    print("4. DETECTABILITY BY SOUNDSCAPE (Overall)")
    print("=" * 70)
    for cm in ['Quiet', 'Music', 'Speech']:
        vals = long_df[long_df['CM'] == cm]['Detectability']
        print(f"  {cm}: M={vals.mean():.2f}")
    print("\n  By Notification Type:")
    for cm in ['Quiet', 'Music', 'Speech']:
        for nt in ['Earcon', 'Short Speech', 'Rich Speech']:
            vals = long_df[(long_df['CM'] == cm) & (long_df['Notification_Type'] == nt)]['Detectability']
            print(f"    {cm} / {nt}: M={vals.mean():.2f}")

    print("\n" + "=" * 70)
    print("5. FULL PAIRWISE SIGNIFICANCE TESTS")
    print("=" * 70)

    pairwise_config = {
        'Disruption': {
            'e_Task': ['High mental', 'Low', 'High physical'],
            'Asocial': ['Alone', 'Interactive', 'Passive'],
            'CM': ['Music', 'Quiet', 'Speech'],
        },
        'Social_Acceptability': {
            'Asocial': ['Alone', 'Interactive', 'Passive'],
            'e_Task': ['High mental', 'Low', 'High physical'],
            'CM': ['Music', 'Quiet', 'Speech'],
        },
        'Detectability': {
            'CM': ['Music', 'Quiet', 'Speech'],
            'Asocial': ['Alone', 'Interactive', 'Passive'],
            'e_Task': ['High mental', 'Low', 'High physical'],
        }
    }

    for dv, ivs in pairwise_config.items():
        print(f"\n--- {dv} ---")
        for iv, levels in ivs.items():
            print(f"  {iv}:")
            for i in range(len(levels)):
                for j in range(i + 1, len(levels)):
                    ref = levels[i]
                    target = levels[j]
                    m = fit_lmm(dv, long_df, {iv: ref})
                    beta, p = get_coef(m, iv, ref, target)
                    label = sig_label(p)
                    print(f"    {ref} vs {target}: beta={beta:.3f}, p={p:.4e} => {label}")

    print("\n" + "=" * 70)
    print("6. NOTIFICATION TYPE PAIRWISE")
    print("=" * 70)
    for dv in ['Disruption', 'Social_Acceptability', 'Detectability']:
        print(f"\n--- {dv} ---")
        nt_levels = ['Earcon', 'Short Speech', 'Rich Speech']
        for i in range(len(nt_levels)):
            for j in range(i + 1, len(nt_levels)):
                ref = nt_levels[i]
                target = nt_levels[j]
                m = fit_lmm(dv, long_df, {'Notification_Type': ref})
                beta, p = get_coef(m, 'Notification_Type', ref, target)
                label = sig_label(p)
                print(f"  {ref} vs {target}: beta={beta:.3f}, p={p:.4e} => {label}")

    print("\n" + "=" * 70)
    print("7. DESCRIPTIVE SUMMARY TABLE CHECK")
    print("=" * 70)
    print("\nDisruption by Task Load:")
    for nt in ['Earcon', 'Short Speech', 'Rich Speech']:
        row = []
        for task in ['Low', 'High mental', 'High physical']:
            vals = long_df[(long_df['e_Task'] == task) & (long_df['Notification_Type'] == nt)]['Disruption']
            row.append(f"{vals.mean():.2f}")
        print(f"  {nt}: Low={row[0]}, HiMental={row[1]}, HiPhys={row[2]}")

    print("\nSocial Acceptability by Social Setting:")
    for nt in ['Earcon', 'Short Speech', 'Rich Speech']:
        row = []
        for soc in ['Alone', 'Passive', 'Interactive']:
            vals = long_df[(long_df['Asocial'] == soc) & (long_df['Notification_Type'] == nt)]['Social_Acceptability']
            row.append(f"{vals.mean():.2f}")
        print(f"  {nt}: Alone={row[0]}, Passive={row[1]}, Interactive={row[2]}")

    print("\nDetectability by Soundscape:")
    for nt in ['Earcon', 'Short Speech', 'Rich Speech']:
        row = []
        for cm in ['Quiet', 'Music', 'Speech']:
            vals = long_df[(long_df['CM'] == cm) & (long_df['Notification_Type'] == nt)]['Detectability']
            row.append(f"{vals.mean():.2f}")
        print(f"  {nt}: Quiet={row[0]}, Music={row[1]}, Speech={row[2]}")


if __name__ == '__main__':
    main()
