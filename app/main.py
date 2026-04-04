import os
from datetime import timezone
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from google import genai
from sqlalchemy.exc import IntegrityError
from openai import AsyncOpenAI
from sqlalchemy import select
from app.database import Appointment, AsyncSessionFactory, Availability_Schedule, Patient

load_dotenv()
app = FastAPI()
IST = ZoneInfo("Asia/Kolkata")


def format_slot_for_whatsapp(slot_start) -> str:
    if slot_start.tzinfo is None:
        slot_start = slot_start.replace(tzinfo=timezone.utc)
    return slot_start.astimezone(IST).strftime('%b %d at %I:%M %p')

def build_booking_prompt(reply: str) -> str:
    return (
        f"{reply}\n\n"
        "If you would like to book an appointment, type *book appointment* anytime."
    )

def get_profile_name(entry: dict) -> str:
    contacts = entry.get("contacts") or []
    if contacts and isinstance(contacts, list):
        profile = contacts[0].get("profile") or {}
        profile_name = profile.get("name")
        if profile_name:
            return profile_name
    return "Patient"

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

# Point the OpenAI client directly to Groq's super-fast servers
groq_client = AsyncOpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

# --- THE AI BRAIN ---
async def get_ai_response(user_question: str) -> str:
    """Sends the patient's question to the LLM with strict clinic rules."""
    
    system_prompt = """
    You are Sarah, the friendly AI receptionist for City Health Clinic. 
    Keep your answers very brief, professional, and conversational (1-2 sentences max).
    
    CLINIC KNOWLEDGE BASE:
    - Working hours: Monday to Friday, 9:00 AM to 5:00 PM.
    - Location: 123 Main Street, Noida.
    - Insurances accepted: Bajaj Allianz, HDFC ERGO, and Star Health.
    - Services: General checkups, Physiotherapy, and Dental cleaning.
    - Prices: General checkup is ₹500. Dental cleaning is ₹1200.
    
    RULES:
    1. Do NOT diagnose medical conditions. Tell them to book an appointment.
    2. If they ask something outside this knowledge base, say: "I'm still learning! Please call the clinic directly at +91-9876543210 for that specific question."
    """
    
    try:
        response = await groq_client.chat.completions.create(
            model="llama-3.1-8b-instant", # Groq's insanely fast model
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_question}
            ],
            temperature=0.3 # Low temperature keeps the AI from hallucinating
        )
        return response.choices[0].message.content or "I could not generate a response right now."
    except Exception as e:
        print(f"❌ AI Error: {e}")
        return "I'm currently undergoing maintenance. Please try again in a few minutes!"
async def generate_ai_response(user_text: str) -> str:
    if gemini_client is None: return "Gemini is not configured."
    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                "You are a helpful receptionist for City Health Clinic. Open Mon-Sat, 9 AM to 6 PM. Fee is 500 INR. Keep responses under 2 sentences.",
                user_text
            ]
        )
        return response.text or "I could not generate a response right now."
    except Exception as e:
        print(f"AI Error: {e}")
        return "I'm having trouble connecting to my knowledge base."

# --- THE OUTBOUND ENGINE ---
async def send_to_meta(payload: dict):
    """Fires the JSON payload to Meta's actual servers."""
    META_PHONE_ID = os.getenv("META_PHONE_ID")
    META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
    
    if not META_PHONE_ID or not META_ACCESS_TOKEN:
        print("⚠️ Missing Meta Credentials in .env!")
        return

    url = f"https://graph.facebook.com/v18.0/{META_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            print("✅ Delivered to WhatsApp!")
        except httpx.HTTPStatusError as e:
            print(f"❌ Meta API Error: {e.response.text}")
        except Exception as e:
            print(f"❌ Network Error: {e}")

async def send_whatsapp_text(to_phone: str, reply_text: str):
    print(f"\n🚀 SENDING TEXT TO {to_phone}: {reply_text}\n")
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": reply_text}
    }
    await send_to_meta(payload)

async def send_whatsapp_interactive_menu(to_phone: str):
    print(f"\n🚀 SENDING MAIN MENU TO {to_phone}\n")
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "Welcome to City Health Clinic! How can I help you today?"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "btn_book_appt", "title": "Book Appointment"}},
                    {"type": "reply", "reply": {"id": "btn_ask_question", "title": "Ask a Question"}}
                ]
            }
        }
    }
    await send_to_meta(payload)

# --- UPDATED: DYNAMIC LIST GENERATOR ---
async def send_whatsapp_list(to_phone: str, formatted_rows: list):
    """Dynamically builds the WhatsApp list based on formatted dictionary rows."""
    print(f"\n🚀 SENDING TIME SLOTS TO {to_phone}\n")
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": "Available Slots"},
            "body": {"text": "Please select a time for your appointment:"},
            "action": {
                "button": "Select a Time",
                # FIX 2: We pass the 'formatted_rows' variable directly here
                "sections": [{"title": "Upcoming Slots", "rows": formatted_rows}]
            }
        }
    }
    await send_to_meta(payload)

