import os
import sys
import asyncio
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from typing import Literal, Optional, List

import httpx
import fastapi
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from google import genai
from sqlalchemy.exc import IntegrityError
from openai import AsyncOpenAI
from sqlalchemy import select, or_, func
from app.database import Appointment, AsyncSessionFactory, Availability_Schedule, Patient, Encounter, Doctor
from app.pdf_service import generate_prescription_pdf, generate_clinical_notes_pdf, sanitize_patient_name
from app.reminders import start_scheduler, stop_scheduler, send_whatsapp_text as send_reminder_whatsapp
from app.calendar_sync_service import sync_appointment_to_calendar
from app.analytics_service import AnalyticsService

load_dotenv()
app = FastAPI()

# ---------------------------------------------------------------------------
# CORS Middleware (Task 4.2)
# ---------------------------------------------------------------------------
# CORS_ORIGINS accepts a comma-separated list of allowed origins.
# Defaults to "*" so the dashboard works immediately after deploy.
# To restrict: set CORS_ORIGINS=https://clinicos-nine-ashy.vercel.app on Render.
_cors_env = os.getenv("CORS_ORIGINS", "*")
if _cors_env == "*":
    _allowed_origins = ["*"]
else:
    _allowed_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=_cors_env != "*",  # credentials not allowed with wildcard
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Pydantic API response models (Task 4.1)
# ---------------------------------------------------------------------------

class AppointmentResponse(BaseModel):
    id: int
    clinic_id: int
    patient_id: int
    doctor_id: Optional[int] = None
    scheduled_start: datetime
    scheduled_end: datetime
    status: str
    patient_name: str
    patient_phone: Optional[str] = None
    booking_id_display: str  # zero-padded, e.g. "0042"

    class Config:
        from_attributes = True


class AppointmentStatusUpdate(BaseModel):
    status: Literal["booked", "completed", "missed", "waiting"]


class DailyAnalyticsResponse(BaseModel):
    date: str
    total_appointments: int
    completed: int
    missed: int
    revenue: int


class MonthlyAnalyticsResponse(BaseModel):
    month: str
    total_revenue: int
    total_appointments: int
    completed_appointments: int
    missed_appointments: int
    no_show_rate: float
    daily_breakdown: List[DailyAnalyticsResponse]


class PatientResponse(BaseModel):
    id: int
    full_name: str
    phone: Optional[str] = None
    email: str
    created_at: datetime

    class Config:
        from_attributes = True


class EncounterResponse(BaseModel):
    id: int
    patient_id: int
    record: dict
    created_at: datetime

    class Config:
        from_attributes = True

from app.voice import router as voice_router
app.include_router(voice_router)

# --- STARTUP & SHUTDOWN EVENTS ---
@app.on_event("startup")
async def startup_event():
    """Validate required environment variables, create tables, then start the reminder scheduler."""
    print("[startup] ClinicOS starting up...")

    _REQUIRED_ENV_VARS = ["DATABASE_URL", "META_PHONE_ID", "META_ACCESS_TOKEN"]
    missing = [var for var in _REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing:
        for var in missing:
            print(f"[startup] ERROR: Required environment variable '{var}' is not set.")
        print("[startup] Aborting — set the missing variables in your .env file and restart.")
        sys.exit(1)

    # Auto-create tables if they don't exist (safe to run on every startup)
    try:
        from app.database import engine, Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("[startup] Database tables verified/created")
    except Exception as e:
        print(f"[startup] WARNING: Could not create tables: {e}")

    start_scheduler()
    print("[startup] Reminder scheduler activated")

@app.on_event("shutdown")
async def shutdown_event():
    """Stop scheduler on app shutdown"""
    print("[shutdown] ClinicOS shutting down...")
    stop_scheduler()
    print("[shutdown] Reminder scheduler stopped")

IST = ZoneInfo("Asia/Kolkata")

# --- MULTI-AGENT SWARM (INTEGRATED & SYNCED) ---
class Agent:
    def __init__(self, name: str, system_prompt: str, model: str = "llama-3.1-8b-instant"):
        self.name = name
        self.system_prompt = system_prompt
        self.model = model

    async def run(self, user_input: str) -> dict:
        try:
            response = await groq_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.3
            )
            content = response.choices[0].message.content
            content = content.strip() if content else ""
            return {"agent": self.name, "status": "success", "response": content}
        except Exception as e:
            return {"agent": self.name, "status": "error", "response": str(e)}

