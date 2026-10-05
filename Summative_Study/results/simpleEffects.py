"""
simpleEffects.py – Simple-effects analysis (System within each Urgency level).
================================================================================

This script performs the same Friedman + Holm-corrected Wilcoxon analysis as
mainEffects.py, but separately for:
  (1) LOW-urgency/importance notifications only
  (2) HIGH-urgency/importance notifications only

These are called "simple effects of System at each level of Urgency" and are
a standard follow-up to the main-effect analysis. They reveal whether the
system differences are driven by LOW messages, HIGH messages, or both.

Special handling:
  LOW urgency:
    - SonoAdapt mutes LOW notifications (silent by design).
    - Detectability is N/A for SonoAdapt-LOW → 3-system Friedman runs on 3 DVs only.
    - For Detectability-LOW, we report a 2-system Wilcoxon (Earcon vs Speech only).

  HIGH urgency:
    - All 3 systems produce audible notifications → full 3-system Friedman on all 4 DVs.

Outputs saved to simpleEffectsPlotsAndData/:
  - simpleEffectsResults.txt          – Full statistical report
  - participantMeans_LOW.csv          – Participant-level means for LOW
  - participantMeans_HIGH.csv         – Participant-level means for HIGH
  - fig_simpleEffects_LOW_*.png/pdf   – Boxplots for LOW urgency
  - fig_simpleEffects_HIGH_*.png/pdf  – Boxplots for HIGH urgency

Data source: raw.xlsx (with outlier removal via potential_outliers.json)
"""

import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# ── 0. Paths ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
RAW_PATH = SCRIPT_DIR / "raw.xlsx"
OUTLIERS_PATH = SCRIPT_DIR / "potential_outliers.json"
OUTPUT_DIR = SCRIPT_DIR / "simpleEffectsPlotsAndData"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_TXT = OUTPUT_DIR / "simpleEffectsResults.txt"

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
ALPHA_BONF = 0.025  # per a-priori power analysis

SYSTEM_LABELS = {"E": "Earcon", "S": "Speech", "X": "SonoAdapt"}
URGENCY_LABELS = {"L": "Low", "H": "High"}
SCENARIO_LABELS = {"I": "Interview", "M": "Math"}
SYSTEM_ORDER = ["Earcon", "Speech", "SonoAdapt"]

# Likert label → numeric mappings
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

DV_ORDER_FULL = ["Appropriateness", "SocialAcceptability", "Detectability", "Disruptiveness"]
DV_ORDER_NO_DETECT = ["Appropriateness", "SocialAcceptability", "Disruptiveness"]

DV_PLOT_TITLES = {
    "Appropriateness": "Appropriateness",
    "SocialAcceptability": "Social Acceptability",
    "Detectability": "Detectability",
    "Disruptiveness": "Disruptiveness\n(lower = better)",
}


# ── 2. Data Loading & Preprocessing ──────────────────────────────────────────
def hr(title="", char="=", width=88):
    if title:
        print(f"\n{char * width}")
        print(title)
        print(char * width)
    else:
        print(char * width)


hr("SonoAdapt Summative Study — Simple-Effects Analysis (System × Urgency)")
print(f"Data source: {RAW_PATH}")
print(f"Output dir:  {OUTPUT_DIR}\n")

df_raw = pd.read_excel(RAW_PATH, header=0, skiprows=[1])
print(f"Raw rows loaded: {len(df_raw)}")

# Remove pilot (first row)
df_raw = df_raw.iloc[1:].reset_index(drop=True)
print(f"Rows after removing pilot: {len(df_raw)}")

# ── 3. Reshape wide → long ───────────────────────────────────────────────────
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
        # Map Likert labels → numeric
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

# ── 4. Outlier Removal ───────────────────────────────────────────────────────
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

# ── 5. SonoAdapt+LOW Detectability → NaN ─────────────────────────────────────
silent_mask = (df["system"] == "SonoAdapt") & (df["urgency"] == "Low")
df.loc[silent_mask, "Detectability"] = np.nan
print(f"SonoAdapt+LOW: {silent_mask.sum()} trials have Detectability set to NaN (silent by design)")
print()


# ── 6. Statistical Helpers ────────────────────────────────────────────────────

