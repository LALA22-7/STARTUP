# ClinicOS

**WhatsApp-first clinic management for Indian practices.**

ClinicOS reduces patient no-shows by 20–40% through automated WhatsApp reminders and dual-channel (WhatsApp + IVR) appointment management. Clinics get a real-time receptionist dashboard, an owner revenue view, and a lightweight EMR — all without asking patients to install an app.

---

## Why ClinicOS

Indian clinics lose significant revenue to no-shows. ClinicOS tackles this at the source:

- Patients book appointments entirely over WhatsApp — no app download, no web form
- Automated reminders go out 24 hours before each appointment via WhatsApp and voice call
- Patients who don't respond get an IVR auto-callback offering to confirm, cancel, or reschedule
- Receptionists manage the day from a live dashboard; owners track revenue and no-show trends

---

## System Architecture

```
Patient
  │
  ├─ WhatsApp message ──► Meta API ──► POST /webhook
  │                                         │
  │                                    AI Agent Swarm
  │                                    (Triage · Booking · Sentiment
  │                                     Clinical · Webhook · Orchestrator)
  │                                         │
  │                                    PostgreSQL DB
  │                                         │
  │                                    Reminder Service (APScheduler)
  │                                         │
  └─ WhatsApp reminder ◄── Meta API ◄───────┘
  └─ IVR auto-callback ◄── Twilio ◄─────────┘

Receptionist / Owner / Doctor
  │
  └─ Browser ──► React/Next.js Frontend ──► GET/PATCH /api/* ──► Backend
```

### Key Components

| Component | Technology | Role |
|-----------|-----------|------|
| Backend | FastAPI + SQLAlchemy | Webhook handler, REST API, business logic |
| Database | PostgreSQL 14+ | Appointments, patients, encounters, audit logs |
| AI Agent Swarm | Groq LLM (6 agents) | Message triage, booking extraction, clinical notes |
| Reminder Service | APScheduler | Hourly check; sends WhatsApp + IVR reminders |
| IVR Auto-Callback | Twilio | Voice calls for non-responders and no-show recovery |
| Prescription Service | ReportLab + Meta API | PDF generation and WhatsApp document delivery |
| Frontend | Next.js 14 + Tailwind | Admin dashboard, owner analytics, EMR view |

---

## Dashboard Views

**Admin Dashboard (`/dashboard`)** — Receptionist control center. Live appointment queues (Confirmed, Waiting, Completed), upcoming appointments for the next 24 hours, and today's missed list. Status updates reflect within 2 seconds.

**Owner Dashboard (`/owner`)** — Revenue and operations. Today's revenue, monthly totals, no-show rate, patient volume metrics, and a daily revenue trend chart. Supports month-picker for historical data.

**EMR View (`/emr`)** — Patient clinical history. Search patients by name or phone, view their last 10 encounters with expandable clinical notes.

---

## Tech Stack

```
backend/
  app/main.py              FastAPI app — webhooks, REST API, CORS
  app/database.py          SQLAlchemy ORM (8 tables)
  app/analytics_service.py Revenue and no-show calculations
  app/reminders.py         APScheduler reminder jobs
  app/pdf_service.py       ReportLab prescription PDFs
  app/voice.py             Twilio IVR TwiML routes
  agents/                  Six AI agent definition files

frontend/
  app/dashboard/           Admin Dashboard page
  app/owner/               Owner Dashboard page
  app/emr/                 EMR View page
  components/              AppointmentCard, KPICard, RevenueTrendChart, etc.
  lib/api.ts               Typed fetch wrappers for all backend endpoints
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL 14+
- Node.js 18+

### 1. Clone and configure

```bash
git clone <repository>
cp .env.example .env
# Fill in required values in .env (see docs/SETUP.md)
```

### 2. Start with Docker Compose

```bash
docker compose up --build
```

The backend starts at `http://localhost:8000` and the frontend at `http://localhost:3000`.

### 3. Manual start (development)

```bash
# Backend
cd backend
pip install -r requirements.txt
python app/init_db.py        # create tables and seed data
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

API docs are available at `http://localhost:8000/docs`.

---

## REST API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/appointments` | List appointments (filter by clinic, status, date range) |
| PATCH | `/api/appointments/{id}/status` | Update appointment status |
| GET | `/api/analytics/daily` | Daily revenue and appointment counts |
| GET | `/api/analytics/monthly` | Monthly revenue, no-show rate, daily breakdown |
| GET | `/api/patients` | List patients (search by name or phone) |
| GET | `/api/patients/{id}/encounters` | Last 10 clinical encounters for a patient |
| POST | `/webhook` | Meta WhatsApp webhook receiver |
| GET | `/webhook` | Meta webhook verification |
| POST | `/prescription/send` | Generate and deliver prescription PDF via WhatsApp |
| POST | `/voice/*` | Twilio IVR TwiML routes |

---

## Environment Variables

Copy `.env.example` to `.env` and fill in your values. Required variables:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string |
| `META_PHONE_ID` | Meta WhatsApp Business phone number ID |
| `META_ACCESS_TOKEN` | Meta API access token |
| `META_VERIFY_TOKEN` | Webhook verification secret |
| `GROQ_API_KEY` | LLM key for the AI agent swarm |
| `GEMINI_API_KEY` | Gemini AI key |

Optional (IVR and calendar features degrade gracefully when absent):

| Variable | Purpose |
|----------|---------|
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_PHONE_NUMBER` | Twilio outbound phone number |
| `GOOGLE_CREDENTIALS_FILE` | Path to Google Calendar service account JSON |
| `NEXT_PUBLIC_API_URL` | Backend URL consumed by the frontend (default: `http://localhost:8000`) |

See [docs/SETUP.md](docs/SETUP.md) for step-by-step credential setup and [docs/HOSTING.md](docs/HOSTING.md) for deployment instructions.

---

## Documentation

- [docs/SETUP.md](docs/SETUP.md) — Credential setup, database migrations, local development
- [docs/HOSTING.md](docs/HOSTING.md) — Deploying to Railway/Render (backend) and Vercel (frontend)
