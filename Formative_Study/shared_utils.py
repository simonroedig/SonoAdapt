"""
Shared Utilities for SonoAdapt Formative Study Analysis
========================================================
Common data-loading, filtering, and transformation functions
used across all analysis scripts in the final/ submission folder.

Extracted from analysis.py to avoid code duplication.
"""
import pandas as pd
import numpy as np
import os

# ==========================================
# CONFIGURATION & MAPPINGS
# ==========================================

# Date Filtering
START_DATE = "2026-06-30"
END_DATE = None
REMOVE_OUTLIERS = True

# Notification Types
NOTIFICATION_TYPES = {
    '1': 'Earcon',
    '2': 'Short Speech',
    '3': 'Rich Speech'
}

# Scenario Definitions (Taguchi L9 Orthogonal Array)
SCENARIO_MAPPING = {
    'A': {'Social': 'Alone',       'Task': 'High mental',   'Soundscape': 'Quiet'},
    'B': {'Social': 'Interactive', 'Task': 'High mental',   'Soundscape': 'Speech'},
    'C': {'Social': 'Alone',       'Task': 'Low',           'Soundscape': 'Music'},
    'D': {'Social': 'Interactive', 'Task': 'High physical', 'Soundscape': 'Music'},
    'E': {'Social': 'Passive',     'Task': 'High physical', 'Soundscape': 'Quiet'},
    'F': {'Social': 'Passive',     'Task': 'Low',           'Soundscape': 'Speech'},
    'G': {'Social': 'Alone',       'Task': 'High physical', 'Soundscape': 'Speech'},
    'H': {'Social': 'Passive',     'Task': 'High mental',   'Soundscape': 'Music'},
    'I': {'Social': 'Interactive', 'Task': 'Low',           'Soundscape': 'Quiet'},
}

# Likert Scale Mapping (text -> numeric)
LIKERT_MAP = {
    "Very difficult to detect": 1, "Difficult to detect": 2, "Somewhat difficult to detect": 3,
    "Neither easy nor difficult to detect": 4, "Somewhat easy to detect": 5, "Easy to detect": 6, "Very easy to detect": 7,
    "Not disruptive at all": 1, "Slightly disruptive": 2, "Somewhat disruptive": 3,
    "Moderately disruptive": 4, "Disruptive": 5, "Very disruptive": 6, "Extremely disruptive": 7,
    "Completely unacceptable": 1, "Unacceptable": 2, "Somewhat unacceptable": 3,
    "Neither acceptable nor unacceptable": 4, "Somewhat acceptable": 5, "Acceptable": 6,
    "Completely acceptable": 7, "Completely Acceptable": 7, "Completel Acceptable": 7,
    "Completely inappropriate": 1, "Inappropriate": 2, "Somewhat inappropriate": 3,
    "Neither appropriate nor inappropriate": 4, "Somewhat appropriate": 5, "Appropriate": 6,
    "Completely appropriate": 7
}


# ==========================================
# DATA LOADING & FILTERING
# ==========================================

def load_and_filter_data(data_path, outliers_path, start_date=START_DATE, end_date=END_DATE, remove_outliers=REMOVE_OUTLIERS):
    """Load survey data from Excel, filter by date range, and remove outlier participants."""
    print("Loading data...")
    df = pd.read_excel(data_path)
    raw_count = len(df)

    df['RecordedDate'] = pd.to_datetime(df['RecordedDate'], errors='coerce', format='mixed')
    if start_date: df = df[df['RecordedDate'] >= pd.to_datetime(start_date)]
    if end_date: df = df[df['RecordedDate'] <= pd.to_datetime(end_date)]

    post_date_count = len(df)
    date_removed_count = raw_count - post_date_count

    removed_outliers_count = 0
    if remove_outliers:
        if os.path.exists(outliers_path):
            with open(outliers_path, 'r') as f:
                outliers = [line.strip() for line in f if line.strip()]
            removed_outliers_count = df['ResponseId'].isin(outliers).sum()
            df = df[~df['ResponseId'].isin(outliers)]
            print(f"Excluded {removed_outliers_count} outliers.")
        else:
            print(f"Outlier file '{outliers_path}' not found.")

    stats = {
        'raw_original': raw_count,
        'date_removed': date_removed_count,
        'post_date': post_date_count,
        'outliers_removed': removed_outliers_count,
        'final': len(df)
    }
    return df, stats


def find_column(columns, sc_key, keyword, t_id):
    """Find a survey column matching the scenario key, keyword, and notification type ID."""
    keyword_lower = keyword.lower()
    for col in columns:
        col_str = str(col)
        if col_str.startswith(f"{sc_key}.") and keyword_lower in col_str.lower() and col_str.endswith(f"_{t_id}"):
            return col_str
    return None


def transform_to_long_format(df):
    """Transform wide-format survey data into long format suitable for statistical analysis."""
    print("Transforming dataset (including Appropriateness)...")
    long_data = []
    df.columns = [str(c).replace('\xa0', ' ').strip() for c in df.columns]

    for _, row in df.iterrows():
        response_id = row.get('ResponseId', 'Unknown')

        for sc_key, sc_attrs in SCENARIO_MAPPING.items():
            for t_id, t_name in NOTIFICATION_TYPES.items():

                col_detect = find_column(df.columns, sc_key, 'detect', t_id)
                col_disrupt = find_column(df.columns, sc_key, 'disrupt', t_id)
                col_social = find_column(df.columns, sc_key, 'social', t_id)
                col_approp = find_column(df.columns, sc_key, 'appropriateness', t_id)

                val_detect = row.get(col_detect, pd.NA) if col_detect else pd.NA
                val_disrupt = row.get(col_disrupt, pd.NA) if col_disrupt else pd.NA
                val_social = row.get(col_social, pd.NA) if col_social else pd.NA
                val_approp = row.get(col_approp, pd.NA) if col_approp else pd.NA

                # Apply likert map if values are text
                if isinstance(val_detect, str): val_detect = LIKERT_MAP.get(val_detect.strip(), val_detect)
                if isinstance(val_disrupt, str): val_disrupt = LIKERT_MAP.get(val_disrupt.strip(), val_disrupt)
                if isinstance(val_social, str): val_social = LIKERT_MAP.get(val_social.strip(), val_social)
                if isinstance(val_approp, str): val_approp = LIKERT_MAP.get(val_approp.strip(), val_approp)

                if pd.isna(val_detect) and pd.isna(val_disrupt) and pd.isna(val_social) and pd.isna(val_approp):
                    continue

                long_data.append({
                    'ResponseId': response_id,
                    'Notification_Type': t_name,
                    'Scenario': sc_key,
                    'Asocial': sc_attrs['Social'],
                    'e_Task': sc_attrs['Task'],
                    'CM': sc_attrs['Soundscape'],
                    'Detectability': pd.to_numeric(val_detect, errors='coerce'),
                    'Disruption': pd.to_numeric(val_disrupt, errors='coerce'),
                    'Social_Acceptability': pd.to_numeric(val_social, errors='coerce'),
                    'Appropriateness': pd.to_numeric(val_approp, errors='coerce')
                })

    return pd.DataFrame(long_data)


def get_data_paths(script_file):
    """Resolve paths to data.xlsx and outliers file relative to the final/ root."""
    script_dir = os.path.dirname(os.path.abspath(script_file))
    final_dir = os.path.dirname(script_dir)  # parent = final/
    data_file = os.path.join(final_dir, "data.xlsx")
    outliers_file = os.path.join(final_dir, "listOfManuallyIdentifiedOutliers.txt")
    return data_file, outliers_file, script_dir, final_dir
