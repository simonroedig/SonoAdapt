import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from collections import Counter
import re
import os

# Resolve data path relative to this script's location (parent = final/)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_FINAL_DIR = os.path.dirname(_SCRIPT_DIR)
_DATA_PATH = os.path.join(_FINAL_DIR, "data.xlsx")

# --- Page Configuration ---
st.set_page_config(page_title="Smart Glasses Audio Notifs", page_icon="🕶️", layout="wide")

# --- Define Full Likert Scales ---
SCALE_AGREE = [
    'Strongly disagree', 'Disagree', 'Somewhat disagree', 
    'Neither agree nor disagree', 'Somewhat agree', 'Agree', 'Strongly agree'
]
SCALE_APPROPRIATE = [
    'Completely inappropriate', 'Inappropriate', 'Somewhat inappropriate', 
    'Neither appropriate nor inappropriate', 'Somewhat appropriate', 'Appropriate', 'Completely appropriate'
]
SCALE_DETECT = [
    'Very difficult to detect', 'Difficult to detect', 'Somewhat difficult to detect', 
    'Neither easy nor difficult to detect', 'Somewhat easy to detect', 'Easy to detect', 'Very easy to detect'
]
SCALE_DISRUPT = [
    'Not disruptive at all', 'Slightly disruptive', 'Somewhat disruptive', 
    'Moderately disruptive', 'Disruptive', 'Very disruptive', 'Extremely disruptive'
]
SCALE_SOCIAL = [
    'Completely unacceptable', 'Unacceptable', 'Somewhat unacceptable', 
    'Neither acceptable nor unacceptable', 'Somewhat acceptable', 'Acceptable', 'Completely Acceptable'
]
SCALE_ENGLISH = [
    'Cannot understand at all', 'Understand very little', 'Understand somewhat', 
    'Understand moderately well', 'Understand well', 'Understand very well', 'Understand perfectly'
]
SCALE_PREF_MATRIX = [
    'Mute (Do not notify me auditorily at all) 🔕', 
    "Sound Only 'Version 1' 🔔", 
    "Speech 'Version 2' (Sender) 🗣️", 
    "Speech 'Version 3' (Sender + Full/Summarized Content) 🗣️🗣️"
]
SCALE_DELAY_MATRIX = [
    'No delay: Must interrupt me immediately, regardless of my situation.',
    'Brief delay (Seconds): Can wait for a quick safe moment (e.g., until I finish crossing the street, silence).',
    'Moderate delay (Minutes): Can wait until I finish my current task (e.g., finishing an email or a conversation).',
    'Indefinite delay (Hours): Can be withheld entirely until I manually check my phone or ask the device.'
]

# --- Helper Functions ---
@st.cache_data
def load_data(filepath):
    try:
        raw_df = pd.read_excel(filepath)
        descriptions = raw_df.iloc[0].to_dict()
        df = raw_df.iloc[1:].reset_index(drop=True)
        # Clean column names (remove non-breaking spaces)
        df.columns = [str(c).replace('\xa0', ' ').strip() for c in df.columns]
        return df, descriptions
    except Exception as e:
        return None, str(e)

def get_counts_with_ids(df, col, category_order=None):
    """Aggregates counts and maps ResponseIds for chart tooltips."""
    has_id = 'ResponseId' in df.columns
    counts = df[col].value_counts().reset_index()
    counts.columns = [col, 'Count']
    
    if has_id:
        grouped = df.dropna(subset=[col]).groupby(col)['ResponseId'].apply(lambda x: ', '.join(x.astype(str))).reset_index()
        grouped.columns = [col, 'Participants']
        counts = pd.merge(counts, grouped, on=col, how='left')
    else:
        counts['Participants'] = ""
        
    if category_order:
        cat_df = pd.DataFrame({col: category_order})
        counts = pd.merge(cat_df, counts, on=col, how='left').fillna({'Count': 0, 'Participants': ''})
    return counts