def holm_correction(pvals):
    """Holm-Bonferroni step-down adjusted p-values."""
    p = np.asarray(pvals, float)
    order = np.argsort(p)
    m = len(p)
    adj = np.empty(m)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * p[idx])
        adj[idx] = min(1.0, running)
    return adj


def kendalls_w(mat):
    """Kendall's W for an n_subjects × k_conditions matrix (Friedman effect size)."""
    n, k = mat.shape
    chi2, _ = stats.friedmanchisquare(*[mat[:, j] for j in range(k)])
    return chi2 / (n * (k - 1))


def wilcoxon_pair(a, b):
    """Wilcoxon signed-rank test with rank-biserial and z-based effect sizes."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = a - b
    nz = d[d != 0]
    n_nz = len(nz)
    if n_nz == 0:
        return dict(W=np.nan, p=1.0, z=0.0, r=0.0, rb=0.0, n_nonzero=0)
    try:
        res = stats.wilcoxon(a, b, zero_method="wilcox", method="auto")
    except TypeError:
        res = stats.wilcoxon(a, b, zero_method="wilcox")
    W, p = float(res.statistic), float(res.pvalue)
    ranks = stats.rankdata(np.abs(nz))
    t_pos = ranks[nz > 0].sum()
    t_neg = ranks[nz < 0].sum()
    rb = (t_pos - t_neg) / (t_pos + t_neg) if (t_pos + t_neg) > 0 else 0.0
    mu = n_nz * (n_nz + 1) / 4.0
    sd = np.sqrt(n_nz * (n_nz + 1) * (2 * n_nz + 1) / 24.0)
    z = (min(t_pos, t_neg) - mu) / sd if sd > 0 else 0.0
    r = abs(z) / np.sqrt(len(a))
    return dict(W=W, p=p, z=z, r=r, rb=rb, n_nonzero=n_nz)


def cohen_dz(a, b):
    """Cohen's d_z for paired data."""
    d = np.asarray(a, float) - np.asarray(b, float)
    sd = d.std(ddof=1)
    return d.mean() / sd if sd > 0 else np.nan


def sig_stars(p, alpha=ALPHA):
    if p < 0.001: return "***"
    if p < 0.01:  return "**"
    if p < alpha:  return "*"
    if p < 0.10:  return "."
    return "n.s."


def wide_by_system(data, dv):
    """Create participant × system matrix, averaging over scenarios."""
    w = data.pivot_table(index="pid", columns="system", values=dv,
                         aggfunc="mean", observed=True)
    return w.reindex(columns=SYSTEM_ORDER)


# ── 7. Analysis Functions ─────────────────────────────────────────────────────

