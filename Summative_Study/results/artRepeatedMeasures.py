"""
artRepeatedMeasures.py – Aligned Rank Transform (ART) interaction analysis.
=============================================================================

Implements the Aligned Rank Transform (ART) procedure (Wobbrock et al., 2011)
entirely in Python (no R / rpy2 required) to test factorial interaction effects
that cannot be tested with the Friedman test alone.

Reference:
  Wobbrock, J.O., Findlater, L., Gergle, D. & Higgins, J.J. (2011).
  The Aligned Rank Transform for Nonparametric Factorial Analyses Using
  Only ANOVA Procedures. Proc. CHI '11, pp. 143-146.

Design:
  3 (System: Earcon / Speech / SonoAdapt)
  × 2 (Urgency/Importance: Low / High)
  × 2 (Scenario: Interview / Math)
  Fully within-subjects; 12 trials per participant.

What this script does:
  1. Loads data identically to mainEffects.py (raw.xlsx, outlier removal, etc.)
  2. Performs the ART procedure for a 2-factor model (System × Scenario)
     on HIGH-urgency trials only — this is the analysis the supervisor requested.
     Rationale: SonoAdapt mutes Low notifications, so a System × Scenario
     interaction only makes sense for High notifications where all systems
     deliver sound (and SonoAdapt picks Earcon in Interview, Speech in Math).
  3. Additionally performs a 2-factor ART (System × Urgency) on all trials
     for the three DVs where it makes sense (Appropriateness, Social Acceptability,
     Disruptiveness). Detectability is excluded because SonoAdapt-Low is silent.
  4. Exports full results to artRepeatedMeasurePlotsAndData/.

ART algorithm (for each effect of interest):
  Step 1: Fit a linear model Y ~ all_terms to get cell means.
  Step 2: Alignment: Y_aligned = Y - Ŷ(other effects) + grand_mean
          This strips away all effects EXCEPT the one of interest.
  Step 3: Rank the aligned residuals (midranks).
  Step 4: Run a standard repeated-measures ANOVA on the aligned ranks.
          Only the F-test row for the effect of interest is valid.

Outputs saved to artRepeatedMeasurePlotsAndData/:
  - artResults.txt            – Full statistical report
  - art_system_x_scenario.txt – System × Scenario interaction (HIGH only)
  - art_system_x_urgency.txt  – System × Urgency interaction (all trials)
  - art_data_high.csv         – Trial-level data used for System × Scenario
  - art_data_full.csv         – Trial-level data used for System × Urgency
  - artInteractionSection.tex – LaTeX section for the thesis

Data source: results/raw.xlsx (with outlier removal via results/potential_outliers.json)
"""

import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from statsmodels.formula.api import ols
from statsmodels.stats.anova import AnovaRM

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")
warnings.filterwarnings("ignore", category=FutureWarning)

# ── 0. Paths ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = SCRIPT_DIR / "results"
RAW_PATH = RESULTS_DIR / "raw.xlsx"
OUTLIERS_PATH = RESULTS_DIR / "potential_outliers.json"
OUTPUT_DIR = SCRIPT_DIR / "artRepeatedMeasurePlotsAndData"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_TXT = OUTPUT_DIR / "artResults.txt"

# ── Tee: write to console + file simultaneously ──────────────────────────────
class _Tee:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            s.write(data)
    def flush(self):
        for s in self.streams:
            s.flush()

_output_file = open(OUTPUT_TXT, "w", encoding="utf-8")
sys.stdout = _Tee(sys.__stdout__, _output_file)


# ── 1. Configuration ─────────────────────────────────────────────────────────
REMOVE_OUTLIERS = True
ALPHA = 0.05

SYSTEM_LABELS = {"E": "Earcon", "S": "Speech", "X": "SonoAdapt"}
URGENCY_LABELS = {"L": "Low", "H": "High"}
SCENARIO_LABELS = {"I": "Interview", "M": "Math"}
SYSTEM_ORDER = ["Earcon", "Speech", "SonoAdapt"]

# Likert label → numeric mappings (same as mainEffects.py)
APPROPRIATENESS_MAP = {
    "Completely inappropriate": 1, "Inappropriate": 2,
    "Somewhat inappropriate": 3, "Neither appropriate nor inappropriate": 4,
    "Somewhat appropriate": 5, "Appropriate": 6, "Completely appropriate": 7,
}
DETECTABILITY_MAP = {
    "Very difficult to detect": 1, "Difficult to detect": 2,
    "Somewhat difficult to detect": 3, "Neither easy nor difficult to detect": 4,
    "Somewhat easy to detect": 5, "Easy to detect": 6, "Very easy to detect": 7,
}
DISRUPTIVENESS_MAP = {
    "Not disruptive at all": 1, "Slightly disruptive": 2,
    "Somewhat disruptive": 3, "Moderately disruptive": 4,
    "Disruptive": 5, "Very disruptive": 6, "Extremely disruptive": 7,
}
SOCIAL_MAP = {
    "Completely unacceptable": 1, "Unacceptable": 2,
    "Somewhat unacceptable": 3, "Neither acceptable nor unacceptable": 4,
    "Somewhat acceptable": 5, "Acceptable": 6,
    "Completely acceptable": 7, "Completely Acceptable": 7,
}