def plot_bar(df, col, title, orientation='v', category_order=None):
    if col not in df.columns: return
    
    counts = get_counts_with_ids(df, col, category_order)
    
    fig = px.bar(counts, x=col if orientation=='v' else 'Count', 
                 y='Count' if orientation=='v' else col, 
                 title=title, text='Count', color=col,
                 hover_data=['Participants'],
                 color_discrete_sequence=px.colors.qualitative.Pastel)
    
    if category_order:
        if orientation == 'v':
            fig.update_xaxes(categoryorder='array', categoryarray=category_order)
        else:
            fig.update_yaxes(categoryorder='array', categoryarray=category_order)

    fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)

def plot_multiple_choice(df, col, title):
    if col not in df.columns: return
    
    flat_records = []
    for _, row in df.dropna(subset=[col]).iterrows():
        items = re.split(r',(?!\s)', str(row[col]))
        for item in items:
            clean_item = item.strip()
            if clean_item:
                flat_records.append({
                    'Response': clean_item, 
                    'Participant': str(row['ResponseId']) if 'ResponseId' in df.columns else ''
                })
                
    flat_df = pd.DataFrame(flat_records)
    if flat_df.empty: return
    
    counts = flat_df.groupby('Response').agg(
        Count=('Participant', 'size'),
        Participants=('Participant', lambda x: ', '.join(x))
    ).reset_index().sort_values('Count', ascending=True)

    fig = px.bar(counts, x='Count', y='Response', orientation='h', title=title, text='Count',
                 color='Response', hover_data=['Participants'], 
                 color_discrete_sequence=px.colors.qualitative.Set2)
    fig.update_layout(showlegend=False, yaxis={'categoryorder':'total ascending'})
    st.plotly_chart(fig, use_container_width=True)

def plot_scenario_comparison(df, prefix, metric, title, category_order=None):
    col1, col2, col3 = f"{prefix}. {metric}_1", f"{prefix}. {metric}_2", f"{prefix}. {metric}_3"
    if not any(c in df.columns for c in [col1, col2, col3]): return

    counts_dict = []
    versions = {'🔔 V1 (Sound)': col1, '🗣️ V2 (Sender)': col2, '🗣️🗣️ V3 (Full)': col3}
    
    for name, col in versions.items():
        if col in df.columns:
            merged = get_counts_with_ids(df, col, category_order)
            merged['Version'] = name
            merged.rename(columns={col: 'Rating'}, inplace=True)
            counts_dict.append(merged)
            
    if not counts_dict: return
            
    counts_df = pd.concat(counts_dict)
    fig = px.bar(counts_df, x='Rating', y='Count', color='Version', barmode='group', title=title, 
                 hover_data=['Participants'],
                 color_discrete_sequence=['#F4D03F', '#AF7AC5', '#5B2C6F'])
                 
    if category_order:
        fig.update_xaxes(categoryorder='array', categoryarray=category_order)
        
    fig.update_layout(xaxis_title="Rating", yaxis_title="Number of Participants", legend_title="Version")
    st.plotly_chart(fig, use_container_width=True)

def plot_matrix(df, cols, labels, title, barmode='group', category_order=None):
    melted = []
    for col, label in zip(cols, labels):
        if col in df.columns:
            merged = get_counts_with_ids(df, col, category_order)
            merged.rename(columns={col: 'Preference'}, inplace=True)
            merged['Message Type'] = label
            melted.append(merged)
    if not melted: return
    
    plot_df = pd.concat(melted)
    fig = px.bar(plot_df, x='Message Type', y='Count', color='Preference', 
                 barmode=barmode, title=title, hover_data=['Participants'],
                 color_discrete_sequence=px.colors.qualitative.Safe,
                 category_orders={'Preference': category_order} if category_order else None)
    st.plotly_chart(fig, use_container_width=True)

def display_text_table(df, text_col, title, extra_cols=None):
    if text_col not in df.columns: return
    cols_to_get = ['ResponseId'] + (extra_cols if extra_cols else []) + [text_col]
    available_cols = [c for c in cols_to_get if c in df.columns]
    
    temp_df = df[available_cols].dropna(subset=[text_col])
    temp_df = temp_df[temp_df[text_col].astype(str).str.strip() != ""]
    if temp_df.empty: return
    
    rename_dict = {'ResponseId': 'Participant ID'}
    if extra_cols:
        for c in extra_cols: rename_dict[c] = c.split('.')[-1].strip()
    
    temp_df = temp_df.rename(columns=rename_dict)
    
    with st.expander(f"📖 {title} ({len(temp_df)} responses)"):
        if extra_cols and extra_cols[0] in rename_dict:
            temp_df = temp_df.sort_values(by=rename_dict[extra_cols[0]])
        st.dataframe(temp_df, use_container_width=True, hide_index=True)


