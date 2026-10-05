"""
stripRaw.py – Extract post-study questionnaire responses from raw.xlsx.
========================================================================

Creates a cleaned Excel file containing only:
  - Participant ID and Name (for identification)
  - The four post-study questionnaire columns:
      AdaptiveORStatic, AdaptiveRules, Explanation, Customization

Removes:
  - The pilot participant (Laura Schuetz, row 0)
  - All outliers (Tejaswini, Ritika, Anna, Osama)

Output: results/rawStripped.xlsx
"""

import json
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

SCRIPT_DIR = Path(__file__).resolve().parent
RAW_PATH = SCRIPT_DIR / "results" / "raw.xlsx"
OUTLIERS_PATH = SCRIPT_DIR / "results" / "potential_outliers.json"
OUTPUT_PATH = SCRIPT_DIR / "results" / "rawStripped.xlsx"

# ── Load ──────────────────────────────────────────────────────────────────────
df = pd.read_excel(RAW_PATH, header=0, skiprows=[1])
print(f"Loaded: {len(df)} rows")

# ── Remove pilot (first row = Laura Schuetz) ──────────────────────────────────
df = df.iloc[1:].reset_index(drop=True)
print(f"After removing pilot: {len(df)} rows")

# ── Remove outliers ───────────────────────────────────────────────────────────
with open(OUTLIERS_PATH, "r", encoding="utf-8") as f:
    outlier_data = json.load(f)

outlier_names = [
    o["name"] for o in outlier_data.get("outliers", [])
    if o.get("status") == "is_outlier"
]

removed = df[df["Participant Name"].isin(outlier_names)]["Participant Name"].tolist()
df = df[~df["Participant Name"].isin(outlier_names)].reset_index(drop=True)
print(f"Removed outliers: {', '.join(removed)}")
print(f"After removing outliers: {len(df)} rows")

# ── Keep only ID + post-study columns ─────────────────────────────────────────
keep_cols = [
    "Participant ID",
    "Participant Name",
    "AdaptiveORStatic",
    "AdaptiveRules",
    "Explanation",
    "Customization",
]

df_stripped = df[keep_cols].copy()

# ── Save ──────────────────────────────────────────────────────────────────────
df_stripped.to_excel(OUTPUT_PATH, index=False)
print(f"\n✅ Saved: {OUTPUT_PATH}")
print(f"   {len(df_stripped)} participants × {len(keep_cols)} columns")
print(f"\nColumns: {', '.join(keep_cols)}")