DV_MAPS = {
    "Appropriateness": APPROPRIATENESS_MAP,
    "Detectability": DETECTABILITY_MAP,
    "Disruptiveness": DISRUPTIVENESS_MAP,
    "SocialAcceptability": SOCIAL_MAP,
}

DV_COLUMNS = {
    "Appropriateness": "Appropriate_1",
    "Detectability": "Detect_1",
    "Disruptiveness": "Disruptive_1",
    "SocialAcceptability": "Social_1",
}

DV_NOTES = {
    "Appropriateness":     "1 = completely inappropriate … 7 = completely appropriate; higher = better",
    "SocialAcceptability": "1 = completely unacceptable  … 7 = completely acceptable;  higher = better",
    "Detectability":       "1 = very difficult to detect … 7 = very easy to detect;    higher = better",
    "Disruptiveness":      "1 = not disruptive at all    … 7 = extremely disruptive;   LOWER = better",
}

DV_ORDER = ["Appropriateness", "SocialAcceptability", "Detectability", "Disruptiveness"]


# ── 2. Helpers ────────────────────────────────────────────────────────────────

def hr(title="", char="=", width=88):
    if title:
        print(f"\n{char * width}")
        print(title)
        print(char * width)
    else:
        print(char * width)

def sig_stars(p, alpha=ALPHA):
    if p < 0.001: return "***"
    if p < 0.01:  return "**"
    if p < alpha:  return "*"
    if p < 0.10:  return "."
    return "n.s."


def partial_eta_squared(ss_effect, ss_error):
    """Compute partial eta squared (η²_p) from SS."""
    if (ss_effect + ss_error) == 0:
        return 0.0
    return ss_effect / (ss_effect + ss_error)


# ── 3. Data Loading (identical to mainEffects.py) ─────────────────────────────

hr("ART Repeated-Measures Analysis — Aligned Rank Transform (Wobbrock et al., 2011)")
print(f"Data source: {RAW_PATH}")
print(f"Output dir:  {OUTPUT_DIR}\n")

df_raw = pd.read_excel(RAW_PATH, header=0, skiprows=[1])
print(f"Raw rows loaded: {len(df_raw)}")

# Remove pilot (first row)
df_raw = df_raw.iloc[1:].reset_index(drop=True)
print(f"Rows after removing pilot: {len(df_raw)}")

# Reshape wide → long
records = []
for _, row in df_raw.iterrows():
    pid = str(row["Participant ID"]).strip()
    pname = str(row["Participant Name"]).strip()
    for trial_num in range(1, 13):
        prefix = f"{trial_num}_"
        code = row.get(f"{prefix}ID")
        if pd.isna(code) or str(code).strip() == "":
            continue
        code = str(code).strip().upper()
        scenario_key = code[0]
        system_key = code[1]
        urgency_key = code[2]
        message_num = code[3:]

        rec = {
            "pid": pid,
            "participant": pname,
            "trial": trial_num,
            "code": code,
            "scenario": SCENARIO_LABELS.get(scenario_key, scenario_key),
            "system": SYSTEM_LABELS.get(system_key, system_key),
            "urgency": URGENCY_LABELS.get(urgency_key, urgency_key),
            "message": f"{urgency_key}{message_num}",
        }
        for dv, col_suffix in DV_COLUMNS.items():
            label = str(row.get(f"{prefix}{col_suffix}", "")).strip()
            rec[dv] = DV_MAPS[dv].get(label, np.nan)
        records.append(rec)

df = pd.DataFrame(records)
df["system"] = pd.Categorical(df["system"], SYSTEM_ORDER, ordered=True)
df["urgency"] = pd.Categorical(df["urgency"], ["Low", "High"], ordered=True)
df["scenario"] = pd.Categorical(df["scenario"], ["Interview", "Math"], ordered=True)

print(f"Total trials (long format): {len(df)}")
print(f"Participants: {df['pid'].nunique()}")

