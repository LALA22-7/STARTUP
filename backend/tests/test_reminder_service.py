"""
Unit tests: Reminder and Auto-Callback service.

Verifies:
- start_scheduler() / stop_scheduler() are called on FastAPI startup/shutdown
- check_and_send_reminders() sends WhatsApp reminders with CONFIRM/CANCEL/RESCHEDULE
- Twilio IVR call is skipped (with warning log) when TWILIO_* env vars are absent

Task 6.3 — Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Async helper
# ---------------------------------------------------------------------------

def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# 6.3.1 — Scheduler lifecycle: start/stop wired to FastAPI startup/shutdown
# ---------------------------------------------------------------------------

def test_start_scheduler_called_on_startup():
    """
    FastAPI startup event must call start_scheduler().
    Validates: Requirements 7.1
    """
    env_patch = {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "META_PHONE_ID": "test_phone_id",
        "META_ACCESS_TOKEN": "test_access_token",
    }

    with patch.dict(os.environ, env_patch):
        with patch("app.main.start_scheduler") as mock_start:
            with patch("app.main.stop_scheduler"):
                from app.main import app as fastapi_app
                from starlette.testclient import TestClient

                with TestClient(fastapi_app):
                    mock_start.assert_called_once()


def test_stop_scheduler_called_on_shutdown():
    """
    FastAPI shutdown event must call stop_scheduler().
    Validates: Requirements 7.1
    """
    env_patch = {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "META_PHONE_ID": "test_phone_id",
        "META_ACCESS_TOKEN": "test_access_token",
    }

    with patch.dict(os.environ, env_patch):
        with patch("app.main.start_scheduler"):
            with patch("app.main.stop_scheduler") as mock_stop:
                from app.main import app as fastapi_app
                from starlette.testclient import TestClient

                with TestClient(fastapi_app):
                    pass  # context exit triggers shutdown

                mock_stop.assert_called_once()


# ---------------------------------------------------------------------------
# 6.3.2 — check_and_send_reminders sends WhatsApp message with
#          CONFIRM / CANCEL / RESCHEDULE options
# ---------------------------------------------------------------------------

def test_reminder_message_contains_confirm_cancel_reschedule():
    """
    check_and_send_reminders() must send a WhatsApp message that includes
    CONFIRM, CANCEL, and RESCHEDULE options.
    Validates: Requirements 7.2
    """
    # Build mock ORM objects
    mock_patient = MagicMock()
    mock_patient.phone = "919999999999"
    mock_patient.full_name = "Test Patient"

    mock_appt = MagicMock()
    mock_appt.scheduled_start = datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc)

    mock_schedule = MagicMock()

    # Patch the DB session to return one appointment row
    mock_result = MagicMock()
    mock_result.all.return_value = [(mock_appt, mock_patient, mock_schedule)]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_session_factory = MagicMock(return_value=mock_session)

    captured_messages = []

    async def mock_send_whatsapp(to_phone: str, text: str) -> None:
        captured_messages.append({"to": to_phone, "text": text})

    async def mock_send_voice(phone: str, appt_time: str) -> None:
        pass  # voice is tested separately

    with patch("app.reminders.AsyncSessionFactory", mock_session_factory):
        with patch("app.reminders.send_whatsapp_text", side_effect=mock_send_whatsapp):
            with patch("app.reminders.send_voice_reminder", side_effect=mock_send_voice):
                run_async(__import__("app.reminders", fromlist=["check_and_send_reminders"]).check_and_send_reminders())

    assert len(captured_messages) == 1, (
        f"Expected 1 WhatsApp reminder, got {len(captured_messages)}"
    )

    msg_text = captured_messages[0]["text"]
    assert "CONFIRM" in msg_text, "Reminder must include CONFIRM option"
    assert "CANCEL" in msg_text, "Reminder must include CANCEL option"
    assert "RESCHEDULE" in msg_text, "Reminder must include RESCHEDULE option"
    assert captured_messages[0]["to"] == "919999999999"


def test_reminder_skipped_when_patient_has_no_phone():
    """
    check_and_send_reminders() must NOT send a reminder when the patient
    has no phone number.
    Validates: Requirements 7.2
    """
    mock_patient = MagicMock()
    mock_patient.phone = None  # no phone
    mock_patient.full_name = "No Phone Patient"

    mock_appt = MagicMock()
    mock_appt.scheduled_start = datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc)
    mock_schedule = MagicMock()

    mock_result = MagicMock()
    mock_result.all.return_value = [(mock_appt, mock_patient, mock_schedule)]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_session_factory = MagicMock(return_value=mock_session)

    captured_messages = []

    async def mock_send_whatsapp(to_phone: str, text: str) -> None:
        captured_messages.append({"to": to_phone, "text": text})

    with patch("app.reminders.AsyncSessionFactory", mock_session_factory):
        with patch("app.reminders.send_whatsapp_text", side_effect=mock_send_whatsapp):
            run_async(__import__("app.reminders", fromlist=["check_and_send_reminders"]).check_and_send_reminders())

    assert len(captured_messages) == 0, (
        "No reminder should be sent when patient has no phone number"
    )


# ---------------------------------------------------------------------------
# 6.3.3 — Twilio IVR call is skipped with a warning when credentials absent
# ---------------------------------------------------------------------------

def test_voice_reminder_skipped_when_twilio_credentials_missing(capsys):
    """
    send_voice_reminder() must skip the IVR call and log a warning when
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, or TWILIO_PHONE_NUMBER are absent.
    Validates: Requirements 7.6
    """
    # Ensure Twilio env vars are absent
    env_without_twilio = {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "META_PHONE_ID": "test_phone_id",
        "META_ACCESS_TOKEN": "test_access_token",
    }
    # Remove Twilio vars if present
    for key in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"):
        env_without_twilio[key] = ""

    with patch.dict(os.environ, env_without_twilio, clear=False):
        # Unset the vars so os.getenv returns None/empty
        for key in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"):
            os.environ.pop(key, None)

        from app.reminders import send_voice_reminder

        # Should complete without raising an exception
        run_async(send_voice_reminder("919999999999", "June 1 at 10:00 AM"))

    captured = capsys.readouterr()
    # The function must log a warning about missing credentials
    assert "twilio" in captured.out.lower() or "credentials" in captured.out.lower(), (
        f"Expected a Twilio warning in stdout, got: {captured.out!r}"
    )


def test_voice_reminder_skipped_when_twilio_library_missing():
    """
    send_voice_reminder() must skip the IVR call gracefully when the
    twilio library is not installed (_get_twilio_client returns None).
    Validates: Requirements 7.6
    """
    env_with_twilio = {
        "TWILIO_ACCOUNT_SID": "ACtest",
        "TWILIO_AUTH_TOKEN": "authtest",
        "TWILIO_PHONE_NUMBER": "+15550000000",
    }

    with patch.dict(os.environ, env_with_twilio):
        with patch("app.reminders._get_twilio_client", return_value=None):
            from app.reminders import send_voice_reminder

            # Should complete without raising an exception
            run_async(send_voice_reminder("919999999999", "June 1 at 10:00 AM"))
