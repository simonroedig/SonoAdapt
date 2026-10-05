"""
roughAnalysis.py – Quick directional analysis of the SonoAdapt summative study.
Compares SonoAdapt (X) against Baseline-Earcon (E) and Baseline-Speech (S)
on four Likert dimensions: Appropriateness, Detectability, Disruptiveness,
and Social Acceptability.

No significance testing – just means, to see where the data is trending.
"""

import pandas as pd
import numpy as np
import json
import sys
from pathlib import Path

# Force unbuffered output to avoid garbled / repeated lines in some terminals.
sys.stdout.reconfigure(line_buffering=True)

# ── 0. Config ─────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
RAW_PATH = SCRIPT_DIR / "raw.xlsx"
OUTLIERS_PATH = SCRIPT_DIR / "potential_outliers.json"
OUTPUT_PATH   = SCRIPT_DIR / "roughAnalysisResults.txt"

# Toggle outlier removal on/off
REMOVE_OUTLIERS = True


# ── Tee: write all print() output to both console and text file ──────────────
class _Tee:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            s.write(data)
    def flush(self):
        for s in self.streams:
            s.flush()

_output_file = open(OUTPUT_PATH, "w", encoding="utf-8")
sys.stdout = _Tee(sys.__stdout__, _output_file)

# Likert-to-numeric mappings (higher = "better" for Appropriateness & Social;
# higher = easier to detect for Detectability; higher = more disruptive for
# Disruptiveness – we keep the natural scale direction and interpret later).

APPROPRIATENESS_MAP = {
    "Completely inappropriate":              1,
    "Inappropriate":                         2,
    "Somewhat inappropriate":                3,
    "Neither appropriate nor inappropriate": 4,
    "Somewhat appropriate":                  5,
    "Appropriate":                           6,
    "Completely appropriate":                7,
}

DETECTABILITY_MAP = {
    "Very difficult to detect":              1,
    "Difficult to detect":                   2,
    "Somewhat difficult to detect":          3,
    "Neither easy nor difficult to detect":  4,
    "Somewhat easy to detect":               5,
    "Easy to detect":                        6,
    "Very easy to detect":                   7,
}

DISRUPTIVENESS_MAP = {
    "Not disruptive at all":  1,
    "Slightly disruptive":    2,
    "Somewhat disruptive":    3,
    "Moderately disruptive":  4,
    "Disruptive":             5,
    "Very disruptive":        6,
    "Extremely disruptive":   7,
}

SOCIAL_MAP = {
    "Completely unacceptable":              1,
    "Unacceptable":                         2,
    "Somewhat unacceptable":                3,
    "Neither acceptable nor unacceptable":  4,
    "Somewhat acceptable":                  5,
    "Acceptable":                           6,
    "Completely acceptable":                7,
    "Completely Acceptable":                7,  # handle capitalisation variant in data
}

SYSTEM_LABELS = {"E": "Baseline-Earcon", "S": "Baseline-Speech", "X": "SonoAdapt"}
URGENCY_LABELS = {"L": "LOW", "H": "HIGH"}


# ── 1. Data preprocessing ────────────────────────────────────────────────────
print("=" * 70)
print("LOADING & PREPROCESSING")
print("=" * 70)

df_raw = pd.read_excel(RAW_PATH, header=0, skiprows=[1])  # skip Qualtrics sub-header row

print(f"  Raw rows loaded: {len(df_raw)}")

# Remove pilot participant (the very first row in the spreadsheet was a pilot test).
# We drop by row position, NOT by name, so a future participant named Laura won't
# be removed accidentally.
df_raw = df_raw.iloc[1:].reset_index(drop=True)

print(f"  Rows after removing pilot (1st row): {len(df_raw)}")
print(f"  Remaining participants: {df_raw['Participant Name'].tolist()}")
print()

