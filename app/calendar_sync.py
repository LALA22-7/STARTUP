import os
import asyncio
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

# This defines the exact permission we need (editing events)
SCOPES = ['https://www.googleapis.com/auth/calendar.events']

# Look for the credentials file in the root directory
CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'google_credentials.json')

def _create_event_sync(patient_phone: str, slot_start: datetime, slot_end: datetime):
    """Synchronous function to talk to Google's API."""
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID")
    if not calendar_id:
        print("⚠️ GOOGLE_CALENDAR_ID missing from .env!")
        return

    try:
        # 1. Authenticate using the robot service account
        creds = service_account.Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)

        # 2. Format the event data
        event = {
            'summary': f'Patient Appointment - {patient_phone}',
            'description': 'Automatically booked via WhatsApp AI Receptionist.',
            'start': {
                'dateTime': slot_start.isoformat(),
                'timeZone': 'UTC', # Our database saves everything in UTC
            },
            'end': {
                'dateTime': slot_end.isoformat(),
                'timeZone': 'UTC',
            },
            'colorId': '5' # Makes the event yellow on the calendar
        }

        # 3. Push to Google Calendar
        event_result = service.events().insert(calendarId=calendar_id, body=event).execute()
        print(f"🗓️ GOOGLE CALENDAR SYNCED: {event_result.get('htmlLink')}")

    except Exception as e:
        print(f"❌ Google Calendar Sync Failed: {e}")

async def push_to_google_calendar(patient_phone: str, slot_start: datetime, slot_end: datetime):
    """
    Wraps the synchronous Google API call in an async thread 
    so it doesn't freeze the FastAPI server while waiting for Google.
    """
    await asyncio.to_thread(_create_event_sync, patient_phone, slot_start, slot_end)