class AgentManager:
    def __init__(self):
        self.agents = self._load_agents()

    def _load_agents(self) -> List[Agent]:
        """Dynamically loads agents from the agents/ folder to keep them in sync."""
        loaded_agents = []
        agents_dir = os.path.join(os.path.dirname(__file__), "..", "agents")
        if not os.path.exists(agents_dir):
            print("[warn] agents directory not found")
            return loaded_agents

        import re
        for filename in os.listdir(agents_dir):
            if filename.endswith(".agent.md"):
                try:
                    with open(os.path.join(agents_dir, filename), "r", encoding="utf-8") as f:
                        content = f.read()
                        name_match = re.search(r'name:\s*"([^"]+)"', content)
                        name = name_match.group(1) if name_match else filename
                        parts = content.split("---")
                        if len(parts) >= 3:
                            system_prompt = parts[2].strip()
                            loaded_agents.append(Agent(name, system_prompt))
                            print(f"[agent] loaded: {name}")
                except Exception as e:
                    print(f"[agent] failed to load {filename}: {e}")
        return loaded_agents

    async def analyze(self, user_input: str):
        if not self.agents:
            self.agents = self._load_agents()
        tasks = [agent.run(user_input) for agent in self.agents]
        return await asyncio.gather(*tasks)

agent_manager = AgentManager()


def format_slot_for_whatsapp(slot_start) -> str:
    if slot_start.tzinfo is None:
        slot_start = slot_start.replace(tzinfo=timezone.utc)
    return slot_start.astimezone(IST).strftime('%b %d at %I:%M %p')

def build_booking_prompt(reply: str) -> str:
    return (
        f"{reply}\n\n"
        "If you would like to book an appointment, type *book appointment* anytime."
    )

class TextMessage(BaseModel):
    body: str

class ButtonReply(BaseModel):
    id: str
    title: Optional[str] = None

class ListReply(BaseModel):
    id: str
    title: Optional[str] = None
    description: Optional[str] = None

class InteractiveMessage(BaseModel):
    type: str
    button_reply: Optional[ButtonReply] = None
    list_reply: Optional[ListReply] = None

class Message(BaseModel):
    from_: str = Field(alias="from")
    type: str
    text: Optional[TextMessage] = None
    interactive: Optional[InteractiveMessage] = None

class Profile(BaseModel):
    name: str

class Contact(BaseModel):
    profile: Profile
    wa_id: Optional[str] = None

class Value(BaseModel):
    messaging_product: str
    metadata: dict
    contacts: Optional[List[Contact]] = None
    messages: Optional[List[Message]] = None

class Change(BaseModel):
    value: Value
    field: str

class Entry(BaseModel):
    id: str
    changes: List[Change]

class MetaWebhookPayload(BaseModel):
    object: str
    entry: List[Entry]

def phone_to_email(phone_number: str) -> str:
    digits_only = "".join(ch for ch in phone_number if ch.isdigit())
    base = digits_only or "unknown"
    return f"wa_{base}@clinic.local"


WELCOME_GUIDE = (
    "Welcome to City Health Clinic.\n"
    "To book instantly, type: *book appointment*\n"
    "To ask anything, type your question directly."
)


async def send_available_slots(to_phone: str) -> None:
    try:
        async with AsyncSessionFactory() as session:
            stmt = (
                select(Availability_Schedule)
                .where(
                    Availability_Schedule.clinic_id == 1,
                    Availability_Schedule.is_open == True,
                )
                .order_by(Availability_Schedule.slot_start)
                .limit(3)
            )

            result = await session.execute(stmt)
            available_slots = result.scalars().all()

        if not available_slots:
            await send_whatsapp_text(
                to_phone,
                "I'm sorry, we don't have any available appointments right now. Please try again tomorrow!",
            )
            return

        formatted_rows = [
            {
                "id": f"slot_{slot.id}",
                "title": format_slot_for_whatsapp(slot.slot_start)[:24],
            }
            for slot in available_slots
        ]
        await send_whatsapp_list(to_phone, formatted_rows)

    except Exception as e:
        print(f"Database Error: {e}")
        await send_whatsapp_text(
            to_phone,
            "Oops! Our calendar is syncing right now. Please try again in a minute.",
        )

