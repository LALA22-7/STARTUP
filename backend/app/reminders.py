"""
Automated Reminder Service using APScheduler
Handles WhatsApp and voice reminders for appointments
"""
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
import httpx

from app.database import AsyncSessionFactory, Appointment, Availability_Schedule, Patient

IST = ZoneInfo("Asia/Kolkata")

scheduler = AsyncIOScheduler()


def _get_twilio_client():
    """Import Twilio lazily so voice is optional at runtime."""
    try:
        from twilio.rest import Client
    except ImportError:
        return None
    return Client


async def send_whatsapp_text(to_phone: str, reply_text: str) -> None:
    """Send WhatsApp text reminder"""
    META_PHONE_ID = os.getenv("META_PHONE_ID")
    META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
    url = f"https://graph.facebook.com/v18.0/{META_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": reply_text},
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload, timeout=10.0)
            response.raise_for_status()
            print(f"[reminder] sent to {to_phone}")
        except Exception as e:
            print(f"[reminder] failed for {to_phone}: {e}")


async def check_and_send_reminders() -> None:
    """
    Runs every hour to check for upcoming appointments within 24 hours
    and sends WhatsApp + voice reminders
    """
    try:
        async with AsyncSessionFactory() as session:
            now = datetime.now(timezone.utc)
            tomorrow = now + timedelta(days=1)
            
            # Get all appointments scheduled for the next 24 hours that haven't been reminded
            stmt = (
                select(Appointment, Patient, Availability_Schedule)
                .join(Patient, Appointment.patient_id == Patient.id)
                .join(
                    Availability_Schedule,
                    Appointment.schedule_id == Availability_Schedule.id,
                )
                .where(
                    Appointment.scheduled_start >= now,
                    Appointment.scheduled_start <= tomorrow,
                    Appointment.status == "booked",
                )
            )
            
            result = await session.execute(stmt)
            appointments = result.all()
            
            for appt, patient, schedule in appointments:
                if patient.phone:
                    appt_time = appt.scheduled_start.astimezone(IST).strftime(
                        "%B %d at %I:%M %p"
                    )
                    reminder_text = (
                        f"🏥 *Appointment Reminder*\n\n"
                        f"Hi {patient.full_name},\n\n"
                        f"This is a reminder for your appointment on *{appt_time}*.\n\n"
                        f"Please reply with:\n"
                        f"✅ *CONFIRM* to confirm\n"
                        f"❌ *CANCEL* to cancel\n"
                        f"📅 *RESCHEDULE* to reschedule\n\n"
                        f"If you don't respond, we'll follow up with a call."
                    )
                    await send_whatsapp_text(patient.phone, reminder_text)
                    patient_phone = patient.phone
                    appointment_details = appt_time
                    await send_voice_reminder(patient_phone, appointment_details)
                    
    except Exception as e:
        print(f"[reminder] check failed: {e}")


async def send_voice_reminder(phone_number: str, appt_time_str: str) -> None:
    """
    Trigger automated voice reminder via Twilio
    (Requires Twilio credentials in .env)
    """
    try:
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_phone = os.getenv("TWILIO_PHONE_NUMBER")
        
        if not account_sid or not auth_token or not from_phone:
            print("[voice] twilio credentials missing, skipping reminder")
            return
            
        twilio_client = _get_twilio_client()
        if twilio_client is None:
            print("[voice] twilio library missing, skipping reminder")
            return

        client = twilio_client(account_sid, auth_token)
        
        message_body = f"Hello! This is a reminder about your appointment on {appt_time_str}. Press 1 to confirm, 2 to cancel, or 3 to speak with someone."
        
        call = client.calls.create(
            to=phone_number,
            from_=from_phone,
            twiml=f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>{message_body}</Say>
    <Gather numDigits="1" action="/voice/reminder-response" method="POST">
        <Say>Please press a digit</Say>
    </Gather>
</Response>"""
        )
        print(f"[voice] reminder initiated: {call.sid}")
    except Exception as e:
        print(f"[voice] reminder failed: {e}")


async def send_no_show_recovery_call(phone_number: str, patient_name: str) -> None:
    """Send recovery call for no-shows"""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_phone = os.getenv("TWILIO_PHONE_NUMBER")
    
    if not account_sid or not auth_token or not from_phone:
        return
        
    twilio_client = _get_twilio_client()
    if twilio_client is None:
        print("[voice] twilio library missing, skipping no-show recovery")
        return

    client = twilio_client(account_sid, auth_token)
    
    message_body = f"Hi {patient_name}, we noticed you missed your appointment. Would you like to reschedule? Press 1 to book now, or we'll have our receptionist call you back."
    
    call = client.calls.create(
        to=phone_number,
        from_=from_phone,
        twiml=f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>{message_body}</Say>
    <Gather numDigits="1" action="/voice/reschedule-from-no-show" method="POST">
        <Say>Please press a digit</Say>
    </Gather>
</Response>"""
    )
    print(f"[voice] no-show recovery call sent: {call.sid}")


def start_scheduler() -> None:
    """Initialize and start the reminder scheduler"""
    if not scheduler.running:
        # Check and send reminders every hour
        scheduler.add_job(
            check_and_send_reminders,
            CronTrigger(hour="*"),  # Every hour
            id="hourly_reminders",
            name="Hourly appointment reminders",
            replace_existing=True,
        )
        
        scheduler.start()
        print("[scheduler] reminder scheduler started")


def stop_scheduler() -> None:
    """Stop the scheduler"""
    if scheduler.running:
        scheduler.shutdown()
        print("[scheduler] reminder scheduler stopped")