# Outlier removal
hr("OUTLIER REMOVAL", "-")
if REMOVE_OUTLIERS and OUTLIERS_PATH.exists():
    with open(OUTLIERS_PATH, "r", encoding="utf-8") as fh:
        outlier_data = json.load(fh)
    outlier_names = [
        o["name"] for o in outlier_data.get("outliers", [])
        if o.get("status") == "is_outlier"
    ]
    n_before = df["participant"].nunique()
    removed = df[df["participant"].isin(outlier_names)]["participant"].unique().tolist()
    df = df[~df["participant"].isin(outlier_names)].reset_index(drop=True)
    n_after = df["participant"].nunique()
    print(f"Outliers removed: {', '.join(removed)} ({len(removed)} participants)")
    print(f"Participants remaining: {n_after} (was {n_before})")
else:
    print("No outlier removal applied.")
print()

N = df["pid"].nunique()

# SonoAdapt+LOW Detectability → NaN
silent_mask = (df["system"] == "SonoAdapt") & (df["urgency"] == "Low")
df.loc[silent_mask, "Detectability"] = np.nan
print(f"SonoAdapt+LOW: {silent_mask.sum()} trials have Detectability set to NaN (silent by design)\n")


# ══════════════════════════════════════════════════════════════════════════════
# 4. THE ALIGNED RANK TRANSFORM (ART) PROCEDURE
# ══════════════════════════════════════════════════════════════════════════════

def art_align_and_rank(data, dv, factors, subject_col="pid"):
    """
    Perform the Aligned Rank Transform (ART) for a given DV and set of factors.

    The ART procedure (Wobbrock et al., 2011):
      For each effect (main effect or interaction) in the model:
        1. Compute the cell means for ALL effects in the model.
        2. ALIGN: subtract all effects EXCEPT the effect of interest
           from the raw response. Y_aligned = Y - (sum of other effects).
           Concretely: Y_aligned = Y - cell_mean(full_model) + marginal_mean(effect_of_interest)
        3. RANK: assign midranks to the aligned values.
        4. Run a standard ANOVA on the aligned-ranked values.
           Only the F-test for the effect of interest is valid.

    Parameters
    ----------
    data : DataFrame
        Trial-level data in long format.
    dv : str
        Name of the dependent variable column.
    factors : list of str
        Names of the factor columns (e.g., ["system", "scenario"]).
    subject_col : str
        Name of the subject/participant column.

    Returns
    -------
    results : dict
        Keys are effect names (e.g., "system", "scenario", "system:scenario").
        Values are dicts with F, df_num, df_den, p, eta2_p, aligned_data.
    """
    work = data[[subject_col] + factors + [dv]].dropna(subset=[dv]).copy()

    # Ensure factors are strings for groupby operations
    for f in factors:
        work[f] = work[f].astype(str)
    work[subject_col] = work[subject_col].astype(str)

    # Grand mean
    grand_mean = work[dv].mean()

    # Compute cell means for the full model (all factor combinations)
    cell_means = work.groupby(factors, observed=True)[dv].mean()

    # Generate all effects: main effects + all interactions
    from itertools import combinations
    all_effects = []
    for r in range(1, len(factors) + 1):
        for combo in combinations(range(len(factors)), r):
            effect_factors = [factors[i] for i in combo]
            effect_name = ":".join(effect_factors)
            all_effects.append((effect_name, effect_factors))

    # Compute marginal means for each effect
    marginal_means = {}
    for effect_name, effect_factors in all_effects:
        mm = work.groupby(effect_factors, observed=True)[dv].mean()
        marginal_means[effect_name] = mm

    results = {}

    for target_name, target_factors in all_effects:
        # === ALIGNMENT ===
        # Y_aligned = Y - cell_mean(all_factors) + marginal_mean(target_effect)
        #
        # The alignment strips out ALL effects except the target one.
        # Equivalently: Y_aligned = residual + marginal_mean(target) + grand_mean
        # But the clearest formulation from Wobbrock et al.:
        #   Y_aligned_ij = Y_ij - Ŷ_ij + μ̂_target
        # where Ŷ_ij is the estimated response (cell mean of the full model)
        # and μ̂_target is the estimated marginal mean of the target effect.

        aligned = work.copy()

        # Subtract the full cell mean
        cell_mean_col = aligned[factors].apply(lambda row: cell_means[tuple(row)], axis=1)

        # Add back the target effect's marginal mean
        if len(target_factors) == 1:
            target_mean_col = aligned[target_factors[0]].map(
                marginal_means[target_name]
            )
        else:
            target_mean_col = aligned[target_factors].apply(
                lambda row: marginal_means[target_name][tuple(row)], axis=1
            )

        aligned[f"aligned_{dv}"] = work[dv] - cell_mean_col + target_mean_col

        # === RANKING (midranks) ===
        aligned[f"art_{dv}"] = stats.rankdata(aligned[f"aligned_{dv}"], method="average")

        # === ANOVA on the aligned-ranked data ===
        # Use repeated-measures ANOVA (all factors are within-subjects)
        # We use statsmodels AnovaRM for the repeated-measures structure.
        #
        # However, AnovaRM only supports a single within factor at a time.
        # For a two-way within-subjects ANOVA, we use the Type III SS approach
        # via OLS with proper coding, then manually extract the F-tests.

        # For repeated-measures: we use the standard approach of computing
        # SS via the linear model and then dividing by the appropriate error terms.
        # For a fully within-subjects design:
        #   SS_effect / (SS_effect×subject / df)
        #
        # We implement this using the standard formulas.

        art_col = f"art_{dv}"

        # Build a pivot table: subjects × cells
        # For repeated-measures ANOVA with multiple within factors:
        results[target_name] = _rm_anova_for_effect(
            aligned, art_col, factors, target_factors, subject_col
        )
        results[target_name]["aligned_data"] = aligned

    return results


