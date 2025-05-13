import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from io import BytesIO

st.set_page_config(page_title="Dynamic Gantt Chart with Holidays", layout="wide")
st.title("📊 Workflow Timeline")

# --- Sidebar Config ---
st.sidebar.header("Configuration")
num_workers = st.sidebar.number_input("Number of Workers", min_value=1, value=4)
hours_per_worker_per_day = st.sidebar.number_input("Hours per Worker per Day", min_value=1, max_value=24, value=10)
start_date = st.sidebar.date_input("Start Date", value=datetime(2025, 6, 2))

# --- Holidays Input ---
st.sidebar.subheader("Holidays (Non-working Days)")
holidays = st.sidebar.text_area("Enter Holidays (comma-separated, in YYYY-MM-DD format)", "").strip()
holidays_list = []
if holidays:
    try:
        holidays_list = [datetime.strptime(date.strip(), "%Y-%m-%d").date() for date in holidays.split(",")]
    except ValueError:
        st.warning("⚠️ Invalid holiday format. Use YYYY-MM-DD.")

# --- Task Input Table ---
st.subheader("📝 Task List ")
st.markdown("➡️ Optionally enter a **Manual Start Date** (YYYY-MM-DD) for each task to fix its schedule.")

default_data = {
    "Task": [
        "Task 1", "Task 2", "Task 3", "Task 4", "Task 5",
        "Task 6", "Task 7", "Task 8", "Task 9", "Task 10"
    ],
    "Total Hours": [80, 50, 200, 20, 150, 120, 60, 100, 80, 40],
    "Workers Requested": [2, 4, 3, 1, 5, 3, 2, 3, 4, 1],
    "Priority": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "Dependencies": [
        "", "Task 1", "Task 2", "Task 3", "Task 1",
        "Task 2", "Task 3", "Task 7", "Task 8", "Task 9"
    ],
    "Manual Start": [""] * 10
}
task_df = pd.DataFrame(default_data)
edited_df = st.data_editor(task_df, num_rows="dynamic", use_container_width=True)

# --- Setup Scheduler ---
task_states = []
for _, row in edited_df.iterrows():
    if pd.isna(row["Task"]) or pd.isna(row["Total Hours"]) or pd.isna(row["Workers Requested"]) or pd.isna(row["Priority"]):
        continue
    if str(row["Task"]).strip() == "" or int(row["Workers Requested"]) <= 0 or int(row["Total Hours"]) <= 0:
        continue

    dependencies = [d.strip() for d in str(row["Dependencies"]).split(",") if d.strip()]
    requested_workers = min(int(row["Workers Requested"]), num_workers)

    manual_start = None
    if isinstance(row.get("Manual Start"), str) and row["Manual Start"].strip():
        try:
            manual_start = datetime.strptime(row["Manual Start"].strip(), "%Y-%m-%d").date()
        except ValueError:
            st.warning(f"⚠️ Invalid manual start date format for task '{row['Task']}'. Use YYYY-MM-DD.")

    task_states.append({
        "Task": row["Task"],
        "Total Hours": int(row["Total Hours"]),
        "Remaining Hours": int(row["Total Hours"]),
        "Requested Workers": requested_workers,
        "Priority": int(row["Priority"]),
        "Dependencies": dependencies,
        "Assigned Workers": 0,
        "Start": None,
        "End": None,
        "In Progress": False,
        "Completed": False,
        "Manual Start": manual_start
    })

current_day = datetime.combine(start_date, datetime.min.time())
active_tasks = []
daily_worker_log = []

max_days = 365
day_count = 0

def is_working_day(date):
    return date.weekday() < 5 and date not in holidays_list  # Mon–Fri only

# --- Ensure start date is working day ---
while not is_working_day(current_day.date()):
    current_day += timedelta(days=1)