# --- Main App ---
st.title("🕶️ Auditory Notifications on Smart Glasses - Dashboard")
st.markdown("Interactive analysis of the Qualtrics user study results. **Hover over bars to see Participant IDs.**")

df, descriptions = load_data(_DATA_PATH)

if df is None:
    st.error("Could not load `data.xlsx`. Make sure it's in the same folder.")
    st.stop()

# --- Sidebar Filters ---
st.sidebar.header("⚙️ Data Filters")

date_col = next((c for c in ['RecordedDate', 'StartDate', 'EndDate'] if c in df.columns), None)
if date_col:
    df['__temp_date'] = pd.to_datetime(df[date_col], errors='coerce')
    min_date = df['__temp_date'].min()
    max_date = df['__temp_date'].max()
    
    import datetime
    if pd.notna(min_date) and pd.notna(max_date):
        min_d = min_date.date()
        max_d = max_date.date()
        
        st.sidebar.markdown("### 📅 Timeframe Filter")
        st.sidebar.caption("Note: The earliest recording with the full release is June 30, 2026. Earlier dates may contain initial test recordings.")
        
        default_start = datetime.date(2026, 6, 30)
        if default_start < min_d:
            default_start = min_d
        elif default_start > max_d:
            default_start = max_d

        date_selection = st.sidebar.date_input(
            "Select range to exclude test data:",
            value=(default_start, max_d),
            min_value=min_d,
            max_value=max_d
        )
        
        if len(date_selection) == 2:
            start_d, end_d = date_selection
            mask = (df['__temp_date'].dt.date >= start_d) & (df['__temp_date'].dt.date <= end_d)
            df = df[mask]
            
    df = df.drop(columns=['__temp_date'])

st.sidebar.markdown("---")

outliers_file = "listOfManuallyIdentifiedOutliers.txt"
outliers = []
try:
    with open(outliers_file, "r", encoding="utf-8") as f:
        outliers = [line.strip() for line in f if line.strip()]
except FileNotFoundError:
    pass

if outliers:
    st.sidebar.markdown("### 🚫 Outliers")
    with st.sidebar.expander(f"View {len(outliers)} manually identified outliers"):
        for out_id in outliers:
            st.markdown(f"- {out_id}")
    
    exclude_outliers = st.sidebar.checkbox("Exclude identified outliers", value=True)
    if exclude_outliers and 'ResponseId' in df.columns:
        df = df[~df['ResponseId'].isin(outliers)]

if 'ResponseId' in df.columns:
    all_ids = df['ResponseId'].dropna().tolist()
    selected_ids = st.sidebar.multiselect("Select Participants (ResponseId)", all_ids, default=all_ids)
    df = df[df['ResponseId'].isin(selected_ids)]

st.sidebar.success(f"**{len(df)}** participants matching criteria.")

# --- Export/Log Statistics ---
import json