def run_friedman_analysis(data, dv, note, label=""):
    """Run 3-system Friedman omnibus + Holm-corrected pairwise Wilcoxon for one DV."""
    title = f"[{dv}]  ({note})"
    if label:
        title = f"{label}: {title}"
    print(f"\n{'-' * 88}")
    print(title)
    print(f"{'-' * 88}")

    # --- Trial-level descriptives ---
    print("\nTrial-level descriptives:")
    trial_desc = data.groupby("system", observed=True)[dv].agg(
        n="count", M="mean", SD="std", Mdn="median",
        Q1=lambda s: s.quantile(0.25), Q3=lambda s: s.quantile(0.75),
        Min="min", Max="max"
    ).reindex(SYSTEM_ORDER).round(2)
    print(trial_desc.to_string())

    # --- Participant-level aggregation ---
    w = wide_by_system(data, dv)
    mat = w.dropna().to_numpy(float)
    n_valid = len(mat)

    print(f"\nParticipant-level means (unit of analysis, N = {n_valid}):")
    part_desc = pd.DataFrame({
        "M": w.mean(), "SD": w.std(ddof=1), "Mdn": w.median(),
        "Q1": w.quantile(0.25), "Q3": w.quantile(0.75),
        "Min": w.min(), "Max": w.max()
    }).round(2)
    print(part_desc.to_string())

    # --- Friedman omnibus test ---
    cols = [mat[:, j] for j in range(mat.shape[1])]
    chi2, p_fr = stats.friedmanchisquare(*cols)
    W = kendalls_w(mat)
    print(f"\nFriedman omnibus test:")
    print(f"  χ²({mat.shape[1]-1}) = {chi2:.2f},  p = {p_fr:.5f}  {sig_stars(p_fr)}")
    print(f"  Kendall's W = {W:.3f}")

    # --- Post-hoc pairwise Wilcoxon ---
    pairs = [("Earcon", "Speech"), ("Earcon", "SonoAdapt"), ("Speech", "SonoAdapt")]
    results = [wilcoxon_pair(w[a].dropna(), w[b].dropna()) for a, b in pairs]
    p_adj = holm_correction([x["p"] for x in results])

    print(f"\nPost-hoc: Wilcoxon signed-rank tests, Holm-Bonferroni corrected ({len(pairs)} comparisons):")
    print(f"  {'Comparison':<26} {'ΔM':>7} {'W':>7} {'p':>9} {'p_Holm':>9}"
          f" {'r_rb':>7} {'r':>6} {'d_z':>6}   sig")
    for (a, b), x, pa in zip(pairs, results, p_adj):
        diff = w[a].mean() - w[b].mean()
        bonf_flag = "  [<.025]" if pa < ALPHA_BONF else ""
        print(f"  {a + ' vs ' + b:<26} {diff:>7.2f} {x['W']:>7.1f}"
              f" {x['p']:>9.5f} {pa:>9.5f}"
              f" {x['rb']:>7.2f} {x['r']:>6.2f} {cohen_dz(w[a].dropna(), w[b].dropna()):>6.2f}"
              f"   {sig_stars(pa)}{bonf_flag}")
    print(f"  (r_rb = matched-pairs rank-biserial; r = |z|/√N; d_z = Cohen's d for paired data)")

    return w, chi2, p_fr, W, results, p_adj


def run_two_system_wilcoxon(data, dv, sys_a, sys_b, note, label=""):
    """Run a 2-system Wilcoxon signed-rank test (no Friedman needed for k=2)."""
    title = f"[{dv}]  ({note})"
    if label:
        title = f"{label}: {title}"
    print(f"\n{'-' * 88}")
    print(title)
    print(f"  NOTE: Only {sys_a} vs {sys_b} (SonoAdapt is muted → N/A)")
    print(f"{'-' * 88}")

    # --- Trial-level descriptives ---
    subset = data[data["system"].isin([sys_a, sys_b])]
    print("\nTrial-level descriptives:")
    trial_desc = subset.groupby("system", observed=True)[dv].agg(
        n="count", M="mean", SD="std", Mdn="median",
        Q1=lambda s: s.quantile(0.25), Q3=lambda s: s.quantile(0.75),
        Min="min", Max="max"
    ).reindex([sys_a, sys_b]).round(2)
    print(trial_desc.to_string())

    # --- Participant-level aggregation ---
    w = subset.pivot_table(index="pid", columns="system", values=dv,
                           aggfunc="mean", observed=True)
    w = w.reindex(columns=[sys_a, sys_b])
    valid = w.dropna()

    print(f"\nParticipant-level means (N = {len(valid)}):")
    part_desc = pd.DataFrame({
        "M": w.mean(), "SD": w.std(ddof=1), "Mdn": w.median(),
        "Q1": w.quantile(0.25), "Q3": w.quantile(0.75),
        "Min": w.min(), "Max": w.max()
    }).round(2)
    print(part_desc.to_string())

    # --- Wilcoxon signed-rank test ---
    res = wilcoxon_pair(valid[sys_a], valid[sys_b])
    dz = cohen_dz(valid[sys_a], valid[sys_b])
    diff = valid[sys_a].mean() - valid[sys_b].mean()

    print(f"\nWilcoxon signed-rank test:")
    print(f"  {sys_a} vs {sys_b}:  ΔM = {diff:.2f},  W = {res['W']:.1f},"
          f"  p = {res['p']:.5f}  {sig_stars(res['p'])}")
    print(f"  r_rb = {res['rb']:.2f},  r = {res['r']:.2f},  d_z = {dz:.2f}")

    return w, res


# ── 8. Split Data by Urgency ─────────────────────────────────────────────────
df_low = df[df["urgency"] == "Low"].copy()
df_high = df[df["urgency"] == "High"].copy()