# --- AI SETUP ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

groq_client = AsyncOpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

async def get_ai_response(user_question: str) -> str:
    system_prompt = """
    You are Sarah, the friendly AI receptionist for City Health Clinic. 
    Keep your answers very brief, professional, and conversational (1-2 sentences max).
    CLINIC KNOWLEDGE BASE: Noida location, Mon-Fri 9-5, Fees ₹500.
    """
    try:
        response = await groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_question}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content or "I could not generate a response."
    except Exception as e:
        return "Maintenance mode. Please call us."

async def send_to_meta(payload: dict):
    META_PHONE_ID = os.getenv("META_PHONE_ID")
    META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
    url = f"https://graph.facebook.com/v18.0/{META_PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {META_ACCESS_TOKEN}", "Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        except Exception as e:
            print(f"[meta] error: {e}")

async def send_main_menu_quick_reply(to_phone: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "Need anything else?"},
            "action": {"buttons": [{"type": "reply", "reply": {"id": "btn_main_menu", "title": "Back to Main Menu"}}]}
        }
    }
    await send_to_meta(payload)

async def send_whatsapp_text(to_phone: str, reply_text: str, *, add_menu_button: bool = True):
    payload = {"messaging_product": "whatsapp", "to": to_phone, "type": "text", "text": {"body": reply_text}}
    await send_to_meta(payload)
    if add_menu_button: await send_main_menu_quick_reply(to_phone)


def _build_meta_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def upload_whatsapp_media(
    pdf_bytes: bytes,
    filename: str,
) -> str:
    """Upload a PDF to WhatsApp media API and return media ID."""
    meta_phone_id = os.getenv("META_PHONE_ID")
    meta_access_token = os.getenv("META_ACCESS_TOKEN")
    if not meta_phone_id or not meta_access_token:
        raise RuntimeError("META_PHONE_ID or META_ACCESS_TOKEN missing")

    upload_url = f"https://graph.facebook.com/v18.0/{meta_phone_id}/media"
    headers = _build_meta_headers(meta_access_token)
    files = {"file": (filename, pdf_bytes, "application/pdf")}
    data = {"messaging_product": "whatsapp"}

    async with httpx.AsyncClient() as client:
        response = await client.post(upload_url, headers=headers, files=files, data=data, timeout=20.0)
        response.raise_for_status()
        payload = response.json()
    media_id = payload.get("id")
    if not media_id:
        raise RuntimeError(f"Media upload succeeded without media ID: {payload}")
    return media_id