try:
    log_data = {
        "study_statistics": {
            "total_participants": len(df)
        }
    }
    
    if 'Age' in df.columns:
        ages = pd.to_numeric(df['Age'], errors='coerce').dropna()
        log_data["age"] = {
            "n": len(ages),
            "mean": round(ages.mean(), 2) if len(ages) > 0 else None,
            "sd": round(ages.std(), 2) if len(ages) > 1 else None,
            "min": int(ages.min()) if len(ages) > 0 else None,
            "max": int(ages.max()) if len(ages) > 0 else None
        }

    if 'Gender' in df.columns:
        genders = df['Gender'].dropna()
        total_genders = len(genders)
        log_data["gender"] = {
            "n": total_genders,
            "breakdown": {}
        }
        if total_genders > 0:
            for val, count in genders.value_counts().items():
                log_data["gender"]["breakdown"][val] = {
                    "n": int(count),
                    "percentage": round((count / total_genders) * 100, 1)
                }

    if 'English Skill_1' in df.columns:
        english = df['English Skill_1'].dropna()
        total_english = len(english)
        log_data["english_proficiency"] = {
            "n": total_english,
            "breakdown": {}
        }
        if total_english > 0:
            eng_counts = english.value_counts()
            for level in SCALE_ENGLISH:
                if level in eng_counts:
                    count = eng_counts[level]
                    log_data["english_proficiency"]["breakdown"][level] = {
                        "n": int(count),
                        "percentage": round((count / total_english) * 100, 1)
                    }
            for val, count in eng_counts.items():
                if val not in SCALE_ENGLISH:
                    log_data["english_proficiency"]["breakdown"][val] = {
                        "n": int(count),
                        "percentage": round((count / total_english) * 100, 1)
                    }

    if 'Glass Experience_1' in df.columns:
        glass_exp = df['Glass Experience_1'].dropna()
        total_glass = len(glass_exp)
        log_data["smart_glass_experience"] = {
            "n": total_glass,
            "breakdown": {}
        }
        if total_glass > 0:
            for val, count in glass_exp.value_counts().items():
                log_data["smart_glass_experience"]["breakdown"][val] = {
                    "n": int(count),
                    "percentage": round((count / total_glass) * 100, 1)
                }

    if 'Which Notif Auditory' in df.columns:
        auditory_apps = df['Which Notif Auditory'].dropna()
        total_auditory = len(auditory_apps)
        log_data["desired_apps_for_auditory_notifications"] = {
            "n_participants": total_auditory,
            "breakdown": {}
        }
        if total_auditory > 0:
            app_counts = {}
            for val in auditory_apps:
                items = re.split(r',(?!\s)', str(val))
                for item in items:
                    clean_item = item.strip()
                    if clean_item:
                        app_counts[clean_item] = app_counts.get(clean_item, 0) + 1
            for app_name, count in sorted(app_counts.items(), key=lambda x: x[1], reverse=True):
                log_data["desired_apps_for_auditory_notifications"]["breakdown"][app_name] = {
                    "n": int(count),
                    "percentage": round((count / total_auditory) * 100, 1)
                }

    for col, key_name in [('Notif ImprtancUrgent_1', 'only_notify_important'), 
                          ('Notif ImprtancUrgent_2', 'only_notify_urgent')]:
        if col in df.columns:
            series = df[col].dropna()
            total = len(series)
            log_data[key_name] = {
                "n": total,
                "breakdown": {}
            }
            if total > 0:
                counts = series.value_counts()
                for level in SCALE_AGREE:
                    if level in counts:
                        c = counts[level]
                        log_data[key_name]["breakdown"][level] = {
                            "n": int(c),
                            "percentage": round((c / total) * 100, 1)
                        }
                for val, c in counts.items():
                    if val not in SCALE_AGREE:
                        log_data[key_name]["breakdown"][val] = {
                            "n": int(c),
                            "percentage": round((c / total) * 100, 1)
                        }

    if 'Preference' in df.columns:
        pref = df['Preference'].dropna()
        total_pref = len(pref)
        log_data["general_notification_preference"] = {
            "n": total_pref,
            "breakdown": {},
            "reasons": {}
        }
        if total_pref > 0:
            for val, count in pref.value_counts().items():
                log_data["general_notification_preference"]["breakdown"][val] = {
                    "n": int(count),
                    "percentage": round((count / total_pref) * 100, 1)
                }
        
        if 'Preference Text' in df.columns:
            pref_df = df[['Preference', 'Preference Text']].dropna(subset=['Preference Text'])
            pref_df = pref_df[pref_df['Preference Text'].astype(str).str.strip() != ""]
            for p_val in pref_df['Preference'].unique():
                subset = pref_df[pref_df['Preference'] == p_val]
                log_data["general_notification_preference"]["reasons"][p_val] = [str(text).strip() for text in subset['Preference Text']]

    for col, key_name in [('Speech Opinion_1', 'assumption_speech_means_urgent'), 
                          ('Speech Opinion_2', 'acceptable_read_loud_unprompted')]:
        if col in df.columns:
            series = df[col].dropna()
            total = len(series)
            log_data[key_name] = {
                "n": total,
                "breakdown": {}
            }
            if total > 0:
                counts = series.value_counts()
                for level in SCALE_AGREE:
                    if level in counts:
                        c = counts[level]
                        log_data[key_name]["breakdown"][level] = {
                            "n": int(c),
                            "percentage": round((c / total) * 100, 1)
                        }
                for val, c in counts.items():
                    if val not in SCALE_AGREE:
                        log_data[key_name]["breakdown"][val] = {
                            "n": int(c),
                            "percentage": round((c / total) * 100, 1)
                        }

    if 'Speech Opinion 2' in df.columns:
        factors = df['Speech Opinion 2'].dropna()
        total_factors = len(factors)
        log_data["factors_influencing_speech_attitude"] = {
            "n_participants": total_factors,
            "breakdown": {}
        }
        if total_factors > 0:
            fact_counts = {}
            for val in factors:
                items = re.split(r',(?!\s)', str(val))
                for item in items:
                    clean_item = item.strip()
                    if clean_item:
                        fact_counts[clean_item] = fact_counts.get(clean_item, 0) + 1
            for f_name, count in sorted(fact_counts.items(), key=lambda x: x[1], reverse=True):
                log_data["factors_influencing_speech_attitude"]["breakdown"][f_name] = {
                    "n": int(count),
                    "percentage": round((count / total_factors) * 100, 1)
                }

    if 'Maximum Length' in df.columns:
        max_len = df['Maximum Length'].dropna()
        total_max = len(max_len)
        log_data["maximum_acceptable_length"] = {
            "n_participants": total_max,
            "breakdown": {}
        }
        if total_max > 0:
            len_counts = {}
            for val in max_len:
                items = re.split(r',(?!\s)', str(val))
                for item in items:
                    clean_item = item.strip()
                    if clean_item:
                        len_counts[clean_item] = len_counts.get(clean_item, 0) + 1
            for l_name, count in sorted(len_counts.items(), key=lambda x: x[1], reverse=True):
                log_data["maximum_acceptable_length"]["breakdown"][l_name] = {
                    "n": int(count),
                    "percentage": round((count / total_max) * 100, 1)
                }

    if 'Summary Acceptance_1' in df.columns:
        series = df['Summary Acceptance_1'].dropna()
        total = len(series)
        log_data["acceptance_ai_summarization"] = {
            "n": total,
            "breakdown": {}
        }
        if total > 0:
            counts = series.value_counts()
            for level in SCALE_AGREE:
                if level in counts:
                    c = counts[level]
                    log_data["acceptance_ai_summarization"]["breakdown"][level] = {
                        "n": int(c),
                        "percentage": round((c / total) * 100, 1)
                    }
            for val, c in counts.items():
                if val not in SCALE_AGREE:
                    log_data["acceptance_ai_summarization"]["breakdown"][val] = {
                        "n": int(c),
                        "percentage": round((c / total) * 100, 1)
                    }

    with open("appDataLogs.json", "w", encoding="utf-8") as log_file:
        json.dump(log_data, log_file, indent=4, ensure_ascii=False)

