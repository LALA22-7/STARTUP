"""
Automated Reminder Service using APScheduler

Flow:
  1. Every 5 minutes: find appointments starting in ~2 hours that haven't been
     reminded yet → send WhatsApp reminder, stamp reminder_sent_at.
  2. Every 5 minutes: find appointments where the reminder was sent 30+ minutes
     ago and the patient has NOT confirmed → trigger a voice call.
  3. When the patient replies CONFIRM via WhatsApp, main.py sets confirmed=True
     so the follow-up call is suppressed.
"""
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, update
import httpx

from app.database import AsyncSessionFactory, Appointment, Availability_Schedule, Patient

IST = ZoneInfo("Asia/Kolkata")

scheduler = AsyncIOScheduler()

# How far ahead to send the WhatsApp reminder (minutes)
REMINDER_WINDOW_MINUTES = 120  # 2 hours before appointment
# Tolerance band so we don't miss appointments when the job fires slightly late
REMINDER_TOLERANCE_MINUTES = 6  # job runs every 5 min, 1 min buffer

# How long to wait after the reminder before calling if no confirmation
CALL_DELAY_MINUTES = 30


def _get_twilio_client():
    """Import Twilio lazily so voice is optional at runtime."""
    try:
        from twilio.rest import Client
    except ImportError:
        return None
    return Client


async def send_whatsapp_text(to_phone: str, reply_text: str) -> None:
    """Send a plain WhatsApp text message."""
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
            print(f"[reminder] WhatsApp sent to {to_phone}")
        except Exception as e:
            print(f"[reminder] WhatsApp failed for {to_phone}: {e}")


