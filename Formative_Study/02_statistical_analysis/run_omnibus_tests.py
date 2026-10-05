"""
Omnibus Main Effect Tests (Type III Wald Chi-Square) for all LMMs
=================================================================
Runs the omnibus Wald χ² tests for each factor across all three DVs.
Must be run BEFORE pairwise comparisons are justified.

Originally: omnibus_test.py
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


def omnibus_wald_test(result, factor_name):
    """
    Perform an omnibus Wald chi-square test for a categorical factor.
    Tests H0: all coefficients for this factor are simultaneously zero.
    Returns chi2 statistic, df, and p-value.
    """
    param_names = [name for name in result.params.index if name.startswith(f'C({factor_name}')]

    if not param_names:
        return None, None, None

    indices = [list(result.params.index).index(name) for name in param_names]

    R = np.zeros((len(indices), len(result.params)))
    for i, idx in enumerate(indices):
        R[i, idx] = 1.0

    wald_result = result.wald_test(R)
    chi2 = float(wald_result.statistic)
    df = int(wald_result.df_denom) if hasattr(wald_result, 'df_denom') else len(indices)
    p_value = float(wald_result.pvalue)

    return chi2, len(indices), p_value


def main():
    data_file, outliers_file, _, _ = get_data_paths(__file__)

    df, _ = load_and_filter_data(data_file, outliers_file)
    model_data = transform_to_long_format(df).dropna(
        subset=['Disruption', 'Social_Acceptability', 'Detectability', 'Appropriateness', 'ResponseId']
    )

    dvs = ['Disruption', 'Social_Acceptability', 'Detectability']
    factors = ['Notification_Type', 'Asocial', 'e_Task', 'CM']
    factor_labels = {
        'Notification_Type': 'Notification Type',
        'Asocial': 'Social Setting',
        'e_Task': 'Task Load',
        'CM': 'Soundscape'
    }

    print("=" * 80)
    print("OMNIBUS MAIN EFFECT TESTS (Type III Wald Chi-Square)")
    print("=" * 80)
    print()

    results = {}

    for dv in dvs:
        formula = f"{dv} ~ C(Notification_Type) + C(Asocial) + C(e_Task) + C(CM)"
        model = smf.mixedlm(formula, data=model_data, groups=model_data['ResponseId'])
        res = model.fit(reml=False)

        print(f"--- {dv} ---")
        results[dv] = {}

        for factor in factors:
            chi2, df_val, p = omnibus_wald_test(res, factor)
            sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"
            results[dv][factor] = (chi2, df_val, p, sig)
            print(f"  {factor_labels[factor]:25s}: chi2({df_val}) = {chi2:8.3f}, p = {p:.2e}  {sig}")
        print()

    # Print LaTeX-ready summary table
    print("=" * 80)
    print("LATEX-READY SUMMARY TABLE")
    print("=" * 80)
    print()
    print("\\begin{table}[H]")
    print("\\centering")
    print("\\caption{Omnibus main effect tests (Type III Wald $\\chi^2$) for each factor across the three dependent variables. Significance threshold: Bonferroni-corrected $\\alpha = .0167$.}")
    print("\\label{tab:omnibus_tests}")
    print("\\begin{tabular}{@{}lccc@{}}")
    print("\\toprule")
    print("\\textbf{Factor} & \\textbf{Disruption} & \\textbf{Social Acc.} & \\textbf{Detectability} \\\\")
    print("\\midrule")

    for factor in factors:
        row_parts = [f"\\textit{{{factor_labels[factor]}}}"]
        for dv in dvs:
            chi2, df_val, p, sig = results[dv][factor]
            cell = f"$\\chi^2({df_val}) = {chi2:.2f}${sig}"
            row_parts.append(cell)
        print(" & ".join(row_parts) + " \\\\")

    print("\\bottomrule")
    print("\\end{tabular}")
    print("\\end{table}")

    print()
    print("=" * 80)
    print("INTERPRETATION")
    print("=" * 80)
    print()
    for dv in dvs:
        print(f"--- {dv} ---")
        for factor in factors:
            chi2, df_val, p, sig = results[dv][factor]
            if sig != "ns":
                print(f"  {factor_labels[factor]:25s}: SIGNIFICANT => pairwise comparisons JUSTIFIED")
            else:
                print(f"  {factor_labels[factor]:25s}: NOT significant => pairwise comparisons NOT justified")
        print()


if __name__ == '__main__':
    main()