except Exception as e:
    st.sidebar.error(f"Error writing to appDataLogs.json: {e}")


# --- Dashboard Tabs ---
tabs = st.tabs([
    "🖥️ Intro Questions",
    "👥 Demographics & Background", 
    "🧠 Familiarization", 
    "🎬 Scenarios (A-I)", 
    "🧮 Final Matrices & Feedback",
    "⏱️ Timing Analysis",
    "⚠️ Attention Checks"
])

# ==========================================
# TAB 1: Intro Questions
# ==========================================
with tabs[0]:
    st.header("Introductory & Tech Checks")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        plot_bar(df, 'Desktop Laptop', "Device Used (Desktop/Laptop)")
    with c2:
        plot_bar(df, 'Headphones', "Using Headphones or Earbuds?")
    with c3:
        plot_bar(df, 'Headphone Check', "Audio Channel Check (Left/Right/Both)")

# ==========================================
# TAB 2: Demographics & Background
# ==========================================
with tabs[1]:
    st.header("Participant Demographics")
    c1, c2, c3 = st.columns(3)
    with c1:
        if 'Age' in df.columns:
            fig_age = px.histogram(df, x='Age', title="Age Distribution", nbins=15, hover_data=['ResponseId'], color_discrete_sequence=['#5DADE2'])
            st.plotly_chart(fig_age, use_container_width=True)
    with c2:
        if 'Gender' in df.columns:
            fig_gender = px.pie(df, names='Gender', title="Gender Breakdown", hover_data=['ResponseId'], hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_gender, use_container_width=True)
    with c3:
        plot_bar(df, 'English Skill_1', "English Proficiency", category_order=SCALE_ENGLISH)

    plot_bar(df, 'Language', "Language / Country of Origin", orientation='h')
    display_text_table(df, 'Impairment_2_TEXT', "Hearing Impairment Details")

    st.divider()
    st.subheader("Baseline Settings & Smart Glass Familiarity")
    
    c4, c5 = st.columns(2)
    with c4:
        plot_bar(df, 'My Notif Settings', "Standard Smartphone Notification Setting", orientation='h')
    with c5:
        plot_multiple_choice(df, 'My Notif SettingsWhy', "Reasons for Chosen Setting")
    display_text_table(df, 'My Notif SettingsWhy_6_TEXT', "Other Specific Settings (Text)")

    plot_bar(df, 'Glass Experience_1', "Smart Glass Experience")

    st.divider()
    st.subheader("Auditory Preferences Independent of Context")
    plot_multiple_choice(df, 'Which Notif Auditory', "Apps Desired for Auditory Notifications via Glasses")
    display_text_table(df, 'Which Notif Auditory_9_TEXT', "Other Specific Apps (Text)")
    
    c6, c7 = st.columns(2)
    with c6:
        plot_bar(df, 'Notif ImprtancUrgent_1', "Only notify me for IMPORTANT messages", category_order=SCALE_AGREE)
    with c7:
        plot_bar(df, 'Notif ImprtancUrgent_2', "Only notify me for URGENT messages", category_order=SCALE_AGREE)