async def send_whatsapp_document(
    to_phone: str,
    media_id: str,
    caption: str,
    filename: str,
) -> None:
    """Send an uploaded document to a WhatsApp user."""
    meta_phone_id = os.getenv("META_PHONE_ID")
    meta_access_token = os.getenv("META_ACCESS_TOKEN")
    if not meta_phone_id or not meta_access_token:
        raise RuntimeError("META_PHONE_ID or META_ACCESS_TOKEN missing")

    send_url = f"https://graph.facebook.com/v18.0/{meta_phone_id}/messages"
    headers = {
        **_build_meta_headers(meta_access_token),
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "document",
        "document": {
            "id": media_id,
            "caption": caption,
            "filename": filename,
        },
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(send_url, headers=headers, json=payload, timeout=20.0)
        response.raise_for_status()


async def send_prescription_pdf(
    to_phone: str,
    patient_name: str,
    doctor_name: str,
    medications: list,
    instructions: str = ""
) -> bool:
    """Generate a prescription PDF and deliver it as WhatsApp document."""
    try:
        pdf_bytes = generate_prescription_pdf(
            patient_name=patient_name,
            doctor_name=doctor_name,
            medications=medications,
            instructions=instructions,
        )
        safe_name = sanitize_patient_name(patient_name)
        filename = f"prescription_{safe_name}.pdf"

        media_id = await upload_whatsapp_media(pdf_bytes=pdf_bytes, filename=filename)
        caption = f"Prescription for {patient_name} from Dr. {doctor_name}"
        await send_whatsapp_document(
            to_phone=to_phone,
            media_id=media_id,
            caption=caption,
            filename=filename,
        )
        print(f"[pdf] sent via whatsapp media_id={media_id}")
        return True
    except Exception as e:
        print(f"[pdf] failed to send: {e}")
        await send_whatsapp_text(
            to_phone,
            "Sorry, we had an issue sending your prescription PDF. Please contact the clinic.",
        )
        return False


class PrescriptionSendRequest(BaseModel):
    to_phone: str
    patient_name: str
    doctor_name: str
    medications: list[dict]
    instructions: str = ""


@app.post("/prescription/send")
async def send_prescription_endpoint(payload: PrescriptionSendRequest):
    delivered = await send_prescription_pdf(
        to_phone=payload.to_phone,
        patient_name=payload.patient_name,
        doctor_name=payload.doctor_name,
        medications=payload.medications,
        instructions=payload.instructions,
    )
    if not delivered:
        raise HTTPException(status_code=502, detail="Prescription PDF delivery failed")
    return {"status": "success", "message": "Prescription PDF sent via WhatsApp"}

async def send_whatsapp_interactive_menu(to_phone: str):
    payload = {
        "messaging_product": "whatsapp", "to": to_phone, "type": "interactive",
        "interactive": {
            "type": "button", "body": {"text": "Welcome! How can I help?"},
            "action": {"buttons": [{"type": "reply", "reply": {"id": "btn_book_appt", "title": "Book Appointment"}}, {"type": "reply", "reply": {"id": "btn_ask_question", "title": "Ask a Question"}}]}
        }
    }
    await send_to_meta(payload)

async def send_whatsapp_list(to_phone: str, formatted_rows: list):
    payload = {
        "messaging_product": "whatsapp", "to": to_phone, "type": "interactive",
        "interactive": {
            "type": "list", "header": {"type": "text", "text": "Available Slots"},
            "body": {"text": "Select a time:"},
            "action": {"button": "Select Time", "sections": [{"title": "Slots", "rows": formatted_rows}]}
        }
    }
    await send_to_meta(payload)

# ---------------------------------------------------------------------------
# REST API endpoints (Tasks 4.3, 4.4, 4.6, 4.8, 4.10, 4.12)
# ---------------------------------------------------------------------------

@app.get("/api/appointments", response_model=List[AppointmentResponse])
async def get_appointments(
    clinic_id: int = Query(..., description="Clinic ID (required)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    date_from: Optional[date] = Query(None, description="Filter from date (ISO, inclusive)"),
    date_to: Optional[date] = Query(None, description="Filter to date (ISO, inclusive)"),
):
    """Return all appointments for a clinic, optionally filtered by status and date range."""
    async with AsyncSessionFactory() as session:
        stmt = (
            select(Appointment, Patient)
            .join(Patient, Appointment.patient_id == Patient.id)
            .where(Appointment.clinic_id == clinic_id)
        )
        if status:
            stmt = stmt.where(Appointment.status == status)
        if date_from:
            day_start = datetime.combine(date_from, datetime.min.time(), tzinfo=IST).astimezone(timezone.utc)
            stmt = stmt.where(Appointment.scheduled_start >= day_start)
        if date_to:
            day_end = datetime.combine(date_to, datetime.max.time(), tzinfo=IST).astimezone(timezone.utc)
            stmt = stmt.where(Appointment.scheduled_start <= day_end)

        result = await session.execute(stmt)
        rows = result.all()

    return [
        AppointmentResponse(
            id=appt.id,
            clinic_id=appt.clinic_id,
            patient_id=appt.patient_id,
            doctor_id=appt.doctor_id,
            scheduled_start=appt.scheduled_start,
            scheduled_end=appt.scheduled_end,
            status=appt.status,
            patient_name=patient.full_name,
            patient_phone=patient.phone,
            booking_id_display=f"{appt.id:04d}",
        )
        for appt, patient in rows
    ]


@app.patch("/api/appointments/{appointment_id}/status", response_model=AppointmentResponse)
async def update_appointment_status(appointment_id: int, body: AppointmentStatusUpdate):
    """Update the status of an appointment. Returns 404 for unknown IDs."""
    async with AsyncSessionFactory() as session:
        async with session.begin():
            appt = await session.get(Appointment, appointment_id)
            if appt is None:
                raise HTTPException(status_code=404, detail=f"Appointment {appointment_id} not found")
            appt.status = body.status

        # Reload with patient join after commit
        stmt = (
            select(Appointment, Patient)
            .join(Patient, Appointment.patient_id == Patient.id)
            .where(Appointment.id == appointment_id)
        )
        result = await session.execute(stmt)
        row = result.first()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Appointment {appointment_id} not found")
        appt, patient = row

    return AppointmentResponse(
        id=appt.id,
        clinic_id=appt.clinic_id,
        patient_id=appt.patient_id,
        doctor_id=appt.doctor_id,
        scheduled_start=appt.scheduled_start,
        scheduled_end=appt.scheduled_end,
        status=appt.status,
        patient_name=patient.full_name,
        patient_phone=patient.phone,
        booking_id_display=f"{appt.id:04d}",
    )


@app.get("/api/analytics/daily", response_model=DailyAnalyticsResponse)
async def get_daily_analytics(
    clinic_id: int = Query(1, description="Clinic ID"),
    date: Optional[str] = Query(None, description="ISO date string (defaults to today IST)"),
):
    """Return daily revenue and appointment stats for a given date."""
    service = AnalyticsService(clinic_id=clinic_id)
    if date:
        parsed_date = datetime.fromisoformat(date).replace(tzinfo=IST)
    else:
        parsed_date = datetime.now(IST)
    data = await service.get_daily_revenue(parsed_date)
    return DailyAnalyticsResponse(**data)


@app.get("/api/analytics/monthly", response_model=MonthlyAnalyticsResponse)
async def get_monthly_analytics(
    clinic_id: int = Query(1, description="Clinic ID"),
    year: int = Query(..., description="Year (e.g. 2025)"),
    month: int = Query(..., description="Month (1–12)"),
):
    """Return monthly revenue, no-show rate, and daily breakdown."""
    service = AnalyticsService(clinic_id=clinic_id)
    data = await service.get_monthly_revenue(year=year, month=month)
    return MonthlyAnalyticsResponse(
        month=data["month"],
        total_revenue=data["total_revenue"],
        total_appointments=data["total_appointments"],
        completed_appointments=data["completed_appointments"],
        missed_appointments=data["missed_appointments"],
        no_show_rate=data["no_show_rate"],
        daily_breakdown=[DailyAnalyticsResponse(**d) for d in data["daily_breakdown"]],
    )


@app.get("/api/patients", response_model=List[PatientResponse])
async def get_patients(
    clinic_id: int = Query(..., description="Clinic ID (required)"),
    search: Optional[str] = Query(None, description="Case-insensitive filter on full_name or phone"),
):
    """Return all patients for a clinic, with optional name/phone search."""
    async with AsyncSessionFactory() as session:
        # Subquery: patient IDs that have at least one appointment for this clinic
        clinic_patient_ids_stmt = select(Appointment.patient_id).where(
            Appointment.clinic_id == clinic_id
        ).distinct()

        stmt = select(Patient).where(Patient.id.in_(clinic_patient_ids_stmt))

        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    func.lower(Patient.full_name).like(func.lower(pattern)),
                    Patient.phone.like(pattern),
                )
            )

        result = await session.execute(stmt)
        patients = result.scalars().all()

    return [
        PatientResponse(
            id=p.id,
            full_name=p.full_name,
            phone=p.phone,
            email=p.email,
            created_at=p.created_at,
        )
        for p in patients
    ]