# ── 2. Reshape wide → long (12 trials per participant) ───────────────────────
records = []
for _, row in df_raw.iterrows():
    pid = row["Participant ID"]
    pname = row["Participant Name"]
    for trial_num in range(1, 13):
        prefix = f"{trial_num}_"
        code = row[f"{prefix}ID"]
        if pd.isna(code) or str(code).strip() == "":
            continue
        code = str(code).strip()
        # Parse the 4-char code: <Scenario I|M><System E|S|X><Urgency L|H><Message 1-6>
        scenario = code[0]   # I or M
        system   = code[1]   # E, S, or X
        urgency  = code[2]   # L or H
        message  = code[3]   # 1-6

        records.append({
            "Participant":    pname,
            "PID":            pid,
            "Trial":          trial_num,
            "Code":           code,
            "Scenario":       "Interview" if scenario == "I" else "Math",
            "System":         SYSTEM_LABELS.get(system, system),
            "Urgency":        URGENCY_LABELS.get(urgency, urgency),
            "Message":        f"{urgency}{message}",
            "Urgency_raw":    row.get(f"{prefix}Urgent and Important_4", np.nan),
            "Importance_raw": row.get(f"{prefix}Urgent and Important_5", np.nan),
            "Form":           row.get(f"{prefix}Form", ""),
            "Appropriateness_label": row.get(f"{prefix}Appropriate_1", ""),
            "Detectability_label":   row.get(f"{prefix}Detect_1", ""),
            "Disruptiveness_label":  row.get(f"{prefix}Disruptive_1", ""),
            "SocialAcceptability_label": row.get(f"{prefix}Social_1", ""),
        })

df = pd.DataFrame(records)

# Map Likert labels → numeric
df["Appropriateness"]     = df["Appropriateness_label"].map(APPROPRIATENESS_MAP)
df["Detectability"]       = df["Detectability_label"].map(DETECTABILITY_MAP)
df["Disruptiveness"]      = df["Disruptiveness_label"].map(DISRUPTIVENESS_MAP)
df["SocialAcceptability"] = df["SocialAcceptability_label"].map(SOCIAL_MAP)

# SonoAdapt + LOW → no auditory notification was played.  The participant was
# instructed to pick "Neither easy nor difficult to detect" (=4) as a default,
# so this is NOT a real detectability measurement.  We NaN it out so it is
# automatically excluded from all downstream Detectability aggregations.
is_sonoadapt_low = (df["System"] == "SonoAdapt") & (df["Urgency"] == "LOW")
df.loc[is_sonoadapt_low, "Detectability"] = np.nan

print(f"  Total trials (long format): {len(df)}")
print(f"  Trials per system:\n{df['System'].value_counts().to_string()}")
print(f"  Note: {is_sonoadapt_low.sum()} SonoAdapt+LOW trials have Detectability = NaN (excluded)")
print()


# ── 3. Sanity check: Perceived urgency/importance vs. designed level ──────────
print("=" * 70)
print("SANITY CHECK: Perceived Urgency & Importance by Designed Level")
print("=" * 70)
print("  (Both are 0–100 sliders. LOW should be low, HIGH should be high.)\n")

for urg in ["LOW", "HIGH"]:
    sub = df[df["Urgency"] == urg]
    u_mean = sub["Urgency_raw"].mean()
    u_std  = sub["Urgency_raw"].std()
    i_mean = sub["Importance_raw"].mean()
    i_std  = sub["Importance_raw"].std()
    print(f"  {urg:4s} notifications (n={len(sub)}):  "
          f"Urgency M={u_mean:5.1f} (SD={u_std:5.1f})   "
          f"Importance M={i_mean:5.1f} (SD={i_std:5.1f})")
print()


# ── 4. Sanity check: Notification form vs. expected delivery ──────────────────
print("=" * 70)
print("SANITY CHECK: Did participants report the correct notification form?")
print("=" * 70)
print("  Expected delivery:")
print("    Baseline-Earcon  → always 🔔 Earcon/Chime")
print("    Baseline-Speech  → always 🗣️ Spoken")
print("    SonoAdapt + LOW  → always ❌ Did not notice (muted)")
print("    SonoAdapt + HIGH + Interview → 🔔 Earcon/Chime")
print("    SonoAdapt + HIGH + Math      → 🗣️ Spoken")
print()

FORM_EARCON = "🔔 Earcon/Chime"
FORM_SPEECH = "🗣️ Spoken"
FORM_NONE   = "❌ Did not notice any auditory notification"


def expected_form(row):
    """Return the expected notification form for a given trial."""
    if row["System"] == "Baseline-Earcon":
        return FORM_EARCON
    elif row["System"] == "Baseline-Speech":
        return FORM_SPEECH
    else:  # SonoAdapt
        if row["Urgency"] == "LOW":
            return FORM_NONE
        else:  # HIGH
            if row["Scenario"] == "Interview":
                return FORM_EARCON
            else:  # Math
                return FORM_SPEECH