# ==========================================
# TAB 3: Familiarization
# ==========================================
with tabs[2]:
    st.header("Familiarization Checks & Preferences")
    
    plot_bar(df, 'Sender Check', "Sender Check (Which versions inform about sender?)")
    
    st.divider()
    st.subheader("General Notification Preference (Independent of Context)")
    plot_bar(df, 'Preference', "Preferred Version")
    display_text_table(df, 'Preference Text', "Why prefer chosen version?", extra_cols=['Preference'])
    
    st.divider()
    st.subheader("Attitudes Towards Speech Output")
    c1, c2 = st.columns(2)
    with c1:
        plot_bar(df, 'Speech Opinion_1', "Assumption: If speech, it must be urgent", category_order=SCALE_AGREE)
    with c2:
        plot_bar(df, 'Speech Opinion_2', "Acceptable to read out loud without explicit request?", category_order=SCALE_AGREE)
        
    plot_multiple_choice(df, 'Speech Opinion 2', "Factors influencing attitude towards speech output")
    display_text_table(df, 'Speech Opinion 2_10_TEXT', "Other factors influencing speech attitude (Text)")
    
    c3, c4 = st.columns(2)
    with c3:
        plot_multiple_choice(df, 'Maximum Length', "Maximum Acceptable Length for Spoken Notifications")
        display_text_table(df, 'Maximum Length_7_TEXT', "Other Maximum Length specs (Text)")
    with c4:
        plot_bar(df, 'Summary Acceptance_1', "Acceptance of AI Summarization for LONG messages", category_order=SCALE_AGREE)


