import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


load_dotenv()

IST = ZoneInfo("Asia/Kolkata")


def get_sync_database_url() -> str:
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL is missing in .env")
    return database_url.replace("+asyncpg", "")


@st.cache_resource
def get_engine():
    return create_engine(get_sync_database_url(), pool_pre_ping=True)


def fetch_slots(is_open: bool) -> pd.DataFrame:
    query = text(
        """
        SELECT id, slot_start, slot_end, is_open
        FROM "Availability_Schedules"
        WHERE clinic_id = :clinic_id AND is_open = :is_open
        ORDER BY slot_start ASC
        """
    )
    try:
        return pd.read_sql(query, get_engine(), params={"clinic_id": 1, "is_open": is_open})
    except Exception as exc:
        st.error(f"Database connection failed: {exc}")
        return pd.DataFrame(columns=["id", "slot_start", "slot_end", "is_open"])


def fetch_booked_appointments() -> pd.DataFrame:
    query = text(
        """
        SELECT
            s.id AS slot_id,
            s.slot_start,
            s.slot_end,
            a.id AS booking_id,
            a.status AS appointment_status,
            p.full_name AS patient_name,
            p.phone AS patient_phone
        FROM "Availability_Schedules" s
        LEFT JOIN "Appointments" a ON a.schedule_id = s.id
        LEFT JOIN "Patients" p ON p.id = a.patient_id
        WHERE s.clinic_id = :clinic_id AND s.is_open = FALSE
        ORDER BY s.slot_start ASC
        """
    )
    try:
        return pd.read_sql(query, get_engine(), params={"clinic_id": 1})
    except Exception as exc:
        st.error(f"Database connection failed: {exc}")
        return pd.DataFrame(
            columns=[
                "slot_id",
                "slot_start",
                "slot_end",
                "booking_id",
                "appointment_status",
                "patient_name",
                "patient_phone",
            ]
        )


def apply_time_filter(df: pd.DataFrame, filter_key: str) -> pd.DataFrame:
    if df.empty or "slot_start" not in df.columns or filter_key == "All":
        return df

    local_times = pd.to_datetime(df["slot_start"], utc=True).dt.tz_convert(IST)
    local_dates = local_times.dt.date
    today = datetime.now(IST).date()

    if filter_key == "Today":
        return df[local_dates == today].copy()

    if filter_key == "This Week":
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        return df[(local_dates >= week_start) & (local_dates <= week_end)].copy()

    return df


