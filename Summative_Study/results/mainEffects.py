"""
mainEffects.py – Main-effects analysis (System factor) for the SonoAdapt summative study.
=========================================================================================

Design:
  3 (System: Earcon / Speech / SonoAdapt)
  × 2 (Urgency/Importance: Low / High)
  × 2 (Scenario: Interview / Math)
  Fully within-subjects; 12 trials per participant.

Dependent variables (7-point Likert):
  Appropriateness:    1 = completely inappropriate … 7 = completely appropriate   (↑ better)
  Social Acceptability: 1 = completely unacceptable … 7 = completely acceptable   (↑ better)
  Detectability:      1 = very difficult to detect … 7 = very easy to detect      (↑ better)
  Disruptiveness:     1 = not disruptive at all … 7 = extremely disruptive        (↓ better)

Statistical approach:
  - Main effect of System (the "overall" comparison, collapsing over urgency + scenario).
  - Unit of analysis: per participant, average across all trials for each system →
    one value per participant per system (repeated-measures factor).
  - Omnibus test: Friedman test (non-parametric repeated-measures ANOVA on ranks).
    Effect size: Kendall's W.
  - Post-hoc: All 3 pairwise Wilcoxon signed-rank tests, Holm-Bonferroni corrected.
    Effect sizes: matched-pairs rank-biserial correlation (r_rb), r = |Z|/√N, Cohen's d_z.
  - Detectability: SonoAdapt+LOW trials are silent by design (muted), so detectability
    ratings for those trials are excluded. The matched comparison uses HIGH-only trials.

Outputs saved to mainEffectsPlotsAndData/:
  - mainEffectsResults.txt   – Full statistical report
  - fig_mainEffects.png/pdf  – Publication-ready boxplot (4 DVs × 3 systems)
  - participantMeans.csv     – Participant-level means used for the Friedman tests

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
OUTPUT_DIR = SCRIPT_DIR / "mainEffectsPlotsAndData"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_TXT = OUTPUT_DIR / "mainEffectsResults.txt"
OUTPUT_CSV = OUTPUT_DIR / "participantMeans.csv"

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
ALPHA_BONF = 0.025  # per a-priori power analysis (2 scenario analyses)

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

DV_ORDER = ["Appropriateness", "SocialAcceptability", "Detectability", "Disruptiveness"]

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


hr("SonoAdapt Summative Study — Main-Effects Analysis (System Factor)")
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
# SonoAdapt suppresses LOW-urgency notifications (no sound played).
# Participants were told to pick the midpoint for detectability in that case.
# These are NOT real detectability measurements, so we exclude them.
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
    # z from the normal approximation
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
    """Create participant × system matrix, averaging over urgency and scenario."""
    w = data.pivot_table(index="pid", columns="system", values=dv,
                         aggfunc="mean", observed=True)
    return w.reindex(columns=SYSTEM_ORDER)


# ── 7. Main Effect Analysis ──────────────────────────────────────────────────

def run_main_effect_analysis(data, dv, note, label=""):
    """Run Friedman omnibus + Holm-corrected pairwise Wilcoxon for one DV."""
    title = f"[{dv}]  ({note})"
    if label:
        title = f"{label}\n  {title}"
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


# ── 8. Run the Main Analysis ─────────────────────────────────────────────────
hr("1. MAIN ANALYSIS — SYSTEM EFFECT, POOLED OVER SCENARIO AND URGENCY")
print(f"N = {N} participants.  Each participant's system score is the mean of all")
print(f"their trials for that system (collapsed across scenario × urgency).\n")

all_participant_means = {}  # for CSV export

for dv in DV_ORDER:
    if dv == "Detectability":
        # Special handling: the matched comparison uses HIGH-only trials
        print(f"\n{'='*88}")
        print(f"NOTE on Detectability: SonoAdapt+LOW is silent by design, so those")
        print(f"detectability ratings are excluded. To avoid confounding system with")
        print(f"urgency (SonoAdapt would only have HIGH trials while baselines have all 4),")
        print(f"we report TWO analyses:")
        print(f"  (a) All available trials (urgency-confounded – shown for completeness)")
        print(f"  (b) HIGH-urgency trials only (matched comparison – this is the one to report)")

        w_a, *_ = run_main_effect_analysis(
            df, dv, DV_NOTES[dv],
            label="(a) All available trials [SonoAdapt = HIGH only; baselines = all trials; CONFOUNDED]"
        )
        high_only = df[df["urgency"] == "High"]
        w_b, *_ = run_main_effect_analysis(
            high_only, dv, DV_NOTES[dv],
            label="(b) HIGH-urgency trials only [matched comparison — REPORT THIS]"
        )
        all_participant_means[dv] = w_b  # use the matched comparison for export
    else:
        w, *_ = run_main_effect_analysis(df, dv, DV_NOTES[dv])
        all_participant_means[dv] = w


# ── 9. Export participant-level means to CSV ──────────────────────────────────
hr("EXPORT: Participant-level means")

csv_frames = []
for dv, w in all_participant_means.items():
    melted = w.reset_index().melt(id_vars="pid", var_name="system", value_name="mean_rating")
    melted["DV"] = dv
    csv_frames.append(melted)

csv_df = pd.concat(csv_frames, ignore_index=True)
csv_df = csv_df[["pid", "DV", "system", "mean_rating"]]
csv_df.to_csv(OUTPUT_CSV, index=False)
print(f"Saved participant-level means to: {OUTPUT_CSV}")
print(f"  ({len(csv_df)} rows: {csv_df['pid'].nunique()} participants × "
      f"{len(DV_ORDER)} DVs × {len(SYSTEM_ORDER)} systems)")
print()


# ── 10. Publication-Ready Boxplots ────────────────────────────────────────────
hr("GENERATING PLOTS")

# Custom color palette
COLORS = {"Earcon": "#FFC300", "Speech": "#694487", "SonoAdapt": "#56C959"}
BOX_WIDTH = 0.75
Y_STEP = 0.3

# We generate 4 plot variants:
#   {all 4 DVs, without Detectability} × {SonoAdapt (thesis), AudioAdapt (paper)}
PLOT_VARIANTS = [
    {"include_detect": True,  "system_name": "SonoAdapt",  "suffix": "SonoAdapt_4DV"},
    {"include_detect": False, "system_name": "SonoAdapt",  "suffix": "SonoAdapt_3DV"},
    {"include_detect": True,  "system_name": "AudioAdapt", "suffix": "AudioAdapt_4DV"},
    {"include_detect": False, "system_name": "AudioAdapt", "suffix": "AudioAdapt_3DV"},
]

def get_plot_matrix(dv):
    """Get the participant × system matrix used for the Friedman tests."""
    if dv == "Detectability":
        return wide_by_system(df[df["urgency"] == "High"], dv)
    return wide_by_system(df, dv)


def get_significant_pairs(w, system_names):
    """Return Holm-corrected significant Wilcoxon pairs for the plot."""
    mat = w.dropna().to_numpy(float)
    if mat.shape[0] < 3:
        return []
    chi2, p_fr = stats.friedmanchisquare(*[mat[:, j] for j in range(mat.shape[1])])
    if p_fr >= ALPHA:
        return []
    pairs = [(system_names[0], system_names[1]),
             (system_names[0], system_names[2]),
             (system_names[1], system_names[2])]
    # Use the original column names for stats (always "Earcon", "Speech", "SonoAdapt")
    orig_pairs = [("Earcon", "Speech"), ("Earcon", "SonoAdapt"), ("Speech", "SonoAdapt")]
    results = [wilcoxon_pair(w[a].dropna(), w[b].dropna()) for a, b in orig_pairs]
    padj = holm_correction([r["p"] for r in results])
    marked = []
    for (a, b), pa in zip(pairs, padj):
        ast = sig_stars(pa, ALPHA)
        if ast not in ("n.s.", "."):
            marked.append((a, b, ast))
    # Sort by span (adjacent pairs first)
    idx = {s: i for i, s in enumerate(system_names)}
    marked.sort(key=lambda t: abs(idx[t[0]] - idx[t[1]]))
    return marked


def hue_offsets(n=3, width=BOX_WIDTH):
    return [-width / 2 + width / (2 * n) + k * (width / n) for k in range(n)]


def make_plot(dv_list, system_name, suffix):
    """Generate a single boxplot variant."""
    system_names = ["Earcon", "Speech", system_name]
    colors = {"Earcon": "#FFC300", "Speech": "#694487", system_name: "#56C959"}

    dv_titles = {
        "Appropriateness": "Appropriateness",
        "SocialAcceptability": "Social Acceptability",
        "Detectability": "Detectability",
        "Disruptiveness": "Disruptiveness\n(lower = better)",
    }

    # Build long-format data for seaborn
    rows = []
    for dv in dv_list:
        w = get_plot_matrix(dv)
        for s_orig, s_display in zip(SYSTEM_ORDER, system_names):
            for _, v in w[s_orig].items():
                if pd.notna(v):
                    rows.append({"scale": dv_titles[dv], "system": s_display, "rating": v})

    plot_data = pd.DataFrame(rows)
    plot_data["scale"] = pd.Categorical(
        plot_data["scale"], [dv_titles[d] for d in dv_list], True
    )
    plot_data["system"] = pd.Categorical(
        plot_data["system"], system_names, ordered=True
    )

    # Adjust figure width based on number of DVs
    fig_width = 12 if len(dv_list) == 4 else 9.5
    fig, ax = plt.subplots(figsize=(fig_width, 5.5))
    sns.boxplot(
        data=plot_data, x="scale", y="rating", hue="system",
        palette=colors, width=BOX_WIDTH, whis=(0, 100), ax=ax,
        saturation=1.0,  # prevent seaborn from washing out colors
    )

    # Add M(SD) annotations above each box
    offs = hue_offsets()
    idx_map = {s: i for i, s in enumerate(system_names)}
    for gi, dv in enumerate(dv_list):
        w = get_plot_matrix(dv)
        for s_orig, s_display in zip(SYSTEM_ORDER, system_names):
            if s_orig in w.columns and w[s_orig].notna().any():
                m = w[s_orig].mean()
                sd = w[s_orig].std(ddof=1)
                x_pos = gi + offs[idx_map[s_display]]
                ax.text(x_pos, 7.2, f"M={m:.2f}\nSD={sd:.2f}",
                        ha="center", fontsize="small",
                        color="black", fontweight="bold",
                        fontfamily="Arial")

    # Add significance bars
    y_start = 8.1

    for gi, dv in enumerate(dv_list):
        y = y_start
        w = get_plot_matrix(dv)
        for a, b, asterisks in get_significant_pairs(w, system_names):
            x1, x2 = gi + offs[idx_map[a]], gi + offs[idx_map[b]]
            bar_height = y
            bar_tips = bar_height - (Y_STEP * 0.2)
            ax.plot([x1, x1, x2, x2], [bar_tips, bar_height, bar_height, bar_tips],
                    lw=1.5, c="black")
            ax.text((x1 + x2) / 2, bar_height, asterisks, ha="center", va="bottom",
                    color="black", fontsize=12)
            y += Y_STEP * 1.5

    ax.set_ylim(0.5, y_start + Y_STEP * 1.5 * 3 + 0.8)
    ax.set_title("Main Effect of the System: Likert Ratings",
                 fontsize=13, fontweight="regular")
    ax.set_xlabel("")
    ax.set_ylabel("Rating (1–7)", fontsize=12)
    ax.set_yticks(range(1, 8))
    ax.legend(title=None, fontsize=11, loc="lower center", ncol=3,
              framealpha=0.9, edgecolor="lightgray")
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()

    for ext in ("pdf", "png"):
        fig.savefig(OUTPUT_DIR / f"fig_mainEffects_{suffix}.{ext}",
                    dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: fig_mainEffects_{suffix}.png / .pdf")


matplotlib.rcdefaults()
plt.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42})

for variant in PLOT_VARIANTS:
    dvs = DV_ORDER if variant["include_detect"] else [d for d in DV_ORDER if d != "Detectability"]
    make_plot(dvs, variant["system_name"], variant["suffix"])

print()


# ── 11. Summary Table ─────────────────────────────────────────────────────────
hr("SUMMARY TABLE — For quick reference / copy-paste into thesis")

print(f"\nN = {N} participants (after outlier removal)")
print(f"\n{'DV':<22} {'Earcon':>12} {'Speech':>12} {'SonoAdapt':>12}"
      f"   {'Friedman χ²':>12} {'p':>10} {'W':>6}   sig")
print("-" * 100)

for dv in DV_ORDER:
    w = get_plot_matrix(dv)
    mat = w.dropna().to_numpy(float)
    chi2, p_fr = stats.friedmanchisquare(*[mat[:, j] for j in range(mat.shape[1])])
    W = kendalls_w(mat)
    means = [f"{w[s].mean():.2f} ({w[s].std(ddof=1):.2f})" for s in SYSTEM_ORDER]
    print(f"{dv:<22} {means[0]:>12} {means[1]:>12} {means[2]:>12}"
          f"   {chi2:>12.2f} {p_fr:>10.5f} {W:>6.3f}   {sig_stars(p_fr)}")

print()
print("Values are M (SD) at the participant level.")
print("Detectability uses HIGH-urgency trials only (matched comparison).")

print()
hr("PAIRWISE SUMMARY TABLE")
print(f"\n{'DV':<22} {'Comparison':<26} {'ΔM':>7} {'p_Holm':>10} {'r_rb':>7} {'d_z':>6}   sig")
print("-" * 95)

for dv in DV_ORDER:
    w = get_plot_matrix(dv)
    pairs = [("Earcon", "Speech"), ("Earcon", "SonoAdapt"), ("Speech", "SonoAdapt")]
    results = [wilcoxon_pair(w[a].dropna(), w[b].dropna()) for a, b in pairs]
    p_adj = holm_correction([x["p"] for x in results])
    for (a, b), x, pa in zip(pairs, results, p_adj):
        diff = w[a].mean() - w[b].mean()
        dz = cohen_dz(w[a].dropna(), w[b].dropna())
        print(f"{dv:<22} {a + ' vs ' + b:<26} {diff:>7.2f} {pa:>10.5f}"
              f" {x['rb']:>7.2f} {dz:>6.2f}   {sig_stars(pa)}")
    if dv != DV_ORDER[-1]:
        print()

print()
print("Significance codes: *** p<.001, ** p<.01, * p<.05, . p<.10, n.s. p≥.10")
print()

# ── Generate dataForWriting.txt ───────────────────────────────────────────────
ref_path = OUTPUT_DIR / "dataForWriting.txt"
with open(ref_path, "w", encoding="utf-8") as f:
    f.write("=" * 80 + "\n")
    f.write("MAIN EFFECTS — Data Reference for Writing\n")
    f.write("=" * 80 + "\n")
    f.write(f"N = 23 participants (after removing 4 outliers)\n")
    f.write(f"All values are participant-level means (unit of analysis).\n")
    f.write(f"Detectability uses HIGH-urgency trials only (matched comparison).\n\n")

    for dv in DV_ORDER:
        w = get_plot_matrix(dv)
        f.write("-" * 80 + "\n")
        f.write(f"DV: {dv}\n")
        f.write(f"  Scale: {DV_NOTES[dv]}\n\n")

        f.write("  Descriptives per System:\n")
        for s in SYSTEM_ORDER:
            m = w[s].mean()
            sd = w[s].std(ddof=1)
            mdn = w[s].median()
            f.write(f"    {s:12s}  M = {m:.2f},  SD = {sd:.2f},  Mdn = {mdn:.2f}\n")

        # Friedman
        mat = w.dropna().to_numpy(float)
        chi2, p_fr = stats.friedmanchisquare(*[mat[:, j] for j in range(mat.shape[1])])
        W = kendalls_w(mat)
        f.write(f"\n  Friedman: χ²(2) = {chi2:.2f}, p = {p_fr:.5f}, W = {W:.3f} {sig_stars(p_fr)}\n")

        # Pairwise
        pairs = [("Earcon", "Speech"), ("Earcon", "SonoAdapt"), ("Speech", "SonoAdapt")]
        results = [wilcoxon_pair(w[a].dropna(), w[b].dropna()) for a, b in pairs]
        p_adj = holm_correction([x["p"] for x in results])

        f.write("\n  Pairwise (Holm-corrected):\n")
        for (a, b), x, pa in zip(pairs, results, p_adj):
            diff = w[a].mean() - w[b].mean()
            dz = cohen_dz(w[a].dropna(), w[b].dropna())
            f.write(f"    {a} vs {b}:  ΔM = {diff:.2f},  p_Holm = {pa:.5f},  "
                    f"r_rb = {x['rb']:.2f},  d_z = {dz:.2f}  {sig_stars(pa)}\n")

        # Copyable inline-text snippets
        f.write(f"\n  ── Copyable Snippets ──\n")
        for s in SYSTEM_ORDER:
            m = w[s].mean()
            sd = w[s].std(ddof=1)
            f.write(f"    {s}: (M = {m:.2f}, SD = {sd:.2f})\n")
        for (a, b), x, pa in zip(pairs, results, p_adj):
            diff = w[a].mean() - w[b].mean()
            f.write(f"    {a} vs {b}: (ΔM = {diff:.2f}, p = {pa:.5f})\n")
        f.write("\n")

    f.write("=" * 80 + "\n")
    f.write("END\n")

sys.__stdout__.write(f"  Saved: {ref_path}\n")


# ── Close output ──────────────────────────────────────────────────────────────
hr("DONE", "=")
print(f"All results saved to: {OUTPUT_DIR}")

_output_file.close()
sys.stdout = sys.__stdout__
print(f"\n✅ Main effects analysis complete. Results saved to: {OUTPUT_DIR}")
