"""
Run Linear Mixed Models (LMMs) for the Formative Study
========================================================
Fits three main-effect LMMs (Disruption, Social Acceptability, Detectability),
one Appropriateness model, calculates descriptive statistics, R² values,
and runs a dominance (relative importance) analysis.

Outputs all results to console and saves descriptive_statistics.csv.
Originally: analysis.py
"""
import sys
import os
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import statsmodels.formula.api as smf
import pingouin as pg

# Add parent directory (final/) to path so we can import shared_utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared_utils import load_and_filter_data, transform_to_long_format, get_data_paths


def print_model_fit_stats(res, model_name):
    """Calculate and print AIC and Nakagawa's R² for a fitted LMM."""
    aic = res.aic
    var_f = np.var(res.fittedvalues)
    var_r = float(res.cov_re.iloc[0, 0])
    var_e = res.scale

    r2_marg = var_f / (var_f + var_r + var_e)
    r2_cond = (var_f + var_r) / (var_f + var_r + var_e)

    print(f"--- Fit Statistics for {model_name} ---")
    print(f"AIC:      {aic:.2f}")
    print(f"R2_marg:  {r2_marg:.3f}")
    print(f"R2_cond:  {r2_cond:.3f}")
    print("-" * 40 + "\n")


def calculate_descriptives(long_df):
    """Calculate and save descriptive statistics (means & SDs)."""
    print("\nCalculating Descriptive Statistics (Means & SDs)...")
    desc_stats = long_df.groupby(['Notification_Type', 'Asocial', 'e_Task', 'CM'])[
        ['Detectability', 'Disruption', 'Social_Acceptability', 'Appropriateness']
    ].agg(['mean', 'std']).round(2)

    desc_stats.to_csv('descriptive_statistics.csv')
    print("-> Descriptive statistics saved successfully to 'descriptive_statistics.csv'.")
    return desc_stats


def run_dominance_analysis(long_df):
    """Run relative importance (dominance) analysis for Appropriateness."""
    print("\n" + "=" * 50)
    print("RELATIVE IMPORTANCE ANALYSIS (DOMINANCE)")
    print("=" * 50)

    df_clean = long_df.dropna(subset=['Appropriateness', 'Social_Acceptability', 'Detectability', 'Disruption'])
    X = df_clean[['Social_Acceptability', 'Detectability', 'Disruption']]
    y = df_clean['Appropriateness']

    lm = pg.linear_regression(X, y, relimp=True)
    relimp_df = lm[['names', 'relimp']].iloc[1:].copy()

    total_relimp = relimp_df['relimp'].sum()
    relimp_df['Normalized_Weight'] = (relimp_df['relimp'] / total_relimp).round(3)
    relimp_df['Percentage'] = (relimp_df['Normalized_Weight'] * 100).round(1).astype(str) + '%'

    print(relimp_df[['names', 'Normalized_Weight', 'Percentage']].to_string(index=False))


def run_lmm_analysis(long_df):
    """Fit and print LMMs for Disruption, Social Acceptability, Detectability, and Appropriateness."""
    print("\n" + "=" * 50)
    print("RUNNING LINEAR MIXED MODELS (LMM)")
    print("=" * 50)

    model_data = long_df.dropna(subset=['Disruption', 'Social_Acceptability', 'Detectability', 'Appropriateness', 'ResponseId'])

    if model_data.empty:
        print("Error: Not enough valid data to run LMMs. Check data formatting.")
        return

    # 1. Main Effect Model for Disruption
    print("\n--- MODEL 1: DISRUPTION ---")
    formula_disrupt = "Disruption ~ C(Notification_Type) + C(Asocial) + C(e_Task) + C(CM)"
    try:
        res_disrupt = smf.mixedlm(formula_disrupt, data=model_data, groups=model_data["ResponseId"]).fit(reml=False)
        print(res_disrupt.summary())
        print_model_fit_stats(res_disrupt, "Disruption")
    except Exception as e:
        print(f"Model failed to fit: {e}")

    # 2. Main Effect Model for Social Acceptability
    print("\n--- MODEL 2: SOCIAL ACCEPTABILITY ---")
    formula_social = "Social_Acceptability ~ C(Notification_Type) + C(Asocial) + C(e_Task) + C(CM)"
    try:
        res_social = smf.mixedlm(formula_social, data=model_data, groups=model_data["ResponseId"]).fit(reml=False)
        print(res_social.summary())
        print_model_fit_stats(res_social, "Social Acceptability")
    except Exception as e:
        print(f"Model failed to fit: {e}")

    # 3. Main Effect Model for Detectability
    print("\n--- MODEL 3: DETECTABILITY ---")
    formula_detect = "Detectability ~ C(Notification_Type) + C(Asocial) + C(e_Task) + C(CM)"
    try:
        res_detect = smf.mixedlm(formula_detect, data=model_data, groups=model_data["ResponseId"]).fit(reml=False)
        print(res_detect.summary())
        print_model_fit_stats(res_detect, "Detectability")
    except Exception as e:
        print(f"Model failed to fit: {e}")

    # 4. The Appropriateness Model
    print("\n--- MODEL 4: APPROPRIATENESS ---")
    print("Testing: Which dimensions explain why people find a notification appropriate?")
    formula_approp = "Appropriateness ~ Detectability + Disruption + Social_Acceptability"
    try:
        res_approp = smf.mixedlm(formula_approp, data=model_data, groups=model_data["ResponseId"]).fit(reml=False)
        print(res_approp.summary())
    except Exception as e:
        print(f"Model failed to fit: {e}")


def main():
    data_file, outliers_file, script_dir, _ = get_data_paths(__file__)

    df, stats = load_and_filter_data(data_file, outliers_file)
    long_df = transform_to_long_format(df)

    # Descriptive Statistics
    calculate_descriptives(long_df)

    # Linear Mixed Models
    run_lmm_analysis(long_df)

    # Dominance Analysis
    run_dominance_analysis(long_df)

    # Summary
    print("\n" + "=" * 50)
    print("DATA PROCESSING SUMMARY")
    print("=" * 50)
    print(f"Raw responses loaded:                      {stats['raw_original']}")
    print(f"Responses removed by date filter:          {stats['date_removed']}")
    print(f"Responses remaining before outlier check:  {stats['post_date']}")
    print(f"Responses removed as outliers:             {stats['outliers_removed']}")
    print(f"Final valid participants analyzed:         {stats['final']}")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    # Log output to file
    class Logger:
        def __init__(self, filename):
            self.terminal = sys.stdout
            self.log = open(filename, "w", encoding="utf-8")
        def write(self, message):
            self.terminal.write(message)
            self.log.write(message)
        def flush(self):
            self.terminal.flush()
            self.log.flush()

    sys.stdout = Logger(os.path.join(os.path.dirname(os.path.abspath(__file__)), "lmm_analysis_output.txt"))
    main()