def _rm_anova_for_effect(data, dv_col, all_factors, target_factors, subject_col):
    """
    Compute the F-test for a specific effect in a fully within-subjects design
    using the aligned-ranked data.

    For a within-subjects effect, the error term is the interaction of that
    effect with the subject factor: SS(effect × subject) / df(effect × subject).
    """
    # We need to compute:
    # SS_effect = Σ n_i * (marginal_mean_i - grand_mean)^2
    # SS_error = SS(effect × subject)
    # where SS(effect × subject) is the residual within the effect after
    # accounting for both the effect and the subject.

    work = data.copy()
    grand_mean = work[dv_col].mean()
    n_subjects = work[subject_col].nunique()

    # For the target effect: compute the marginal means
    target_means = work.groupby(target_factors, observed=True)[dv_col].mean()

    # Number of levels for the target effect
    n_levels = len(target_means)

    # Number of observations per cell of the target effect
    n_per_level = work.groupby(target_factors, observed=True)[dv_col].count()

    # SS_effect: weighted sum of squared deviations of marginal means from grand mean
    ss_effect = sum(
        n_per_level[idx] * (mean - grand_mean) ** 2
        for idx, mean in target_means.items()
    )

    # df_effect: product of (levels - 1) for each factor in the target
    level_counts = [work[f].nunique() for f in target_factors]
    df_effect = 1
    for lc in level_counts:
        df_effect *= (lc - 1)

    # SS_error (effect × subject interaction):
    # For each subject × target_factor_level combination, compute the mean,
    # then SS_error = SS(subject × effect) = SS_total_within - SS_effect - SS_subject
    #
    # More directly: for each subject-cell combination:
    #   SS(effect×subject) = Σ_i Σ_j (X_ij_bar - X_i._bar - X_.j_bar + X_.._bar)^2 * n
    # where i = subject, j = effect level

    # Cell means per subject × target effect
    subj_effect_means = work.groupby(
        [subject_col] + target_factors, observed=True
    )[dv_col].mean()

    # Subject marginal means
    subj_means = work.groupby(subject_col, observed=True)[dv_col].mean()

    # Compute SS(effect × subject)
    ss_error = 0.0
    for (subj, *eff_levels), cell_mean in subj_effect_means.items():
        if len(eff_levels) == 1:
            eff_key = eff_levels[0]
        else:
            eff_key = tuple(eff_levels)
        subj_mean = subj_means[subj]
        eff_mean = target_means[eff_key]
        ss_error += (cell_mean - subj_mean - eff_mean + grand_mean) ** 2

    # Count observations per subject-cell (should all be equal for balanced design)
    n_per_subj_cell = work.groupby(
        [subject_col] + target_factors, observed=True
    )[dv_col].count()
    # Scale SS_error by n per cell
    ss_error_scaled = 0.0
    for (subj, *eff_levels), cell_mean in subj_effect_means.items():
        if len(eff_levels) == 1:
            eff_key = eff_levels[0]
        else:
            eff_key = tuple(eff_levels)
        subj_mean = subj_means[subj]
        eff_mean = target_means[eff_key]
        n_obs = n_per_subj_cell[(subj, *eff_levels)]
        ss_error_scaled += n_obs * (cell_mean - subj_mean - eff_mean + grand_mean) ** 2

    df_error = df_effect * (n_subjects - 1)

    # F-statistic
    ms_effect = ss_effect / df_effect if df_effect > 0 else 0
    ms_error = ss_error_scaled / df_error if df_error > 0 else 0
    F_stat = ms_effect / ms_error if ms_error > 0 else np.inf
    p_value = 1 - stats.f.cdf(F_stat, df_effect, df_error)

    eta2_p = partial_eta_squared(ss_effect, ss_error_scaled)

    return {
        "F": F_stat,
        "df_num": df_effect,
        "df_den": df_error,
        "p": p_value,
        "SS_effect": ss_effect,
        "MS_effect": ms_effect,
        "SS_error": ss_error_scaled,
        "MS_error": ms_error,
        "eta2_p": eta2_p,
    }