async def send_voice_reminder(phone_number: str, appt_time_str: str) -> None:
    """Trigger an automated voice call via Twilio."""
    try:
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_phone = os.getenv("TWILIO_PHONE_NUMBER")

        if not account_sid or not auth_token or not from_phone:
            print("[voice] Twilio credentials missing, skipping call")
            return

        twilio_client = _get_twilio_client()
        if twilio_client is None:
            print("[voice] Twilio library missing, skipping call")
            return

        client = twilio_client(account_sid, auth_token)
        message_body = (
            f"Hello! This is a reminder about your appointment on {appt_time_str}. "
            "Press 1 to confirm, 2 to cancel, or 3 to speak with someone."
        )
        call = client.calls.create(
            to=phone_number,
            from_=from_phone,
            twiml=f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>{message_body}</Say>
    <Gather numDigits="1" action="/voice/reminder-response" method="POST">
        <Say>Please press a digit</Say>
    </Gather>
</Response>""",
        )
        print(f"[voice] call initiated: {call.sid}")
    except Exception as e:
        print(f"[voice] call failed for {phone_number}: {e}")


async def send_whatsapp_reminders() -> None:
    """
    Runs every 5 minutes.
    Finds booked appointments whose scheduled_start is between
    (now + 2h - tolerance) and (now + 2h + tolerance) that haven't
    been reminded yet, sends a WhatsApp message, and stamps reminder_sent_at.

    Each appointment is stamped in its own session BEFORE sending the message
    so that even if the WhatsApp call fails the appointment won't be re-queued
    on the next run (preventing duplicate messages).
    """
    try:
        now = datetime.now(timezone.utc)
        window_start = now + timedelta(minutes=REMINDER_WINDOW_MINUTES - REMINDER_TOLERANCE_MINUTES)
        window_end = now + timedelta(minutes=REMINDER_WINDOW_MINUTES + REMINDER_TOLERANCE_MINUTES)

        # --- Step 1: fetch candidates ---
        async with AsyncSessionFactory() as session:
            stmt = (
                select(Appointment, Patient)
                .join(Patient, Appointment.patient_id == Patient.id)
                .where(
                    Appointment.scheduled_start >= window_start,
                    Appointment.scheduled_start <= window_end,
                    Appointment.status == "booked",
                    Appointment.reminder_sent_at.is_(None),  # not yet reminded
                )
            )
            result = await session.execute(stmt)
            rows = result.all()

        # --- Step 2: for each candidate, stamp first then send ---
        for appt, patient in rows:
            if not patient.phone:
                continue

            # Stamp reminder_sent_at in a fresh session BEFORE sending.
            # This ensures we never send twice even if the HTTP call errors.
            async with AsyncSessionFactory() as stamp_session:
                async with stamp_session.begin():
                    stamped = await stamp_session.execute(
                        update(Appointment)
                        .where(
                            Appointment.id == appt.id,
                            Appointment.reminder_sent_at.is_(None),  # guard against race
                        )
                        .values(reminder_sent_at=now)
                        .returning(Appointment.id)
                    )
                    if not stamped.scalar_one_or_none():
                        # Another process already stamped this appointment
                        print(f"[reminder] appt {appt.id} already stamped, skipping")
                        continue

            appt_time = appt.scheduled_start.astimezone(IST).strftime("%B %d at %I:%M %p")
            reminder_text = (
                f"🏥 *Appointment Reminder*\n\n"
                f"Hi {patient.full_name},\n\n"
                f"Your appointment is scheduled for *{appt_time}* — that's in about 2 hours.\n\n"
                f"Please reply with:\n"
                f"✅ *CONFIRM* to confirm your attendance\n"
                f"❌ *CANCEL* to cancel\n"
                f"📅 *RESCHEDULE* to reschedule\n\n"
                f"If we don't hear back in 30 minutes, we'll give you a quick call."
            )
            await send_whatsapp_text(patient.phone, reminder_text)
            print(f"[reminder] WhatsApp reminder sent for appointment {appt.id}")

    except Exception as e:
        print(f"[reminder] send_whatsapp_reminders failed: {e}")


async def follow_up_unconfirmed_calls() -> None:
    """
    Runs every 5 minutes.
    Finds booked appointments where:
      - reminder_sent_at is set (WhatsApp was sent)
      - reminder was sent >= 30 minutes ago
      - confirmed is False (patient hasn't replied CONFIRM)
      - appointment hasn't passed yet
    Triggers a voice call for each. Sets confirmed=True after calling
    so the same appointment is never called twice.
    """
    try:
        now = datetime.now(timezone.utc)
        call_threshold = now - timedelta(minutes=CALL_DELAY_MINUTES)

        # --- Step 1: fetch candidates ---
        async with AsyncSessionFactory() as session:
            stmt = (
                select(Appointment, Patient)
                .join(Patient, Appointment.patient_id == Patient.id)
                .where(
                    Appointment.status == "booked",
                    Appointment.reminder_sent_at.isnot(None),
                    Appointment.reminder_sent_at <= call_threshold,
                    Appointment.confirmed.is_(False),
                    Appointment.scheduled_start > now,  # appointment hasn't happened yet
                )
            )
            result = await session.execute(stmt)
            rows = result.all()

        # --- Step 2: mark confirmed BEFORE calling to prevent duplicate calls ---
        for appt, patient in rows:
            if not patient.phone:
                continue

            async with AsyncSessionFactory() as stamp_session:
                async with stamp_session.begin():
                    stamped = await stamp_session.execute(
                        update(Appointment)
                        .where(
                            Appointment.id == appt.id,
                            Appointment.confirmed.is_(False),  # guard against race
                        )
                        .values(confirmed=True)
                        .returning(Appointment.id)
                    )
                    if not stamped.scalar_one_or_none():
                        print(f"[reminder] appt {appt.id} already handled, skipping call")
                        continue

            appt_time = appt.scheduled_start.astimezone(IST).strftime("%B %d at %I:%M %p")
            print(
                f"[reminder] no confirmation for appt {appt.id} "
                f"(reminded at {appt.reminder_sent_at}), calling {patient.phone}"
            )
            await send_voice_reminder(patient.phone, appt_time)

    except Exception as e:
        print(f"[reminder] follow_up_unconfirmed_calls failed: {e}")


async def send_no_show_recovery_call(phone_number: str, patient_name: str) -> None:
    """Send recovery call for no-shows."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_phone = os.getenv("TWILIO_PHONE_NUMBER")

    if not account_sid or not auth_token or not from_phone:
        return

    twilio_client = _get_twilio_client()
    if twilio_client is None:
        print("[voice] Twilio library missing, skipping no-show recovery")
        return

    client = twilio_client(account_sid, auth_token)
    message_body = (
        f"Hi {patient_name}, we noticed you missed your appointment. "
        "Would you like to reschedule? Press 1 to book now, "
        "or we'll have our receptionist call you back."
    )
    call = client.calls.create(
        to=phone_number,
        from_=from_phone,
        twiml=f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>{message_body}</Say>
    <Gather numDigits="1" action="/voice/reschedule-from-no-show" method="POST">
        <Say>Please press a digit</Say>
    </Gather>
</Response>""",
    )
    print(f"[voice] no-show recovery call sent: {call.sid}")


def start_scheduler() -> None:
    """Initialize and start the reminder scheduler."""
    if not scheduler.running:
        # Job 1: Send WhatsApp reminder ~2 hours before appointment
        scheduler.add_job(
            send_whatsapp_reminders,
            IntervalTrigger(minutes=5),
            id="whatsapp_2hr_reminders",
            name="WhatsApp reminder 2 hours before appointment",
            replace_existing=True,
        )

        # Job 2: Call patients who haven't confirmed 30 min after the reminder
        scheduler.add_job(
            follow_up_unconfirmed_calls,
            IntervalTrigger(minutes=5),
            id="voice_followup_unconfirmed",
            name="Voice call for unconfirmed reminders after 30 min",
            replace_existing=True,
        )

        scheduler.start()
        print("[scheduler] reminder scheduler started (2-hour WhatsApp + 30-min voice follow-up)")


def stop_scheduler() -> None:
    """Stop the scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        print("[scheduler] reminder scheduler stopped")