# --- Main Scheduling Loop ---
while any(not t["Completed"] for t in task_states) and day_count < max_days:
    while not is_working_day(current_day.date()):
        current_day += timedelta(days=1)
        day_count += 1

    available_workers = num_workers
    daily_log_entry = {"Date": current_day}

    for task in active_tasks[:]:
        if task["Remaining Hours"] <= 0:
            task["Completed"] = True
            task["End"] = current_day
            available_workers += task["Assigned Workers"]
            task["Assigned Workers"] = 0
            active_tasks.remove(task)

    for task in sorted(task_states, key=lambda x: x["Priority"]):
        if task["Completed"] or task["In Progress"]:
            continue
        if task["Manual Start"] and current_day.date() < task["Manual Start"]:
            continue
        can_start = all(dep in [t["Task"] for t in task_states if t["Completed"]] for dep in task["Dependencies"]) if task["Dependencies"] else True
        if can_start:
            task["In Progress"] = True
            if not task["Start"]:
                task["Start"] = datetime.combine(task["Manual Start"], datetime.min.time()) if task["Manual Start"] else current_day
            active_tasks.append(task)

    available_workers = num_workers
    for task in sorted(active_tasks, key=lambda x: x["Priority"]):
        if task["Completed"]:
            continue
        max_needed_today = min(task["Requested Workers"], -(-task["Remaining Hours"] // hours_per_worker_per_day))
        if available_workers <= 0:
            task["Assigned Workers"] = 0
            continue
        assigned = min(available_workers, max_needed_today)
        task["Assigned Workers"] = assigned
        available_workers -= assigned

    for task in task_states:
        if task["In Progress"] and not task["Completed"]:
            task["Remaining Hours"] -= task["Assigned Workers"] * hours_per_worker_per_day
        daily_log_entry[task["Task"]] = task["Assigned Workers"] if task["In Progress"] else 0

    daily_worker_log.append(daily_log_entry)
    current_day += timedelta(days=1)
    day_count += 1

# --- Unscheduled Tasks ---
unscheduled = [t["Task"] for t in task_states if not t["Completed"]]
if unscheduled:
    st.warning("⚠️ These tasks could not be scheduled due to constraints:")
    for t in unscheduled:
        st.write(f"- {t}")

# --- Prepare Schedule Data ---
schedule = []
for task in task_states:
    if task["Start"] and task["End"]:
        schedule.append({
            "Task": task["Task"],
            "Start": task["Start"],
            "End": task["End"],
            "Assigned Workers": task["Requested Workers"],
            "Duration": (task["End"] - task["Start"]).days
        })

# --- Gantt Chart ---
total_days = (max(task["End"] for task in schedule) - min(task["Start"] for task in schedule)).days + 1
fig_width = max(12, total_days * 0.3)
fig, ax = plt.subplots(figsize=(fig_width, len(schedule)))

# Highlight weekends
date_range = pd.date_range(min(task["Start"] for task in schedule), max(task["End"] for task in schedule))
for day in date_range:
    if not is_working_day(day.date()):
        ax.axvspan(day, day + timedelta(days=1), color='lightgrey', alpha=0.3)

for task in schedule:
    start = task["Start"]
    duration = task["Duration"]
    ax.barh(task["Task"], duration, left=start, height=0.5)
    for day in pd.date_range(start, periods=duration):
        workers = next((log[task["Task"]] for log in daily_worker_log if log["Date"] == day), 0)
        if workers > 0:
            ax.text(day + timedelta(hours=12), task["Task"], f'{workers}', va='center', ha='center', color='white',
                    fontweight='bold', fontsize=8)

ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
plt.xticks(rotation=45)
ax.set_xlabel("Date")
ax.set_title("Gantt Chart with Daily Worker Counts (Excluding Weekends & Holidays)")
plt.tight_layout()
plt.grid(True)
st.pyplot(fig)

# --- Daily Worker Table ---
daily_df = pd.DataFrame(daily_worker_log)
daily_df["Date"] = pd.to_datetime(daily_df["Date"])
st.subheader("📅 Daily Worker Allocation Table")
st.dataframe(daily_df.set_index("Date"), use_container_width=True)

# --- Overcapacity Check ---
daily_df["Total Workers"] = daily_df.drop(columns=["Date"]).sum(axis=1)
overcap = daily_df[daily_df["Total Workers"] > num_workers]
if not overcap.empty:
    st.error("⚠️ Overcapacity detected on these days:")
    st.dataframe(overcap[["Date", "Total Workers"]])
else:
    st.success("✅ All worker assignments are within capacity.")

# --- Stacked Chart ---
st.subheader("👷 Daily Worker Allocation (Stacked)")
stacked_fig, stacked_ax = plt.subplots(figsize=(12, 6))
bottom = [0] * len(daily_df)
for task in [t["Task"] for t in task_states]:
    values = daily_df[task].values
    stacked_ax.bar(daily_df["Date"], values, bottom=bottom, label=task)
    bottom = [b + v for b, v in zip(bottom, values)]

stacked_ax.set_ylabel("Workers")
stacked_ax.set_title("Daily Worker Allocation by Task")
stacked_ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
stacked_ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
stacked_ax.legend()
plt.xticks(rotation=45)
plt.tight_layout()
st.pyplot(stacked_fig)

# --- Excel Export ---
output_df = pd.DataFrame(schedule)
output_df["Start"] = output_df["Start"].dt.strftime("%Y-%m-%d")
output_df["End"] = output_df["End"].dt.strftime("%Y-%m-%d")
buffer = BytesIO()
with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
    output_df.to_excel(writer, index=False, sheet_name="Schedule")
    daily_df.to_excel(writer, index=False, sheet_name="Daily Allocation")

st.download_button(
    label="📥 Download Excel Schedule",
    data=buffer,
    file_name="Dynamic_Gantt_Timeline_with_Holidays.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