# ==========================================
# TAB 4: Contextual Scenarios (A-I)
# ==========================================
with tabs[3]:
    st.header("Contextual Scenarios")
    
    scenarios = {
        'A': 'Home Alone Computer',
        'B': 'Team Meeting',
        'C': 'Home Music',
        'D': 'Tent',
        'E': 'Cycle City',
        'F': 'Grocery Shopping',
        'G': 'Cooking Dinner',
        'H': 'Study Coffee Shop',
        'I': 'Quiet Friend Over'
    }
    
    active_scenarios = {k: v for k, v in scenarios.items() if any(col.startswith(f"{k}.") for col in df.columns)}
    
    if active_scenarios:
        scenario_tabs = st.tabs([f"{k}: {v}" for k, v in active_scenarios.items()])
        
        for idx, (prefix, name) in enumerate(active_scenarios.items()):
            with scenario_tabs[idx]:
                st.subheader(f"Scenario {prefix}: {name}")
                
                c1, c2 = st.columns(2)
                with c1:
                    plot_scenario_comparison(df, prefix, 'Appropriateness', "Appropriateness", category_order=SCALE_APPROPRIATE)
                    plot_scenario_comparison(df, prefix, 'Disruption', "Disruption Level", category_order=SCALE_DISRUPT)
                with c2:
                    plot_scenario_comparison(df, prefix, 'Detectability', "Detectability", category_order=SCALE_DETECT)
                    plot_scenario_comparison(df, prefix, 'Social', "Social Acceptability", category_order=SCALE_SOCIAL)

                st.divider()
                
                c3, c4, c5 = st.columns(3)
                with c3:
                    plot_bar(df, f"{prefix}. Overall", "Overall Preferred Version")
                with c4:
                    plot_bar(df, f"{prefix}. Timing", "Preferred Delivery Timing")
                with c5:
                    plot_bar(df, f"{prefix}. Timing Follow", "If Delayed, Preferred Version")
                    
                st.markdown("**Factors Influencing Choice:**")
                plot_multiple_choice(df, f"{prefix}. Overall Why", f"Why did they choose this? (Scenario {prefix})")
                
                st.divider()
                st.subheader("💬 Participant Reasoning (Correlated with their Choices)")
                
                col_overall = f"{prefix}. Overall"
                col_overall_txt = f"{prefix}. Why Text"
                display_text_table(df, col_overall_txt, "Reasons for Overall Preference", extra_cols=[col_overall])
                
                display_text_table(df, f"{prefix}. Overall Why_6_TEXT", "Other factors influencing choice (Text)", extra_cols=[col_overall])

                col_timing = f"{prefix}. Timing"
                col_timing_fol = f"{prefix}. Timing Follow"
                col_timing_txt = f"{prefix}. Why Timing Text"
                display_text_table(df, col_timing_txt, "Reasons for Delivery Timing & Delayed Version", extra_cols=[col_timing, col_timing_fol])
                
                display_text_table(df, f"{prefix}. Timing_5_TEXT", "Other specified timing (Text)", extra_cols=[col_timing])
    else:
        st.warning("No scenario data (A-I) found in the dataset.")


# ==========================================
# TAB 5: Final Matrices & Feedback
# ==========================================
with tabs[4]:
    st.header("Final Notification Matrices")
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Delivery Modality Preference Matrix")
        pref_cols = ['Preference Matrix_1', 'Preference Matrix_2', 'Preference Matrix_3', 'Preference Matrix_4']
        pref_labels = ['Simple Ack (e.g. "Ok")', 'Routine Update', 'Great News', 'Time-sensitive / Action req.']
        plot_matrix(df, pref_cols, pref_labels, "Preferred Version by Message Type", category_order=SCALE_PREF_MATRIX)
        
    with c2:
        st.subheader("Interruption Delay Tolerance Matrix")
        delay_cols = ['Delay Matrix_1', 'Delay Matrix_2', 'Delay Matrix_3', 'Delay Matrix_4']
        plot_matrix(df, delay_cols, pref_labels, "Maximum Delay Tolerance by Message Type", category_order=SCALE_DELAY_MATRIX)

    st.divider()
    st.header("💬 General & Additional Open Text Feedback")
    st.info("These responses represent overall feedback and general concerns not tied to a specific scenario.")
    
    display_text_table(df, 'Final', "Final Additional Comments & Thoughts")