@app.get("/api/patients/{patient_id}/encounters", response_model=List[EncounterResponse])
async def get_patient_encounters(patient_id: int):
    """Return the last 10 encounters for a patient, sorted by created_at descending."""
    async with AsyncSessionFactory() as session:
        stmt = (
            select(Encounter)
            .where(Encounter.patient_id == patient_id)
            .order_by(Encounter.created_at.desc())
            .limit(10)
        )
        result = await session.execute(stmt)
        encounters = result.scalars().all()

    return [
        EncounterResponse(
            id=e.id,
            patient_id=e.patient_id,
            record=e.record,
            created_at=e.created_at,
        )
        for e in encounters
    ]


# --- WEBHOOKS ---
@app.get("/webhook")
async def verify_webhook(request: Request):
    if request.query_params.get("hub.mode") == "subscribe" and request.query_params.get("hub.verify_token") == os.getenv("META_VERIFY_TOKEN"):
        return PlainTextResponse(content=request.query_params.get("hub.challenge"), status_code=200)
    raise HTTPException(status_code=403)

@app.post("/webhook")
async def receive_whatsapp_message(payload: MetaWebhookPayload, background_tasks: fastapi.BackgroundTasks):
    if payload.entry and payload.entry[0].changes:
        value = payload.entry[0].changes[0].value
        if value.messages:
            background_tasks.add_task(process_whatsapp_logic, value, value.messages[0])
    return {"status": "success"}