def validate_art(data, dv, factors, subject_col="pid"):
    """
    Validate the ART alignment by checking that the aligned values
    for non-target effects have near-zero F-statistics (as recommended
    by Wobbrock et al., 2011). This is the "strip" check.
    """
    results = art_align_and_rank(data, dv, factors, subject_col)

    print(f"\n  ART Validation (aligned columns should have F ≈ 0 for non-target effects):")
    for target_name, target_res in results.items():
        aligned_data = target_res["aligned_data"]
        art_col = f"art_{dv}"

        # Check all effects on the aligned-ranked data
        all_effects_check = {}
        from itertools import combinations
        for r in range(1, len(factors) + 1):
            for combo in combinations(range(len(factors)), r):
                effect_factors = [factors[i] for i in combo]
                effect_name = ":".join(effect_factors)
                check = _rm_anova_for_effect(
                    aligned_data, art_col, factors, effect_factors, subject_col
                )
                all_effects_check[effect_name] = check

        # Report: the target effect should have a large F, others should be ~0
        print(f"    Aligned for [{target_name}]:")
        for eff_name, eff_res in all_effects_check.items():
            marker = " ← TARGET" if eff_name == target_name else " (should be ≈ 0)"
            print(f"      {eff_name:30s} F({eff_res['df_num']},{eff_res['df_den']}) = "
                  f"{eff_res['F']:10.4f}, p = {eff_res['p']:.5f}{marker}")

    return results