print(f"Trials after split: LOW = {len(df_low)}, HIGH = {len(df_high)}")
print(f"  LOW participants:  {df_low['pid'].nunique()}")
print(f"  HIGH participants: {df_high['pid'].nunique()}")
print()


# ══════════════════════════════════════════════════════════════════════════════
# ── 9. LOW URGENCY ANALYSIS ──────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
hr("SIMPLE EFFECTS — LOW URGENCY/IMPORTANCE NOTIFICATIONS")
print(f"N = {N} participants.  Each participant's score per system is the mean")
print(f"of their LOW-urgency trials for that system (2 trials: Interview + Math).")
print(f"\nSonoAdapt mutes LOW notifications → Detectability is N/A for SonoAdapt.\n")

low_means = {}  # for CSV export

# --- Appropriateness, SocialAcceptability, Disruptiveness: full 3-system Friedman ---
for dv in DV_ORDER_NO_DETECT:
    w, *_ = run_friedman_analysis(df_low, dv, DV_NOTES[dv], label="LOW")
    low_means[dv] = w

# --- Detectability-LOW: 2-system Wilcoxon (Earcon vs Speech only) ---
w_detect_low, _ = run_two_system_wilcoxon(
    df_low, "Detectability", "Earcon", "Speech",
    DV_NOTES["Detectability"], label="LOW"
)
low_means["Detectability"] = w_detect_low

# --- Export participant means for LOW ---
csv_frames = []
for dv in DV_ORDER_FULL:
    w = low_means[dv]
    melted = w.reset_index().melt(id_vars="pid", var_name="system", value_name="mean_rating")
    melted["DV"] = dv
    csv_frames.append(melted)

csv_low = pd.concat(csv_frames, ignore_index=True)
csv_low = csv_low[["pid", "DV", "system", "mean_rating"]]
csv_path_low = OUTPUT_DIR / "participantMeans_LOW.csv"
csv_low.to_csv(csv_path_low, index=False)
print(f"\nSaved: {csv_path_low}")


# ══════════════════════════════════════════════════════════════════════════════
# ── 10. HIGH URGENCY ANALYSIS ────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
hr("SIMPLE EFFECTS — HIGH URGENCY/IMPORTANCE NOTIFICATIONS")
print(f"N = {N} participants.  Each participant's score per system is the mean")
print(f"of their HIGH-urgency trials for that system (2 trials: Interview + Math).")
print(f"\nAll systems deliver audible notifications for HIGH → all 4 DVs valid.\n")

high_means = {}

for dv in DV_ORDER_FULL:
    w, *_ = run_friedman_analysis(df_high, dv, DV_NOTES[dv], label="HIGH")
    high_means[dv] = w

# --- Export participant means for HIGH ---
csv_frames = []
for dv in DV_ORDER_FULL:
    w = high_means[dv]
    melted = w.reset_index().melt(id_vars="pid", var_name="system", value_name="mean_rating")
    melted["DV"] = dv
    csv_frames.append(melted)

csv_high = pd.concat(csv_frames, ignore_index=True)
csv_high = csv_high[["pid", "DV", "system", "mean_rating"]]
csv_path_high = OUTPUT_DIR / "participantMeans_HIGH.csv"
csv_high.to_csv(csv_path_high, index=False)
print(f"\nSaved: {csv_path_high}")