# --- THE WEBHOOK ENDPOINTS ---
@app.get("/")
async def root(): return {"status": "Alive!"}
@app.get("/webhook")
async def verify_webhook(request: Request):
    """Handles the strict security handshake from Meta's servers."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    # Check if Meta is the one knocking, and if they have the right password
    if mode == "subscribe" and token == os.getenv("META_VERIFY_TOKEN"):
        print("✅ Meta Webhook Verification Successful!")
        # Meta STRICTLY requires returning the challenge as raw text
        return PlainTextResponse(content=challenge, status_code=200)
    else:
        print("❌ Webhook Verification Failed.")
        raise HTTPException(status_code=403, detail="Verification failed")

@app.post("/webhook")
async def receive_whatsapp_message(request: Request):
    body = await request.json()
    
    try:
        # Dig into the massive Meta JSON payload to find the message
        entry = body['entry'][0]['changes'][0]['value']
        
        if 'messages' in entry:
            msg = entry['messages'][0]
            phone_number = msg['from']
            msg_type = msg['type']
            
           # SCENARIO 1: The user clicked a menu button OR selected a list item
            if msg_type == 'interactive':
                interactive_type = msg['interactive']['type']
                
                # --- A. They clicked a standard button ---
                if interactive_type == 'button_reply':
                    button_id = msg['interactive']['button_reply']['id']
                    
                    if button_id == 'btn_book_appt':
                        await send_available_slots(phone_number)
                    
                    elif button_id == 'btn_ask_question':
                        await send_whatsapp_text(phone_number, "Of course! What would you like to know about City Health Clinic?")

                # --- B. They selected a time from the List Menu ---
                elif interactive_type == 'list_reply':
                    selected_slot_id = msg['interactive']['list_reply'].get('id', '')

                    if selected_slot_id.startswith("slot_"):
                        try:
                            # Extract the database ID (e.g., "slot_4" -> 4).
                            db_id = int(selected_slot_id.split("_", 1)[1])
                            patient_name = get_profile_name(entry)
                            booking_code = None

                            async with AsyncSessionFactory() as session:
                                async with session.begin():
                                    slot_stmt = (
                                        select(Availability_Schedule)
                                        .where(Availability_Schedule.id == db_id)
                                        .with_for_update()
                                    )
                                    slot_result = await session.execute(slot_stmt)
                                    slot = slot_result.scalar_one_or_none()

                                    if slot is None or not slot.is_open:
                                        await send_whatsapp_text(
                                            phone_number,
                                            "Sorry, that slot was just taken. Please choose another available slot.",
                                        )
                                        return {"status": "success"}

                                    patient_stmt = select(Patient).where(Patient.phone == phone_number).limit(1)
                                    patient_result = await session.execute(patient_stmt)
                                    patient = patient_result.scalar_one_or_none()

                                    if patient is None:
                                        patient = Patient(
                                            full_name=patient_name,
                                            email=phone_to_email(phone_number),
                                            phone=phone_number,
                                        )
                                        session.add(patient)
                                        await session.flush()
                                    elif patient_name and patient.full_name != patient_name:
                                        patient.full_name = patient_name

                                    appointment = Appointment(
                                        clinic_id=slot.clinic_id,
                                        patient_id=patient.id,
                                        schedule_id=slot.id,
                                        scheduled_start=slot.slot_start,
                                        scheduled_end=slot.slot_end,
                                        status="booked",
                                    )
                                    session.add(appointment)

                                    slot.is_open = False
                                    await session.flush()

                                    booking_code = f"{appointment.id:04d}"

                            if booking_code is not None and slot is not None:
                                await send_whatsapp_text(
                                    phone_number,
                                    (
                                        "Your appointment is confirmed for "
                                        f"{format_slot_for_whatsapp(slot.slot_start)}. "
                                        f"Your booking ID is *{booking_code}*. "
                                        "Please pay ₹500 at the reception and show this booking ID."
                                    ),
                                )
                            else:
                                await send_whatsapp_text(
                                    phone_number,
                                    "Sorry, that slot was just taken. Please choose another available slot.",
                                )
                        except IntegrityError:
                            await send_whatsapp_text(
                                phone_number,
                                "Sorry, that slot was just taken. Please choose another available slot.",
                            )
                        except (ValueError, IndexError):
                            await send_whatsapp_text(
                                phone_number,
                                "I could not read that slot selection. Please choose a slot again from the list.",
                            )
                        except Exception as e:
                            print(f"Slot booking update error: {e}")
                            await send_whatsapp_text(
                                phone_number,
                                "Sorry, we could not confirm your booking right now. Please try again.",
                            )
            # SCENARIO 2: The user typed a text message
            elif msg_type == 'text':
                raw_text = msg['text']['body'].strip()
                user_text = raw_text.lower()

                await send_whatsapp_text(phone_number, WELCOME_GUIDE)

                if 'book appointment' in user_text:
                    await send_available_slots(phone_number)
                elif user_text in ['hi', 'hello', 'hey', 'menu', 'start']:
                    await send_whatsapp_interactive_menu(phone_number)
                else:
                    ai_answer = await get_ai_response(raw_text)
                    await send_whatsapp_text(phone_number, build_booking_prompt(ai_answer))

        return {"status": "success"}

    except Exception as e:
        print(f"Webhook Processing Error: {e}")
        return {"status": "error"}