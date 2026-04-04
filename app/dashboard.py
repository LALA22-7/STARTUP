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


def format_slots(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    formatted = df.copy()
    formatted["slot_start"] = [
        pd.to_datetime(value, utc=True).tz_convert(IST).strftime("%b %d, %Y - %I:%M %p")
        for value in formatted["slot_start"]
    ]
    formatted["slot_end"] = [
        pd.to_datetime(value, utc=True).tz_convert(IST).strftime("%b %d, %Y - %I:%M %p")
        for value in formatted["slot_end"]
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

    formatted = df.copy()
    formatted["slot_start"] = [
        pd.to_datetime(value, utc=True).tz_convert(IST).strftime("%b %d, %Y - %I:%M %p")
        for value in formatted["slot_start"]
    ]
    formatted["slot_end"] = [
        pd.to_datetime(value, utc=True).tz_convert(IST).strftime("%b %d, %Y - %I:%M %p")
        for value in formatted["slot_end"]
    ]
    formatted["booking_id"] = [
        f"{int(value):04d}" if pd.notna(value) else "N/A"
        for value in formatted["booking_id"]
    ]
    formatted["appointment_status"] = [
        str(value).capitalize() if pd.notna(value) else "Unknown"
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
    :root {
        --hospital-green: #1f8f5f;
        --hospital-green-dark: #146846;
        --hospital-bg: #f7f4ed;
        --card-bg: #fdfcf8;
    }

    .stApp {
        background: linear-gradient(180deg, var(--hospital-bg) 0%, #f2eee4 100%);
    }

    .section-title {
        background: linear-gradient(90deg, var(--hospital-green-dark), var(--hospital-green));
        color: #ffffff;
        border-radius: 10px;
        padding: 0.65rem 0.9rem;
        margin: 0.25rem 0 0.9rem 0;
        box-shadow: 0 2px 8px rgba(20, 104, 70, 0.18);
        font-weight: 700;
    }

    .big-icon {
        font-size: 2rem;
        vertical-align: middle;
        margin-right: 0.45rem;
        color: #ffffff;
    }

    .stButton > button, div.stFormSubmitButton > button {
        background-color: var(--hospital-green);
        color: #ffffff;
        border: none;
        font-weight: 600;
    }

    .stButton > button:hover, div.stFormSubmitButton > button:hover {
        background-color: var(--hospital-green-dark);
        color: #ffffff;
    }

    [data-testid="stDataFrame"] {
        border: 1px solid #cde9dd;
        border-radius: 10px;
        background: var(--card-bg);
    }

    [data-testid="stForm"] {
        background: var(--card-bg);
        border: 1px solid #d8e8de;
        border-radius: 10px;
        padding: 0.7rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("<div class='section-title'><span class='big-icon'>🏥</span>Clinic Receptionist Dashboard</div>", unsafe_allow_html=True)

left_col, right_col = st.columns([2, 1])

with left_col:
    st.markdown("<div class='section-title'><span class='big-icon'>📘</span>Booked Appointments</div>", unsafe_allow_html=True)
    booked_df = fetch_booked_appointments()
    booked_table = format_booked_appointments(booked_df)
    if booked_table.empty:
        st.info("No booked appointments yet.")
    else:
        st.dataframe(booked_table, use_container_width=True, hide_index=True)

    st.markdown("<div class='section-title'><span class='big-icon'>🟢</span>Available Slots</div>", unsafe_allow_html=True)
    open_df = fetch_slots(is_open=True)
    open_table = format_slots(open_df)
    if open_table.empty:
        st.info("No available slots.")
    else:
        st.dataframe(open_table, use_container_width=True, hide_index=True)

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
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to create slot: {exc}")

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