df["Expected_Form"] = df.apply(expected_form, axis=1)
df["Form_Correct"]  = df["Form"] == df["Expected_Form"]

n_correct = df["Form_Correct"].sum()
n_total   = len(df)
print(f"  Overall: {n_correct}/{n_total} correct ({100*n_correct/n_total:.0f}%)\n")

# Show mismatches
mismatches = df[~df["Form_Correct"]]
if len(mismatches) == 0:
    print("  ✅ No mismatches – all participants identified the form correctly!")
else:
    print(f"  ⚠️  {len(mismatches)} mismatch(es):")
    for _, m in mismatches.iterrows():
        print(f"    {m['Participant']:10s}  {m['Code']}  "
              f"expected: {m['Expected_Form']}  "
              f"reported: {m['Form']}")
print()


# ── 5. Attention check: SonoAdapt+LOW detectability = "Neither" (=4) ──────────
print("=" * 70)
print("ATTENTION CHECK: SonoAdapt+LOW → Detectability should be 'Neither' (=4)")
print("=" * 70)
print('  (Participants were told: "If you did not receive any auditory')
print('   notification, choose the middle option.")')
print()

sonoadapt_low = df[is_sonoadapt_low].copy()
# We already NaN'd the numeric column, so check using the raw label
sonoadapt_low["Detect_Check"] = (
    sonoadapt_low["Detectability_label"] == "Neither easy nor difficult to detect"
)
n_ok = sonoadapt_low["Detect_Check"].sum()
n_sa_low = len(sonoadapt_low)
print(f"  {n_ok}/{n_sa_low} picked 'Neither' as expected")
if n_ok < n_sa_low:
    fails = sonoadapt_low[~sonoadapt_low["Detect_Check"]]
    for _, f in fails.iterrows():
        print(f"    ⚠️  {f['Participant']:10s}  {f['Code']}  "
              f"answered: {f['Detectability_label']}")
else:
    print("  ✅ All correct!")
print()


# ── 6. Consolidated attention-check summary ───────────────────────────────────
print("=" * 70)
print("ATTENTION-CHECK SUMMARY")
print("=" * 70)

# Check 1: Urgency/Importance direction
low_trials  = df[df["Urgency"] == "LOW"]
high_trials = df[df["Urgency"] == "HIGH"]
check1_ok = (low_trials["Urgency_raw"].mean() < 30) and (high_trials["Urgency_raw"].mean() > 70)

# Check 2: Notification form
check2_n_ok = df["Form_Correct"].sum()
check2_n    = len(df)

# Check 3: SonoAdapt+LOW detectability = Neither
check3_n_ok = n_ok
check3_n    = n_sa_low

print(f"  1. Urgency/Importance vs. designed level:  "
      f"{'✅ PASS' if check1_ok else '⚠️  CHECK'} "
      f"(LOW M={low_trials['Urgency_raw'].mean():.0f}, HIGH M={high_trials['Urgency_raw'].mean():.0f})")
print(f"  2. Notification form identification:       "
      f"{'✅ PASS' if check2_n_ok == check2_n else '⚠️  CHECK'} "
      f"({check2_n_ok}/{check2_n} correct)")
print(f"  3. SonoAdapt+LOW detectability = 'Neither': "
      f"{'✅ PASS' if check3_n_ok == check3_n else '⚠️  CHECK'} "
      f"({check3_n_ok}/{check3_n} correct)")
print()
print("  Note: SonoAdapt+LOW Detectability values are EXCLUDED from all")
print("  downstream analyses (set to NaN) since no notification was played.")
print()


# ── 7. Remove outliers from analysis ─────────────────────────────────────────
print("=" * 70)
print("OUTLIER REMOVAL")
print("=" * 70)

if not REMOVE_OUTLIERS:
    print("  REMOVE_OUTLIERS = False → skipping outlier removal.")