# ══════════════════════════════════════════════════════════════════════════════
# ── 11. SUMMARY TABLES ───────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def print_summary_table(urgency_label, means_dict, dv_list):
    """Print omnibus + pairwise summary tables for one urgency level."""
    hr(f"SUMMARY TABLE — {urgency_label} URGENCY")
    print(f"\nN = {N} participants (after outlier removal)")
    print(f"\n{'DV':<22} {'Earcon':>12} {'Speech':>12} {'SonoAdapt':>12}"
          f"   {'Friedman χ²':>12} {'p':>10} {'W':>6}   sig")
    print("-" * 100)

    for dv in dv_list:
        w = means_dict[dv]
        systems_available = [s for s in SYSTEM_ORDER if s in w.columns and w[s].notna().any()]
        if len(systems_available) < 3:
            # 2-system only (Detectability-LOW)
            means = []
            for s in SYSTEM_ORDER:
                if s in w.columns and w[s].notna().any():
                    means.append(f"{w[s].mean():.2f} ({w[s].std(ddof=1):.2f})")
                else:
                    means.append("N/A (muted)")
            print(f"{dv:<22} {means[0]:>12} {means[1]:>12} {means[2]:>12}"
                  f"   {'(2-sys Wilc.)':>12} {'':>10} {'':>6}   —")
        else:
            mat = w.dropna().to_numpy(float)
            chi2, p_fr = stats.friedmanchisquare(*[mat[:, j] for j in range(mat.shape[1])])
            W = kendalls_w(mat)
            means = [f"{w[s].mean():.2f} ({w[s].std(ddof=1):.2f})" for s in SYSTEM_ORDER]
            print(f"{dv:<22} {means[0]:>12} {means[1]:>12} {means[2]:>12}"
                  f"   {chi2:>12.2f} {p_fr:>10.5f} {W:>6.3f}   {sig_stars(p_fr)}")

    print()
    print("Values are M (SD) at the participant level.")

    # Pairwise table
    print()
    hr(f"PAIRWISE SUMMARY — {urgency_label} URGENCY")
    print(f"\n{'DV':<22} {'Comparison':<26} {'ΔM':>7} {'p_Holm':>10} {'r_rb':>7} {'d_z':>6}   sig")
    print("-" * 95)

    for dv in dv_list:
        w = means_dict[dv]
        systems_available = [s for s in SYSTEM_ORDER if s in w.columns and w[s].notna().any()]

        if len(systems_available) < 3:
            # 2-system comparison
            a, b = systems_available[0], systems_available[1]
            res = wilcoxon_pair(w[a].dropna(), w[b].dropna())
            diff = w[a].mean() - w[b].mean()
            dz = cohen_dz(w[a].dropna(), w[b].dropna())
            print(f"{dv:<22} {a + ' vs ' + b:<26} {diff:>7.2f} {res['p']:>10.5f}"
                  f" {res['rb']:>7.2f} {dz:>6.2f}   {sig_stars(res['p'])}")
        else:
            pairs = [("Earcon", "Speech"), ("Earcon", "SonoAdapt"), ("Speech", "SonoAdapt")]
            results = [wilcoxon_pair(w[a].dropna(), w[b].dropna()) for a, b in pairs]
            p_adj = holm_correction([x["p"] for x in results])
            for (a, b), x, pa in zip(pairs, results, p_adj):
                diff = w[a].mean() - w[b].mean()
                dz = cohen_dz(w[a].dropna(), w[b].dropna())
                print(f"{dv:<22} {a + ' vs ' + b:<26} {diff:>7.2f} {pa:>10.5f}"
                      f" {x['rb']:>7.2f} {dz:>6.2f}   {sig_stars(pa)}")
        if dv != dv_list[-1]:
            print()


print_summary_table("LOW", low_means, DV_ORDER_FULL)
print_summary_table("HIGH", high_means, DV_ORDER_FULL)


# ══════════════════════════════════════════════════════════════════════════════
# ── 12. PLOTS ─────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
hr("GENERATING PLOTS")

_BASE_COLORS = {"Earcon": "#FFC300", "Speech": "#694487", "SonoAdapt": "#56C959",
                "AudioAdapt": "#56C959"}
BOX_WIDTH = 0.75
Y_STEP = 0.3