# ==========================================
# TAB 6: Timing Analysis
# ==========================================
with tabs[5]:
    st.header("⏱️ Survey Timing & Duration Analysis")
    st.markdown("Use this tab to identify participants who may have sped through the survey or skipped listening to the audio clips.")

    # 1. Total Duration
    duration_col = next((c for c in df.columns if 'Duration' in str(c)), None)
    if duration_col:
        st.subheader("Total Survey Duration")
        df['__temp_duration'] = pd.to_numeric(df[duration_col], errors='coerce')
        
        # Plot Histogram of total duration (with manual binning to show IDs)
        df_clean = df.dropna(subset=['__temp_duration']).copy()
        if not df_clean.empty and 'ResponseId' in df_clean.columns:
            df_clean['bin'] = pd.cut(df_clean['__temp_duration'], bins=20)
            
            bin_stats = df_clean.groupby('bin', observed=False).agg(
                Count=('__temp_duration', 'size'),
                Participants=('ResponseId', lambda x: ', '.join(x.astype(str)))
            ).reset_index()
            
            bin_stats['Duration Range'] = bin_stats['bin'].apply(
                lambda x: f"{max(0, int(x.left))} - {int(x.right)}s<br>({max(0, x.left)/60:.1f} - {x.right/60:.1f}m)" if pd.notna(x) else ""
            )
            
            fig_dur = px.bar(bin_stats, x='Duration Range', y='Count', 
                             title="Distribution of Total Duration",
                             labels={'Duration Range': 'Duration'},
                             hover_data=['Participants'],
                             color_discrete_sequence=['#E74C3C'])
            fig_dur.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig_dur, use_container_width=True)
        else:
            fig_dur = px.histogram(df, x='__temp_duration', nbins=20, 
                                   title="Distribution of Total Duration (Seconds)",
                                   labels={'__temp_duration': 'Seconds'},
                                   hover_data=['ResponseId'] if 'ResponseId' in df.columns else None,
                                   color_discrete_sequence=['#E74C3C'])
            st.plotly_chart(fig_dur, use_container_width=True)
        
        # Show min/max/avg
        avg_dur = df['__temp_duration'].mean()
        med_dur = df['__temp_duration'].median()
        st.write(f"**Average Duration:** {avg_dur/60:.1f} minutes | **Median Duration:** {med_dur/60:.1f} minutes")

    st.divider()

    # 2. Time Spent Per Block (Page Submit metrics)
    submit_cols = [c for c in df.columns if 'Page Submit' in str(c)]
    
    if submit_cols:
        st.subheader("Time Spent per Survey Block (Seconds)")
        
        # Reshape data to plot it easily
        timing_df = df[['ResponseId'] + submit_cols].melt(id_vars='ResponseId', var_name='Block', value_name='Seconds')
        timing_df['Seconds'] = pd.to_numeric(timing_df['Seconds'], errors='coerce')
        timing_df = timing_df.dropna(subset=['Seconds'])
        
        # Clean up block names for the graph
        timing_df['Block'] = timing_df['Block'].str.replace('_Page Submit', '', regex=False).str.replace(' Timing', '', regex=False)
        
        # Boxplot to show distribution and outliers
        fig_time = px.box(timing_df, x='Block', y='Seconds', points="all", 
                          hover_data=['ResponseId'], 
                          title="Distribution of Time Spent by Block",
                          color_discrete_sequence=['#3498DB'])
        st.plotly_chart(fig_time, use_container_width=True)
        
        # Data summary table
        st.markdown("**Summary Statistics by Block:**")
        summary_time = timing_df.groupby('Block')['Seconds'].agg(['mean', 'median', 'min', 'max']).round(2).reset_index()
        st.dataframe(summary_time, use_container_width=True)
    else:
        st.info("No detailed 'Page Submit' timing columns found in the dataset. Ensure you exported the timing data variables from Qualtrics.")


# ==========================================
# TAB 7: Attention Checks (NEW)
# ==========================================
with tabs[6]:
    st.header("⚠️ Attention Checks")
    st.markdown("Review the responses to the embedded attention checks to identify potential outliers or unengaged participants. **Hover over the bars to see Participant IDs.**")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if 'Attention Check 1_1' in df.columns:
            st.subheader("Attention Check 1")
            st.caption("Expected answer: **Somewhat disagree**")
            plot_bar(df, 'Attention Check 1_1', "", category_order=SCALE_AGREE)
        else:
            st.warning("Column 'Attention Check 1_1' not found in dataset.")
            
    with col2:
        if 'Attention Check 2_1' in df.columns:
            st.subheader("Attention Check 2")
            st.caption("Expected answer: **Agree**")
            plot_bar(df, 'Attention Check 2_1', "", category_order=SCALE_AGREE)
        else:
            st.warning("Column 'Attention Check 2_1' not found in dataset.")