elif OUTLIERS_PATH.exists():
    with open(OUTLIERS_PATH, "r", encoding="utf-8") as fh:
        outlier_data = json.load(fh)
    outlier_names = [
        o["name"] for o in outlier_data.get("outliers", [])
        if o.get("status") == "is_outlier"
    ]
    n_before = df["Participant"].nunique()
    removed = df[df["Participant"].isin(outlier_names)]["Participant"].unique().tolist()
    df = df[~df["Participant"].isin(outlier_names)].reset_index(drop=True)
    # Re-compute the SonoAdapt+LOW mask on the filtered df
    is_sonoadapt_low = (df["System"] == "SonoAdapt") & (df["Urgency"] == "LOW")
    n_after = df["Participant"].nunique()
    print(f"  Loaded {OUTLIERS_PATH.name}: {len(outlier_names)} outlier(s) listed")
    print(f"  Removed: {', '.join(removed)} ({len(removed)} participants)")
    print(f"  Participants remaining for analysis: {n_after} "
          f"(was {n_before}, removed {n_before - n_after})")
    print(f"  Remaining: {sorted(df['Participant'].unique().tolist())}")
else:
    print(f"  {OUTLIERS_PATH.name} not found – no outliers removed.")
print()


# ── 7b. Gender demographics (after outlier removal) ─────────────────────────
print("=" * 70)
print("PARTICIPANT DEMOGRAPHICS: Gender")
print("=" * 70)

remaining_participants = df["Participant"].unique().tolist()
df_demo = df_raw[df_raw["Participant Name"].isin(remaining_participants)].copy()
gender_counts = df_demo["Gender"].value_counts()
gender_total = len(df_demo)

print(f"  Total participants (after outlier removal): {gender_total}\n")
for gender, count in gender_counts.items():
    pct = 100 * count / gender_total
    print(f"    {gender:20s}  n = {count:2d}  ({pct:5.1f}%)")
print()


# ── 8. Helper to print a comparison table ─────────────────────────────────────
DIMENSIONS = ["Appropriateness", "Detectability", "Disruptiveness", "SocialAcceptability"]
DIM_NOTES = {
    "Appropriateness":     "(1=completely inappropriate … 7=completely appropriate)  ↑ better",
    "Detectability":       "(1=very difficult … 7=very easy to detect)              ↑ better",
    "Disruptiveness":      "(1=not disruptive … 7=extremely disruptive)             ↓ better",
    "SocialAcceptability": "(1=completely unacceptable … 7=completely acceptable)    ↑ better",
}

SYSTEM_ORDER = ["Baseline-Earcon", "Baseline-Speech", "SonoAdapt"]


def print_comparison(subset: pd.DataFrame, title: str):
    """Print mean ± std for each dimension × system."""
    print("=" * 70)
    print(title)
    print("=" * 70)
    n_trials = len(subset)
    n_participants = subset["Participant"].nunique()
    print(f"  n = {n_trials} trials from {n_participants} participants\n")

    for dim in DIMENSIONS:
        print(f"  {dim}  {DIM_NOTES[dim]}")
        agg = (
            subset.groupby("System")[dim]
            .agg(["mean", "std", "count"])
            .reindex(SYSTEM_ORDER)
        )
        for sys_name, row in agg.iterrows():
            marker = ""
            # Mark SonoAdapt with an arrow only if it's STRICTLY the best
            if sys_name == "SonoAdapt" and not np.isnan(row["mean"]):
                others = agg.drop("SonoAdapt")["mean"].dropna()
                if dim == "Disruptiveness":
                    if len(others) > 0 and row["mean"] < others.min():
                        marker = "  ★ lowest"
                else:
                    if len(others) > 0 and row["mean"] > others.max():
                        marker = "  ★ highest"
            print(f"    {sys_name:20s}  M = {row['mean']:5.2f}  (SD = {row['std']:5.2f}, n = {int(row['count'])}){marker}")
        print()


# ── 9. Overall comparison ─────────────────────────────────────────────────────
print_comparison(df, "OVERALL COMPARISON (all trials, outliers removed)")


# ── 10. Split by urgency ─────────────────────────────────────────────────────
for urg in ["LOW", "HIGH"]:
    print_comparison(df[df["Urgency"] == urg], f"URGENCY/IMPORTANCE = {urg}")


print("Done. This is a rough directional overview – no significance tests yet.")

# Close the output file
_output_file.close()
sys.stdout = sys.__stdout__
print(f"\nResults saved to {OUTPUT_PATH}")
