# WhatsApp AI Booking SaaS (Clinic Reception)

A production-focused clinic booking system for WhatsApp + FastAPI + PostgreSQL + Streamlit receptionist dashboard.

## Features

- WhatsApp bot webhook using FastAPI.
- Dynamic slot list for booking from `Availability_Schedules`.
- Case-insensitive direct booking trigger (`book appointment`).
- Greeting + usage instructions on text messages.
- Appointment confirmation with 4-digit booking ID for payment matching.
- Patient capture (name + phone) into `Patients`.
- Appointment persistence in `Appointments` with statuses:
  - `booked`
  - `completed`
  - `missed`
- Receptionist dashboard for:
  - Booked appointments with patient details and booking ID
  - Available slots
  - Create/delete slots
  - Update appointment status
  - Time filters: Today / This Week / All
  - Color-coded status badges
- Timezone-safe display aligned to Asia/Kolkata.

## Tech Stack

- FastAPI
- SQLAlchemy (async engine for API)
- PostgreSQL
- Streamlit + Pandas + sync SQLAlchemy/psycopg2 for dashboard
- Meta WhatsApp Cloud API
- OpenAI-compatible Groq client for conversational responses

## Project Structure

- `app/main.py`: FastAPI webhook + WhatsApp logic
- `app/database.py`: ORM models + async DB setup
- `app/dashboard.py`: Streamlit receptionist dashboard
- `app/init_db.py`: DB initialization + sample seed helper
- `app/calendar_sync.py`: Google Calendar sync helper
- `.env`: Environment variables (local only)

## Database Models Used

- `Clinics`
- `Patients`
- `Availability_Schedules`
- `Appointments`

## Booking Flow

1. User sends `book appointment` (any case) or taps booking button.
2. Bot fetches open slots and sends interactive list.
3. User picks a slot.
4. Bot locks/checks slot and creates:
   - Patient (if missing)
   - Appointment row with `status='booked'`
5. Bot marks slot closed (`is_open=False`).
6. Bot sends confirmation with 4-digit booking ID.

## Dashboard Flow

- View booked appointments with:
  - Booking ID
  - Patient name
  - Phone
  - Start/end
  - Status badge
- Filter by:
  - Today
  - This Week
  - All
- Create and delete open slots.
- Mark appointments as `completed` or `missed`.

## Environment Variables

Create `.env` in project root.

Required:

- `DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<host>:<port>/<db>`
- `META_VERIFY_TOKEN=<verify-token>`
- `META_PHONE_ID=<meta-phone-id>`
- `META_ACCESS_TOKEN=<meta-access-token>`
- `GROQ_API_KEY=<groq-key>`

Optional:

- `GEMINI_API_KEY=<gemini-key>`
- `GOOGLE_CALENDAR_ID=<calendar-id>`

## Setup

1. Create and activate virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Initialize DB tables/sample data (optional):

```bash
python app/init_db.py
```

## Run Services

API:

```bash
uvicorn app.main:app --reload
```

Dashboard:

```bash
streamlit run app/dashboard.py
```

## WhatsApp Webhook Endpoints

- `GET /webhook` for Meta verification
- `POST /webhook` for incoming messages

## Production Notes

- Keep `.env` and `google_credentials.json` out of version control.
- Use HTTPS webhook URL (for example, with ngrok in dev).
- Prefer managed PostgreSQL and secure secret storage in production.
- Add automated tests before scaling traffic.

## Quick User Commands (WhatsApp)

- `book appointment`: open slot list directly
- `hi` / `hello` / `menu`: show main menu
- any other text: AI reply + booking prompt + quick "Back to Main Menu" button