def format_slots(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    def pretty(value) -> str:
        local_dt = pd.to_datetime(value, utc=True).tz_convert(IST)
        return local_dt.strftime("%A, %b %d - %I:%M %p")

    formatted = df.copy()
    formatted["slot_start"] = [
        pretty(value)
        for value in formatted["slot_start"]
    ]
    formatted["slot_end"] = [
        pretty(value)
        for value in formatted["slot_end"]
    ]
    formatted["is_open"] = [
        "🟢 Open" if bool(value) else "🟠 Filled"
        for value in formatted["is_open"]
    ]
    formatted = formatted.rename(
        columns={
            "id": "Slot ID",
            "slot_start": "Start",
            "slot_end": "End",
            "is_open": "Open",
        }
    )
    return formatted


def format_booked_appointments(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    def pretty(value) -> str:
        local_dt = pd.to_datetime(value, utc=True).tz_convert(IST)
        return local_dt.strftime("%A, %b %d - %I:%M %p")

    formatted = df.copy()
    formatted["slot_start"] = [
        pretty(value)
        for value in formatted["slot_start"]
    ]
    formatted["slot_end"] = [
        pretty(value)
        for value in formatted["slot_end"]
    ]
    formatted["booking_id"] = [
        f"{int(value):04d}" if pd.notna(value) else "N/A"
        for value in formatted["booking_id"]
    ]
    formatted["appointment_status"] = [
        str(value).lower() if pd.notna(value) else "unknown"
        for value in formatted["appointment_status"]
    ]
    formatted["patient_name"] = [
        value if pd.notna(value) else "Unknown"
        for value in formatted["patient_name"]
    ]
    formatted["patient_phone"] = [
        value if pd.notna(value) else "Unknown"
        for value in formatted["patient_phone"]
    ]

    return formatted.rename(
        columns={
            "booking_id": "Booking ID",
            "patient_name": "Patient Name",
            "patient_phone": "Phone",
            "slot_start": "Start",
            "slot_end": "End",
            "appointment_status": "Status",
        }
    )[["Booking ID", "Patient Name", "Phone", "Start", "End", "Status"]]


def add_status_badges(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Status" not in df.columns:
        return df

    badge_map = {
        "booked": "🔵 Booked",
        "completed": "🟢 Completed",
        "missed": "🔴 Missed",
    }

    tagged = df.copy()
    tagged["Status"] = [badge_map.get(str(value).lower(), "⚪ Unknown") for value in tagged["Status"]]
    return tagged


def render_bookings_table(df: pd.DataFrame) -> None:
    st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        disabled=True,
        key="bookings_table",
        column_config={
            "Booking ID": st.column_config.TextColumn("Booking ID", width="small"),
            "Patient Name": st.column_config.TextColumn("Patient Name", width="medium"),
            "Phone": st.column_config.TextColumn("Phone", width="medium"),
            "Start": st.column_config.TextColumn("Start", width="large"),
            "End": st.column_config.TextColumn("End", width="large"),
            "Status": st.column_config.TextColumn("Status", width="medium"),
        },
    )


def render_open_slots_table(df: pd.DataFrame) -> None:
    # Streamlit Cloud can be strict with data_editor schema/type inference.
    # Use dataframe here for robust cross-version rendering.
    st.dataframe(df, use_container_width=True, hide_index=True)


def create_slot(slot_date, start_time) -> None:
    local_slot_start = datetime.combine(slot_date, start_time, tzinfo=IST)
    slot_start = local_slot_start.astimezone(timezone.utc)
    slot_end = slot_start + timedelta(minutes=30)

    insert_stmt = text(
        """
        INSERT INTO "Availability_Schedules" (clinic_id, slot_start, slot_end, is_open)
        VALUES (:clinic_id, :slot_start, :slot_end, :is_open)
        """
    )

    with get_engine().begin() as conn:
        conn.execute(
            insert_stmt,
            {
                "clinic_id": 1,
                "slot_start": slot_start,
                "slot_end": slot_end,
                "is_open": True,
            },
        )


def delete_open_slot(slot_id: int) -> int:
    delete_stmt = text(
        """
        DELETE FROM "Availability_Schedules"
        WHERE id = :slot_id AND clinic_id = :clinic_id AND is_open = TRUE
        """
    )

    with get_engine().begin() as conn:
        result = conn.execute(delete_stmt, {"slot_id": slot_id, "clinic_id": 1})
        return result.rowcount or 0


def update_appointment_status(booking_id: int, new_status: str) -> int:
    update_stmt = text(
        """
        UPDATE "Appointments"
        SET status = :new_status
        WHERE id = :booking_id
        """
    )
    with get_engine().begin() as conn:
        result = conn.execute(
            update_stmt,
            {"new_status": new_status, "booking_id": booking_id},
        )
        return result.rowcount or 0


st.set_page_config(page_title="Receptionist Dashboard", layout="wide")
st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    :root {
        --primary-teal: #0f8b8d;
        --primary-teal-dark: #0b6f71;
        --health-blue: #2a6fdb;
        --text-main: #0f172a; /* High contrast dark text */
        --text-muted: #475569; /* Secondary text */
        --surface: #ffffff;
        --border-soft: #e2e8f0;
    }

    .stApp {
        background: #f8fafc;
    }

    /* Force all standard text, labels, and markdown to be dark and readable */
    .stApp, .stApp p, .stApp label, .stApp div[data-testid="stMarkdownContainer"] p {
        color: var(--text-main) !important;
    }

    .section-title {
        background: linear-gradient(90deg, var(--primary-teal-dark), var(--primary-teal));
        color: #ffffff !important;
        border-radius: 12px;
        padding: 0.7rem 1rem;
        margin: 0.25rem 0 0.9rem 0;
        box-shadow: 0 4px 12px rgba(15, 139, 141, 0.15);
        font-weight: 700;
    }

    /* Ensure icons inside the title stay white */
    .section-title .big-icon {
        font-size: 1.8rem;
        vertical-align: middle;
        margin-right: 0.45rem;
        color: #ffffff !important;
    }

    .stButton > button, div.stFormSubmitButton > button {
        background-color: var(--health-blue);
        color: #ffffff !important;
        border: none;
        font-weight: 600;
        border-radius: 10px;
        padding: 0.5rem 0.9rem;
    }

    .stButton > button:hover, div.stFormSubmitButton > button:hover {
        background-color: #1f5fc0;
        color: #ffffff !important;
    }

    /* Metric Cards */
    [data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--border-soft);
        border-radius: 12px;
        padding: 0.4rem 0.7rem;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.05);
    }
    
    [data-testid="stMetricLabel"] {
        color: var(--text-muted) !important;
    }
    
    [data-testid="stMetricValue"] {
        color: var(--text-main) !important;
    }

    /* Tables */
    [data-testid="stDataFrame"] {
        border: 1px solid var(--border-soft);
        border-radius: 12px;
        background: var(--surface);
    }

    /* Forms */
    [data-testid="stForm"] {
        background: var(--surface);
        border: 1px solid var(--border-soft);
        border-radius: 12px;
        padding: 0.8rem;
    }

    /* Tabs - Make unselected tabs visible, and selected tabs pop */
    button[data-baseweb="tab"] p {
        color: var(--text-muted) !important;
        font-weight: 500;
    }
    button[data-baseweb="tab"][aria-selected="true"] p {
        color: var(--health-blue) !important;
        font-weight: 700 !important;
    }

    .danger-zone {
        border-top: 1px dashed #fca5a5;
        margin: 1rem 0 0.8rem 0;
        padding-top: 0.8rem;
        color: #9f1239 !important;
        font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("<div class='section-title'><span class='big-icon'>🏥</span>Clinic Receptionist Dashboard</div>", unsafe_allow_html=True)

filter_choice = st.radio(
    "View Range",
    options=["Today", "This Week", "All"],
    horizontal=True,
)

# Top-level summary metrics
booked_all_df = fetch_booked_appointments()
open_all_df = fetch_slots(is_open=True)
today_booked_df = apply_time_filter(booked_all_df, "Today")
today_booked_count = int(today_booked_df["booking_id"].notna().sum()) if not today_booked_df.empty else 0
open_slots_count = int(len(open_all_df))
estimated_revenue = today_booked_count * 500

metric_col_1, metric_col_2, metric_col_3 = st.columns(3)
metric_col_1.metric("Total Appointments Today", today_booked_count)
metric_col_2.metric("Open Slots Available", open_slots_count)
metric_col_3.metric("Estimated Revenue", f"Rs {estimated_revenue:,}")

left_col, right_col = st.columns([2, 1])

with left_col:
    tab_bookings, tab_open = st.tabs(["📅 Today's Bookings", "🟢 Open Slots"])

    with tab_bookings:
        st.markdown("<div class='section-title'><span class='big-icon'>📘</span>Booked Appointments</div>", unsafe_allow_html=True)
        booked_df = apply_time_filter(fetch_booked_appointments(), filter_choice)
        booked_table = format_booked_appointments(booked_df)
        if booked_table.empty:
            st.info("No booked appointments yet.")
        else:
            render_bookings_table(add_status_badges(booked_table))

    with tab_open:
        st.markdown("<div class='section-title'><span class='big-icon'>🟢</span>Available Slots</div>", unsafe_allow_html=True)
        open_df = apply_time_filter(fetch_slots(is_open=True), filter_choice)
        open_table = format_slots(open_df)
        if open_table.empty:
            st.info("No available slots.")
        else:
            render_open_slots_table(open_table)

with right_col:
    st.markdown("<div class='section-title'><span class='big-icon'>➕</span>Generate New Slot</div>", unsafe_allow_html=True)
    with st.form("create_slot_form", clear_on_submit=True):
        selected_date = st.date_input("Date")
        selected_time = st.time_input("Start Time", step=1800)
        submit_create = st.form_submit_button("Create Slot")

        if submit_create:
            try:
                create_slot(selected_date, selected_time)
                st.success("New slot created successfully.")
                st.toast("New slot created successfully", icon="✅")
                st.balloons()
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to create slot: {exc}")

    st.markdown("<div class='danger-zone'>Danger Zone</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'><span class='big-icon'>🗑️</span>Delete Slot</div>", unsafe_allow_html=True)
    open_slots_for_delete = fetch_slots(is_open=True)

    if open_slots_for_delete.empty:
        st.info("No open slots available to delete.")
    else:
        records = open_slots_for_delete.to_dict(orient="records")
        option_map = {
            f"#{int(record['id'])} | {pd.to_datetime(record['slot_start'], utc=True).tz_convert(IST).strftime('%b %d, %Y - %I:%M %p')}": int(record['id'])
            for record in records
        }
        selected_option = st.selectbox("Open Slots", options=list(option_map.keys()))

        if st.button("Delete Selected Slot", type="secondary"):
            try:
                deleted = delete_open_slot(option_map[selected_option])
                if deleted > 0:
                    st.success("Slot deleted successfully.")
                else:
                    st.warning("Slot was already removed or booked.")
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to delete slot: {exc}")

    st.markdown("<div class='section-title'><span class='big-icon'>✅</span>Update Appointment Status</div>", unsafe_allow_html=True)
    booked_records = fetch_booked_appointments().to_dict(orient="records")
    status_candidates = [record for record in booked_records if pd.notna(record.get("booking_id"))]

    if not status_candidates:
        st.info("No booked appointments available to update.")
    else:
        status_option_map = {
            (
                f"Booking #{int(record['booking_id']):04d} | "
                f"{record.get('patient_name') or 'Unknown'} | "
                f"{pd.to_datetime(record['slot_start'], utc=True).tz_convert(IST).strftime('%b %d, %I:%M %p')}"
            ): int(record["booking_id"])
            for record in status_candidates
        }
        selected_booking_label = st.selectbox(
            "Select Appointment",
            options=list(status_option_map.keys()),
        )
        selected_status = st.selectbox(
            "Mark As",
            options=["booked", "completed", "missed"],
            index=1,
        )

        if st.button("Update Status", type="primary"):
            try:
                updated = update_appointment_status(
                    status_option_map[selected_booking_label],
                    selected_status,
                )
                if updated > 0:
                    st.success("Appointment status updated successfully.")
                else:
                    st.warning("Could not update status. Appointment may no longer exist.")
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to update status: {exc}")