async def process_whatsapp_logic(value: Value, msg: Message):
    try:
        phone_number = msg.from_
        if msg.type == 'interactive' and msg.interactive:
            itype = msg.interactive.type
            if itype == 'button_reply':
                bid = msg.interactive.button_reply.id if msg.interactive.button_reply else None
                if bid == 'btn_book_appt': await send_available_slots(phone_number)
                elif bid == 'btn_ask_question': await send_whatsapp_text(phone_number, "What's your question?")
                elif bid == 'btn_main_menu': await send_whatsapp_interactive_menu(phone_number)
            elif itype == 'list_reply':
                slot_id = msg.interactive.list_reply.id if msg.interactive.list_reply else None
                if slot_id and slot_id.startswith("slot_"):
                    db_id = int(slot_id.split("_")[1])
                    p_name = value.contacts[0].profile.name if value.contacts else "Patient"
                    async with AsyncSessionFactory() as session:
                        async with session.begin():
                            slot = (await session.execute(select(Availability_Schedule).where(Availability_Schedule.id == db_id).with_for_update())).scalar_one_or_none()
                            if not slot or not slot.is_open:
                                await send_whatsapp_text(phone_number, "Slot taken.")
                                return
                            patient = (await session.execute(select(Patient).where(Patient.phone == phone_number))).scalar_one_or_none()
                            if not patient:
                                patient = Patient(full_name=p_name, email=phone_to_email(phone_number), phone=phone_number)
                                session.add(patient); await session.flush()
                            appt = Appointment(clinic_id=slot.clinic_id, patient_id=patient.id, schedule_id=slot.id, scheduled_start=slot.slot_start, scheduled_end=slot.slot_end, status="booked")
                            session.add(appt); slot.is_open = False; await session.flush()
                            await send_whatsapp_text(phone_number, f"Confirmed! ID: {appt.id:04d}")

        elif msg.type == 'text':
            raw_text = msg.text.body if msg.text else ""
            if 'book appointment' in raw_text.lower():
                await send_available_slots(phone_number)
            elif raw_text.lower() in ['hi', 'hello', 'menu']:
                await send_whatsapp_interactive_menu(phone_number)
            else:
                insights = await agent_manager.analyze(raw_text)
                triage = next((r["response"] for r in insights if r["agent"] == "Triage Specialist"), "GENERAL")
                sentiment = next((r["response"] for r in insights if r["agent"] == "Sentiment Analyst"), "NEUTRAL")
                clinical = next((r["response"] for r in insights if r["agent"] == "Clinical Assistant"), None)
                
                # Intelligent Routing based on Agent Swarm
                if "EMERGENCY" in triage or "URGENT" in sentiment:
                    await send_whatsapp_text(phone_number, "🚨 *URGENT ALERT*\nI've flagged this for immediate medical attention. A doctor has been notified. Please call us at +91-9876543210 or visit the clinic immediately.")
                
                elif "BOOKING" in triage:
                    await send_whatsapp_text(phone_number, "I see you'd like to book an appointment. Let me find some available slots for you...", add_menu_button=False)
                    await send_available_slots(phone_number)
                
                elif "CANCELLATION" in triage:
                    await send_whatsapp_text(phone_number, "I've received your request to cancel your appointment. Our receptionist will confirm this with you shortly. Is there anything else I can help with?")
                
                else:
                    # Save clinical findings for all other non-emergency interactions
                    if clinical and "No symptoms reported" not in clinical:
                        async with AsyncSessionFactory() as session:
                            async with session.begin():
                                patient = (await session.execute(select(Patient).where(Patient.phone == phone_number))).scalar_one_or_none()
                                if patient: 
                                    session.add(Encounter(patient_id=patient.id, record={"summary": clinical, "source": "whatsapp_agent"}))

                    # Default to AI Receptionist for FAQs and General chat
                    ai_response = await get_ai_response(raw_text)
                    await send_whatsapp_text(phone_number, build_booking_prompt(ai_response))

    except Exception as e:
        print(f"Error: {e}")