def _blend(hex_color, alpha):
    """Blend hex_color toward white by (1-alpha)."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return "#{:02X}{:02X}{:02X}".format(
        int(r * alpha + 255 * (1 - alpha)),
        int(g * alpha + 255 * (1 - alpha)),
        int(b * alpha + 255 * (1 - alpha)),
    )

def _urgency_colors(system_name, urgency_label):
    """Return color dict with 40% opacity for LOW, 70% for HIGH."""
    alpha = 0.40 if urgency_label == "LOW" else 0.70
    return {
        "Earcon": _blend(_BASE_COLORS["Earcon"], alpha),
        "Speech": _blend(_BASE_COLORS["Speech"], alpha),
        system_name: _blend(_BASE_COLORS.get(system_name, "#56C959"), alpha),
    }


def get_significant_pairs_3sys(w, system_names):
    """Return Holm-corrected significant Wilcoxon pairs for 3-system Friedman."""
    mat = w.dropna().to_numpy(float)
    if mat.shape[0] < 3:
        return []
    chi2, p_fr = stats.friedmanchisquare(*[mat[:, j] for j in range(mat.shape[1])])
    if p_fr >= ALPHA:
        return []
    orig_pairs = [("Earcon", "Speech"), ("Earcon", "SonoAdapt"), ("Speech", "SonoAdapt")]
    display_pairs = [(system_names[0], system_names[1]),
                     (system_names[0], system_names[2]),
                     (system_names[1], system_names[2])]
    results = [wilcoxon_pair(w[a].dropna(), w[b].dropna()) for a, b in orig_pairs]
    padj = holm_correction([r["p"] for r in results])
    marked = []
    for (a, b), pa in zip(display_pairs, padj):
        ast = sig_stars(pa, ALPHA)
        if ast not in ("n.s.", "."):
            marked.append((a, b, ast))
    idx = {s: i for i, s in enumerate(system_names)}
    marked.sort(key=lambda t: abs(idx[t[0]] - idx[t[1]]))
    return marked


def hue_offsets(n=3, width=BOX_WIDTH):
    return [-width / 2 + width / (2 * n) + k * (width / n) for k in range(n)]


def make_simple_effect_plot(urgency_label, dv_list, means_dict, system_name, suffix,
                            df_source):
    """Generate a boxplot for one urgency level."""
    from matplotlib.patches import Rectangle

    system_names = ["Earcon", "Speech", system_name]
    colors = _urgency_colors(system_name, urgency_label)

    # Build long-format data
    rows = []
    for dv in dv_list:
        w = means_dict[dv]
        for s_orig, s_display in zip(SYSTEM_ORDER, system_names):
            if s_orig not in w.columns or w[s_orig].isna().all():
                continue
            for _, v in w[s_orig].items():
                if pd.notna(v):
                    rows.append({"scale": DV_PLOT_TITLES[dv], "system": s_display, "rating": v})

    plot_data = pd.DataFrame(rows)
    plot_data["scale"] = pd.Categorical(
        plot_data["scale"], [DV_PLOT_TITLES[d] for d in dv_list], True
    )
    plot_data["system"] = pd.Categorical(
        plot_data["system"], system_names, ordered=True
    )

    fig_width = 12 if len(dv_list) == 4 else 9.5
    fig, ax = plt.subplots(figsize=(fig_width, 5.5))
    sns.boxplot(
        data=plot_data, x="scale", y="rating", hue="system",
        palette=colors, width=BOX_WIDTH, whis=(0, 100), ax=ax,
        saturation=1.0,
    )

    # Fix zero-IQR boxes: draw a colored rectangle so the color is visible
    offs_list = hue_offsets()
    idx_map = {s: i for i, s in enumerate(system_names)}
    sub_width = BOX_WIDTH / len(system_names)
    for gi, dv in enumerate(dv_list):
        w = means_dict[dv]
        for s_orig, s_display in zip(SYSTEM_ORDER, system_names):
            if s_orig not in w.columns or w[s_orig].isna().all():
                continue
            vals = w[s_orig].dropna().values
            q1, q3 = np.percentile(vals, [25, 75])
            if (q3 - q1) < 0.18:
                median_val = np.median(vals)
                x_center = gi + offs_list[idx_map[s_display]]
                rect_h = 0.20
                rect = Rectangle(
                    (x_center - sub_width / 2, median_val - rect_h / 2),
                    sub_width, rect_h,
                    facecolor=colors[s_display], edgecolor="black",
                    linewidth=1.2, zorder=3,
                )
                ax.add_patch(rect)

    # M(SD) annotations above each box
    for gi, dv in enumerate(dv_list):
        w = means_dict[dv]
        for s_orig, s_display in zip(SYSTEM_ORDER, system_names):
            if s_orig in w.columns and w[s_orig].notna().any():
                m = w[s_orig].mean()
                sd = w[s_orig].std(ddof=1)
                x_pos = gi + offs_list[idx_map[s_display]]
                ax.text(x_pos, 7.2, f"M={m:.2f}\nSD={sd:.2f}",
                        ha="center", fontsize="small",
                        color="black", fontweight="bold",
                        fontfamily="Arial")

    # Significance bars
    y_start = 8.1

    for gi, dv in enumerate(dv_list):
        y = y_start
        w = means_dict[dv]
        systems_available = [s for s in SYSTEM_ORDER if s in w.columns and w[s].notna().any()]
        if len(systems_available) >= 3:
            for a, b, asterisks in get_significant_pairs_3sys(w, system_names):
                x1, x2 = gi + offs_list[idx_map[a]], gi + offs_list[idx_map[b]]
                bar_height = y
                bar_tips = bar_height - (Y_STEP * 0.2)
                ax.plot([x1, x1, x2, x2], [bar_tips, bar_height, bar_height, bar_tips],
                        lw=1.5, c="black")
                ax.text((x1 + x2) / 2, bar_height, asterisks, ha="center", va="bottom",
                        color="black", fontsize=12)
                y += Y_STEP * 1.5

    ax.set_ylim(0.5, y_start + Y_STEP * 1.5 * 3 + 0.8)
    urgency_title = "Low" if urgency_label == "LOW" else "High"
    ax.set_title(f"Simple Effect of the System: {urgency_title} Urgency/Importance",
                 fontsize=13, fontweight="regular")
    ax.set_xlabel("")
    ax.set_ylabel("Rating (1–7)", fontsize=12)
    ax.set_yticks(range(1, 8))
    ax.legend(title=None, fontsize=11, loc="lower center", ncol=3,
              framealpha=0.9, edgecolor="lightgray")
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()

    for ext in ("pdf", "png"):
        fig.savefig(OUTPUT_DIR / f"fig_simpleEffects_{urgency_label}_{suffix}.{ext}",
                    dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: fig_simpleEffects_{urgency_label}_{suffix}.png / .pdf")


matplotlib.rcdefaults()
plt.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42})

# LOW urgency plots: 3 DVs only (no Detectability, since SonoAdapt is muted)
for sname, suffix in [("SonoAdapt", "SonoAdapt"), ("AudioAdapt", "AudioAdapt")]:
    make_simple_effect_plot("LOW", DV_ORDER_NO_DETECT, low_means, sname, suffix, df_low)

# HIGH urgency plots: 4 DVs and 3 DVs variants
for sname, suffix in [("SonoAdapt", "SonoAdapt"), ("AudioAdapt", "AudioAdapt")]:
    make_simple_effect_plot("HIGH", DV_ORDER_FULL, high_means, sname, f"{suffix}_4DV", df_high)
    make_simple_effect_plot("HIGH", DV_ORDER_NO_DETECT, high_means, sname, f"{suffix}_3DV", df_high)

print()


# ══════════════════════════════════════════════════════════════════════════════
# ── 13. CROSS-URGENCY COMPARISON TABLE ────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
hr("CROSS-URGENCY COMPARISON — System means by urgency level")
print(f"\n{'':15} {'—— LOW ——':>36}    {'—— HIGH ——':>36}")
print(f"{'DV':<22} {'Earcon':>12} {'Speech':>12} {'SonoAdapt':>12}"
      f"    {'Earcon':>12} {'Speech':>12} {'SonoAdapt':>12}")
print("-" * 110)

for dv in DV_ORDER_FULL:
    low_vals = []
    for s in SYSTEM_ORDER:
        w = low_means[dv]
        if s in w.columns and w[s].notna().any():
            low_vals.append(f"{w[s].mean():.2f}")
        else:
            low_vals.append("N/A")

    high_vals = [f"{high_means[dv][s].mean():.2f}" for s in SYSTEM_ORDER]

    print(f"{dv:<22} {low_vals[0]:>12} {low_vals[1]:>12} {low_vals[2]:>12}"
          f"    {high_vals[0]:>12} {high_vals[1]:>12} {high_vals[2]:>12}")

print()
print("SonoAdapt-LOW Detectability = N/A (system mutes LOW notifications).")
print()

# ── Generate dataForWriting.txt ───────────────────────────────────────────────
ref_path = OUTPUT_DIR / "dataForWriting.txt"
with open(ref_path, "w", encoding="utf-8") as f:
    f.write("=" * 80 + "\n")
    f.write("SIMPLE EFFECTS — Data Reference for Writing\n")
    f.write("=" * 80 + "\n")
    f.write(f"N = 23 participants (after removing 4 outliers)\n")
    f.write(f"All values are participant-level means.\n\n")

    for urgency_label, means_dict, dv_list in [
        ("LOW", low_means, DV_ORDER_FULL),
        ("HIGH", high_means, DV_ORDER_FULL),
    ]:
        f.write("=" * 80 + "\n")
        f.write(f"URGENCY/IMPORTANCE = {urgency_label}\n")
        f.write("=" * 80 + "\n\n")

        for dv in dv_list:
            w = means_dict[dv]
            systems_available = [s for s in SYSTEM_ORDER if s in w.columns and w[s].notna().any()]
            f.write("-" * 80 + "\n")
            f.write(f"DV: {dv}  ({urgency_label})\n")
            f.write(f"  Scale: {DV_NOTES[dv]}\n\n")

            f.write("  Descriptives per System:\n")
            for s in SYSTEM_ORDER:
                if s in w.columns and w[s].notna().any():
                    m = w[s].mean()
                    sd = w[s].std(ddof=1)
                    mdn = w[s].median()
                    f.write(f"    {s:12s}  M = {m:.2f},  SD = {sd:.2f},  Mdn = {mdn:.2f}\n")
                else:
                    f.write(f"    {s:12s}  N/A (muted by design)\n")

            if len(systems_available) >= 3:
                # Friedman
                mat = w[systems_available].dropna().to_numpy(float)
                chi2, p_fr = stats.friedmanchisquare(*[mat[:, j] for j in range(mat.shape[1])])
                W_val = kendalls_w(mat)
                f.write(f"\n  Friedman: χ²(2) = {chi2:.2f}, p = {p_fr:.5f}, W = {W_val:.3f} {sig_stars(p_fr)}\n")

                pairs = [("Earcon", "Speech"), ("Earcon", "SonoAdapt"), ("Speech", "SonoAdapt")]
                results = [wilcoxon_pair(w[a].dropna(), w[b].dropna()) for a, b in pairs]
                p_adj = holm_correction([x["p"] for x in results])

                f.write("\n  Pairwise (Holm-corrected):\n")
                for (a, b), x, pa in zip(pairs, results, p_adj):
                    diff = w[a].mean() - w[b].mean()
                    dz = cohen_dz(w[a].dropna(), w[b].dropna())
                    f.write(f"    {a} vs {b}:  ΔM = {diff:.2f},  p_Holm = {pa:.5f},  "
                            f"r_rb = {x['rb']:.2f},  d_z = {dz:.2f}  {sig_stars(pa)}\n")
            elif len(systems_available) == 2:
                # 2-system Wilcoxon (Detectability LOW)
                a, b = systems_available
                valid = w[[a, b]].dropna()
                res = wilcoxon_pair(valid[a], valid[b])
                dz = cohen_dz(valid[a], valid[b])
                diff = valid[a].mean() - valid[b].mean()
                f.write(f"\n  Wilcoxon (2-system, no correction needed):\n")
                f.write(f"    {a} vs {b}:  ΔM = {diff:.2f},  p = {res['p']:.5f},  "
                        f"r_rb = {res['rb']:.2f},  d_z = {dz:.2f}  {sig_stars(res['p'])}\n")

            # Copyable inline-text snippets
            f.write(f"\n  ── Copyable Snippets ──\n")
            for s in SYSTEM_ORDER:
                if s in w.columns and w[s].notna().any():
                    m = w[s].mean()
                    sd = w[s].std(ddof=1)
                    f.write(f"    {s}: (M = {m:.2f}, SD = {sd:.2f})\n")
            f.write("\n")

    f.write("=" * 80 + "\n")
    f.write("END\n")

sys.__stdout__.write(f"  Saved: {ref_path}\n")


# ── Close output ──────────────────────────────────────────────────────────────
hr("DONE", "=")
print(f"All results saved to: {OUTPUT_DIR}")

_output_file.close()
sys.stdout = sys.__stdout__
print(f"\n✅ Simple effects analysis complete. Results saved to: {OUTPUT_DIR}")
