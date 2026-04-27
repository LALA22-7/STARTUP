"""
Google Calendar Synchronization Service
Syncs clinic appointments with Google Calendar
"""
import os
from datetime import datetime
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from sqlalchemy import select

from app.database import AsyncSessionFactory, Appointment, Patient, Clinic


SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_calendar_service():
    """Initialize Google Calendar service with service account.

    Supports two configuration methods (in priority order):
    1. GOOGLE_CREDENTIALS_JSON env var — full JSON content as a string (recommended for cloud deployments)
    2. GOOGLE_CREDENTIALS_FILE env var — path to a local credentials file (for local/Docker use)
    """
    import json
    import tempfile

    credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if credentials_json:
        # Parse JSON content directly from env var — no file needed
        info = json.loads(credentials_json)
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
    else:
        credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "google_credentials.json")
        if not os.path.exists(credentials_file):
            raise FileNotFoundError(f"Google credentials file not found: {credentials_file}")
        credentials = service_account.Credentials.from_service_account_file(
            credentials_file, scopes=SCOPES
        )

    service = build("calendar", "v3", credentials=credentials)
    return service


def sync_appointment_to_calendar(
    appointment_id: int,
    patient_name: str,
    doctor_name: str,
    start_time: datetime,
    end_time: datetime,
    clinic_name: str = "City Health Clinic",
    calendar_id: str = "primary",
) -> Optional[str]:
    """
    Sync a single appointment to Google Calendar
    
    Returns:
        Event ID if successful, None otherwise
    """
    try:
        service = get_calendar_service()
        
        event = {
            "summary": f"Appointment: {patient_name} - Dr. {doctor_name}",
            "description": f"Clinic: {clinic_name}\nPatient: {patient_name}\nBooking ID: {appointment_id:04d}",
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": "Asia/Kolkata",
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": "Asia/Kolkata",
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 30},  # 30 min before
                    {"method": "email", "minutes": 60},  # 1 hour before
                ],
            },
        }
        
        created_event = service.events().insert(
            calendarId=calendar_id,
            body=event,
        ).execute()
        
        print(f"✅ Appointment synced to Google Calendar: {created_event['id']}")
        return created_event["id"]
        
    except Exception as e:
        print(f"❌ Failed to sync appointment to Google Calendar: {e}")
        return None


async def sync_all_appointments_to_calendar(clinic_id: int = 1) -> int:
    """
    Sync all pending appointments to Google Calendar
    
    Returns:
        Count of synced appointments
    """
    try:
        async with AsyncSessionFactory() as session:
            stmt = (
                select(Appointment, Patient)
                .join(Patient, Appointment.patient_id == Patient.id)
                .where(
                    Appointment.clinic_id == clinic_id,
                    Appointment.status == "booked",
                )
            )
            
            result = await session.execute(stmt)
            appointments = result.all()
            
            synced_count = 0
            for appt, patient in appointments:
                # Skip if already synced (you might add a calendar_event_id field to track this)
                event_id = sync_appointment_to_calendar(
                    appointment_id=appt.id,
                    patient_name=patient.full_name,
                    doctor_name="General",  # Could be extended with doctor table
                    start_time=appt.scheduled_start,
                    end_time=appt.scheduled_end,
                )
                
                if event_id:
                    synced_count += 1
            
            return synced_count
            
    except Exception as e:
        print(f"❌ Bulk sync failed: {e}")
        return 0


def update_appointment_in_calendar(
    event_id: str,
    patient_name: str,
    doctor_name: str,
    start_time: datetime,
    end_time: datetime,
    calendar_id: str = "primary",
) -> bool:
    """Update an existing calendar event"""
    try:
        service = get_calendar_service()
        
        event = {
            "summary": f"Appointment: {patient_name} - Dr. {doctor_name}",
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": "Asia/Kolkata",
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": "Asia/Kolkata",
            },
        }
        
        service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=event,
        ).execute()
        
        print(f"✅ Calendar event updated: {event_id}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to update calendar event: {e}")
        return False


def delete_appointment_from_calendar(
    event_id: str,
    calendar_id: str = "primary",
) -> bool:
    """Delete an appointment from Google Calendar"""
    try:
        service = get_calendar_service()
        
        service.events().delete(
            calendarId=calendar_id,
            eventId=event_id,
        ).execute()
        
        print(f"✅ Calendar event deleted: {event_id}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to delete calendar event: {e}")
        return False


def list_clinic_calendar_events(
    calendar_id: str = "primary",
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
) -> list:
    """List all events in the clinic calendar"""
    try:
        service = get_calendar_service()
        
        params = {"calendarId": calendar_id, "maxResults": 100}
        
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        
        events_result = service.events().list(**params).execute()
        
        events = events_result.get("items", [])
        print(f"✅ Retrieved {len(events)} calendar events")
        
        return events
        
    except Exception as e:
        print(f"❌ Failed to list calendar events: {e}")
        return []