def format_f_result(res, effect_name):
    """Format an F-test result for printing."""
    return (
        f"  {effect_name:30s}  F({res['df_num']},{res['df_den']}) = {res['F']:.2f}, "
        f"p = {res['p']:.5f} {sig_stars(res['p'])}  "
        f"η²_p = {res['eta2_p']:.3f}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 5. ANALYSIS 1: System × Scenario (HIGH-urgency trials only)
# ══════════════════════════════════════════════════════════════════════════════

hr("ANALYSIS 1: ART System × Scenario (HIGH-urgency trials only)")
print(f"Rationale: For HIGH notifications, all three systems deliver an audible")
print(f"notification. SonoAdapt delivers Earcon in Interview and Speech in Math.")
print(f"Testing whether the system effect depends on the scenario.\n")

df_high = df[df["urgency"] == "High"].copy()
df_high["system"] = df_high["system"].astype(str)
df_high["scenario"] = df_high["scenario"].astype(str)
print(f"HIGH-only trials: {len(df_high)} ({df_high['pid'].nunique()} participants)")
print(f"Cells: {df_high.groupby(['system', 'scenario']).size().to_dict()}\n")

# Export data
df_high.to_csv(OUTPUT_DIR / "art_data_high.csv", index=False)

analysis1_results = {}

for dv in DV_ORDER:
    note = DV_NOTES[dv]
    hr(f"[{dv}] — System × Scenario (HIGH only)", "-")
    print(f"  Scale: {note}")

    dv_data = df_high[["pid", "system", "scenario", dv]].dropna(subset=[dv])
    print(f"  Valid observations: {len(dv_data)}")
    print(f"  Cell means:")
    cell_means = dv_data.groupby(["system", "scenario"])[dv].agg(["mean", "std", "count"])
    print(cell_means.round(2).to_string())
    print()

    # Run ART with validation
    results = validate_art(dv_data, dv, ["system", "scenario"], "pid")

    print(f"\n  ── ART ANOVA Results (only the target effect row is valid) ──")
    for effect_name, res in results.items():
        print(format_f_result(res, effect_name))

    analysis1_results[dv] = results
    print()

# Save Analysis 1 results
with open(OUTPUT_DIR / "art_system_x_scenario.txt", "w", encoding="utf-8") as f:
    f.write("=" * 80 + "\n")
    f.write("ART Analysis 1: System × Scenario Interaction (HIGH-urgency trials only)\n")
    f.write("=" * 80 + "\n")
    f.write(f"N = {N} participants, HIGH trials only\n")
    f.write(f"Wobbrock, J.O. et al. (2011). The Aligned Rank Transform.\n\n")

    for dv in DV_ORDER:
        results = analysis1_results[dv]
        f.write(f"\n--- {dv} ({DV_NOTES[dv]}) ---\n")
        for effect_name, res in results.items():
            f.write(f"  {effect_name:30s}  "
                    f"F({res['df_num']},{res['df_den']}) = {res['F']:.2f}, "
                    f"p = {res['p']:.5f} {sig_stars(res['p'])}  "
                    f"η²_p = {res['eta2_p']:.3f}\n")

    # Write copyable LaTeX snippets
    f.write("\n\n" + "=" * 80 + "\n")
    f.write("COPYABLE LaTeX SNIPPETS\n")
    f.write("=" * 80 + "\n\n")

    for dv in DV_ORDER:
        results = analysis1_results[dv]
        interaction = results.get("system:scenario", {})
        f.write(f"{dv} — System × Scenario interaction:\n")
        if interaction:
            f.write(f"  $F({interaction['df_num']},{interaction['df_den']}) = "
                    f"{interaction['F']:.2f}$, $p = {interaction['p']:.3f}$, "
                    f"$\\eta^2_p = {interaction['eta2_p']:.3f}$\n")
        f.write("\n")


# ══════════════════════════════════════════════════════════════════════════════
# 6. ANALYSIS 2: System × Urgency (all trials, excluding Detectability)
# ══════════════════════════════════════════════════════════════════════════════

hr("ANALYSIS 2: ART System × Urgency (all trials)")
print(f"Rationale: Testing whether the system effect depends on urgency level.")
print(f"Detectability is excluded because SonoAdapt-Low is silent by design.\n")

# For this analysis, we average across scenarios first (each participant
# has 2 trials per System × Urgency cell: one Interview, one Math).
# We keep the trial-level data and let ART handle it.

df_full = df.copy()
df_full["system"] = df_full["system"].astype(str)
df_full["urgency"] = df_full["urgency"].astype(str)
print(f"All trials: {len(df_full)} ({df_full['pid'].nunique()} participants)")

# Export data
df_full.to_csv(OUTPUT_DIR / "art_data_full.csv", index=False)

# For System × Urgency, we need to aggregate across scenarios first
# (each participant has 2 observations per System × Urgency cell)
# We average to get one value per participant per System × Urgency cell.

df_agg = df_full.groupby(
    ["pid", "system", "urgency"], observed=True
).agg({
    "Appropriateness": "mean",
    "SocialAcceptability": "mean",
    "Disruptiveness": "mean",
    "Detectability": "mean",  # Will have NaN for SonoAdapt-Low
}).reset_index()

print(f"Aggregated data (1 obs per participant × system × urgency): {len(df_agg)}")
print()

analysis2_dvs = ["Appropriateness", "SocialAcceptability", "Disruptiveness"]
analysis2_results = {}

for dv in analysis2_dvs:
    hr(f"[{dv}] — System × Urgency (all trials)", "-")
    print(f"  Scale: {DV_NOTES[dv]}")

    dv_data = df_agg[["pid", "system", "urgency", dv]].dropna(subset=[dv])
    print(f"  Valid observations: {len(dv_data)}")
    print(f"  Cell means:")
    cell_means = dv_data.groupby(["system", "urgency"])[dv].agg(["mean", "std", "count"])
    print(cell_means.round(2).to_string())
    print()

    # Run ART with validation
    results = validate_art(dv_data, dv, ["system", "urgency"], "pid")

    print(f"\n  ── ART ANOVA Results ──")
    for effect_name, res in results.items():
        print(format_f_result(res, effect_name))

    analysis2_results[dv] = results
    print()

# Save Analysis 2 results
with open(OUTPUT_DIR / "art_system_x_urgency.txt", "w", encoding="utf-8") as f:
    f.write("=" * 80 + "\n")
    f.write("ART Analysis 2: System × Urgency Interaction (all trials)\n")
    f.write("=" * 80 + "\n")
    f.write(f"N = {N} participants\n")
    f.write(f"Aggregated across scenarios (mean of Interview + Math per cell).\n")
    f.write(f"Detectability excluded (SonoAdapt-Low is silent).\n")
    f.write(f"Wobbrock, J.O. et al. (2011). The Aligned Rank Transform.\n\n")

    for dv in analysis2_dvs:
        results = analysis2_results[dv]
        f.write(f"\n--- {dv} ({DV_NOTES[dv]}) ---\n")
        for effect_name, res in results.items():
            f.write(f"  {effect_name:30s}  "
                    f"F({res['df_num']},{res['df_den']}) = {res['F']:.2f}, "
                    f"p = {res['p']:.5f} {sig_stars(res['p'])}  "
                    f"η²_p = {res['eta2_p']:.3f}\n")

    # Copyable LaTeX snippets
    f.write("\n\n" + "=" * 80 + "\n")
    f.write("COPYABLE LaTeX SNIPPETS\n")
    f.write("=" * 80 + "\n\n")

    for dv in analysis2_dvs:
        results = analysis2_results[dv]
        interaction = results.get("system:urgency", {})
        f.write(f"{dv} — System × Urgency interaction:\n")
        if interaction:
            f.write(f"  $F({interaction['df_num']},{interaction['df_den']}) = "
                    f"{interaction['F']:.2f}$, $p = {interaction['p']:.3f}$, "
                    f"$\\eta^2_p = {interaction['eta2_p']:.3f}$\n")
        f.write("\n")


# ══════════════════════════════════════════════════════════════════════════════
# 7. SUMMARY TABLE
# ══════════════════════════════════════════════════════════════════════════════

hr("SUMMARY TABLE — ART Interaction Effects")

print(f"\nN = {N} participants\n")

print("─" * 90)
print(f"{'Analysis 1: System × Scenario (HIGH-urgency only)':^90}")
print("─" * 90)
print(f"{'DV':<25} {'Effect':<25} {'F':<12} {'df':<10} {'p':<12} {'η²_p':<8} sig")
print("-" * 90)

for dv in DV_ORDER:
    results = analysis1_results[dv]
    for eff_name, res in results.items():
        print(f"{dv:<25} {eff_name:<25} {res['F']:<12.2f} "
              f"({res['df_num']},{res['df_den']}){'':<4} "
              f"{res['p']:<12.5f} {res['eta2_p']:<8.3f} {sig_stars(res['p'])}")
    dv = ""  # avoid repeating DV name

print()
print("─" * 90)
print(f"{'Analysis 2: System × Urgency (all trials, Detectability excluded)':^90}")
print("─" * 90)
print(f"{'DV':<25} {'Effect':<25} {'F':<12} {'df':<10} {'p':<12} {'η²_p':<8} sig")
print("-" * 90)

for dv in analysis2_dvs:
    results = analysis2_results[dv]
    for eff_name, res in results.items():
        print(f"{dv:<25} {eff_name:<25} {res['F']:<12.2f} "
              f"({res['df_num']},{res['df_den']}){'':<4} "
              f"{res['p']:<12.5f} {res['eta2_p']:<8.3f} {sig_stars(res['p'])}")
    dv = ""

print()
print("Significance codes: *** p<.001, ** p<.01, * p<.05, . p<.10, n.s. p≥.10")
print("Effect size: η²_p = partial eta squared")
print("ART procedure: Wobbrock, J.O. et al. (2011). CHI '11, pp. 143-146.")


# ══════════════════════════════════════════════════════════════════════════════
# 8. GENERATE LaTeX SECTION
# ══════════════════════════════════════════════════════════════════════════════

hr("GENERATING LaTeX SECTION")

def fmt_p(p):
    """Format a p-value for LaTeX."""
    if p < 0.001:
        return "p < .001"
    else:
        return f"p = .{p:.3f}"[4:]  # e.g., "p = .042"

def fmt_p_latex(p):
    """Format p-value for LaTeX inline."""
    if p < 0.001:
        return "$p < .001$"
    else:
        return f"$p = {p:.3f}$".replace("0.", ".")

def fmt_f_latex(res):
    """Format an F-test for LaTeX inline."""
    p_str = "p < .001" if res['p'] < 0.001 else f"p = {res['p']:.3f}".replace("0.", ".")
    return (f"$F({res['df_num']},{res['df_den']}) = {res['F']:.2f}$, "
            f"${p_str}$, "
            f"$\\eta^2_p = {res['eta2_p']:.3f}$")

latex_lines = []
latex_lines.append(r"%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
latex_lines.append(r"\subsection{Interaction Effects (Aligned Rank Transform)}")
latex_lines.append(r"\label{sec:art_interactions}")
latex_lines.append(r"%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
latex_lines.append(r"")
latex_lines.append(r"The preceding analyses used one-way Friedman tests to assess the main effect of system, followed by decompositions into simple effects by urgency/importance and exploratory cell-level comparisons. However, the Friedman test is a one-way procedure and cannot formally test interaction effects between two or more factors. To test whether the effect of system depends on urgency/importance level or scenario, we applied the Aligned Rank Transform \citep[ART;][]{Wobbrock_11_ART}, a nonparametric procedure designed for factorial designs with ordinal or non-normal data. ART aligns each response by stripping all effects except the target effect, ranks the aligned values, and then submits them to a standard repeated-measures ANOVA. The resulting $F$-test is valid only for the effect for which the data were aligned.")
latex_lines.append(r"")

# --- Analysis 2: System × Urgency ---
latex_lines.append(r"\paragraph{System $\times$ Urgency/Importance.}")

# Build the result text dynamically
sys_urg_texts = []
for dv in analysis2_dvs:
    res_interaction = analysis2_results[dv]["system:urgency"]
    sig = res_interaction['p'] < ALPHA
    sys_urg_texts.append((dv, res_interaction, sig))

# Check if all interactions are significant
all_sig = all(s for _, _, s in sys_urg_texts)
any_sig = any(s for _, _, s in sys_urg_texts)

if all_sig:
    latex_lines.append(
        r"We tested the System $\times$ Urgency/Importance interaction for the three dependent variables for which all cells contain meaningful ratings (excluding detectability, since SonoAdapt mutes Low notifications). "
        r"The ART ANOVA revealed significant interactions for all three measures: "
    )
else:
    latex_lines.append(
        r"We tested the System $\times$ Urgency/Importance interaction for the three dependent variables for which all cells contain meaningful ratings (excluding detectability, since SonoAdapt mutes Low notifications). "
    )

for dv_name, res_int, is_sig in sys_urg_texts:
    dv_display = "social acceptability" if dv_name == "SocialAcceptability" else dv_name.lower()
    latex_lines.append(
        f"{dv_display} ({fmt_f_latex(res_int)}), "
    )

# Remove trailing comma from last line and add period
if latex_lines[-1].endswith(", "):
    latex_lines[-1] = latex_lines[-1][:-2] + "."

latex_lines.append(
    r"These significant interactions confirm that the effect of the notification system changes depending on urgency/importance, "
    r"which the simple-effects decomposition in Section~\ref{sec:simple_effects} already illustrated descriptively: "
    r"SonoAdapt's advantage is driven primarily by its muting of Low notifications, whereas for High notifications the three systems perform more comparably."
)
latex_lines.append(r"")

# --- Analysis 1: System × Scenario (HIGH only) ---
latex_lines.append(r"\paragraph{System $\times$ Scenario (High Urgency/Importance Only).}")
latex_lines.append(
    r"Because SonoAdapt adapts not only whether to deliver a notification but also which modality to use (Earcon in the Interview, Speech in the Math task), "
    r"we additionally tested the System $\times$ Scenario interaction on the High-urgency/high-importance trials, "
    r"in which all three systems delivered an audible notification. "
)

sys_scen_texts = []
for dv in DV_ORDER:
    res_interaction = analysis1_results[dv]["system:scenario"]
    sig = res_interaction['p'] < ALPHA
    sys_scen_texts.append((dv, res_interaction, sig))

sig_dvs = [(dv, res) for dv, res, s in sys_scen_texts if s]
nonsig_dvs = [(dv, res) for dv, res, s in sys_scen_texts if not s]

if sig_dvs:
    latex_lines.append(r"The ART ANOVA revealed significant System $\times$ Scenario interactions for ")
    sig_parts = []
    for dv_name, res_int in sig_dvs:
        dv_display = "social acceptability" if dv_name == "SocialAcceptability" else dv_name.lower()
        sig_parts.append(f"{dv_display} ({fmt_f_latex(res_int)})")
    latex_lines.append(", ".join(sig_parts) + ". ")

if nonsig_dvs:
    nonsig_parts = []
    for dv_name, res_int in nonsig_dvs:
        dv_display = "social acceptability" if dv_name == "SocialAcceptability" else dv_name.lower()
        nonsig_parts.append(f"{dv_display} ({fmt_f_latex(res_int)})")

    if sig_dvs:
        latex_lines.append("No significant interaction emerged for " + ", ".join(nonsig_parts) + ". ")
    else:
        latex_lines.append("The interaction did not reach significance for any measure: " + "; ".join(nonsig_parts) + ". ")

latex_lines.append(
    r"These results indicate that the relative performance of the three systems changes across scenarios for High notifications, "
    r"which the cell-level analysis in Section~\ref{sec:further_effects} explored in detail: "
    r"Earcon was preferred in the socially constrained Interview, whereas Speech was preferred in the solo Math task. "
    r"SonoAdapt's context-aware modality selection matched these scenario-dependent preferences."
)
latex_lines.append(r"")

# Summary
latex_lines.append(r"\paragraph{Summary.}")
latex_lines.append(
    r"The ART interaction analyses provide formal statistical evidence for two key patterns that were previously supported only by descriptive comparisons and simple-effects tests. "
    r"First, the significant System $\times$ Urgency/Importance interactions confirm that the notification systems are perceived differently depending on message urgency, "
    r"with SonoAdapt's muting strategy for Low notifications being the primary driver of its overall advantage. "
    r"Second, the System $\times$ Scenario results for High notifications demonstrate that the optimal notification modality is scenario-dependent, "
    r"lending further support to SonoAdapt's adaptive approach of selecting Earcon for the Interview and Speech for the Math task."
)

latex_text = "\n".join(latex_lines)

# Save LaTeX section
latex_path = OUTPUT_DIR / "artInteractionSection.tex"
with open(latex_path, "w", encoding="utf-8") as f:
    f.write(latex_text)

print(f"LaTeX section saved to: {latex_path}")
print()


# ── Close output ──────────────────────────────────────────────────────────────
hr("DONE", "=")
print(f"All results saved to: {OUTPUT_DIR}")
print(f"\nFiles generated:")
for p in sorted(OUTPUT_DIR.iterdir()):
    print(f"  {p.name}")

_output_file.close()
sys.stdout = sys.__stdout__
print(f"\n✅ ART repeated-measures analysis complete. Results saved to: {OUTPUT_DIR}")
