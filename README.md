# ClinicOS

**WhatsApp-first clinic management for Indian practices.**

ClinicOS reduces patient no-shows by 20–40% through automated WhatsApp reminders and dual-channel (WhatsApp + IVR) appointment management. Clinics get a real-time receptionist dashboard, an owner revenue view, and a lightweight EMR — all without asking patients to install an app.

**Live Demo**
- Frontend: [https://clinicos-nine-ashy.vercel.app](https://clinicos-nine-ashy.vercel.app)
- Backend API: [https://startup-nqlw.onrender.com/docs](https://startup-nqlw.onrender.com/docs)

---

## Why ClinicOS

Indian clinics lose significant revenue to no-shows. ClinicOS tackles this at the source:

- Patients book appointments entirely over WhatsApp — no app download, no web form
- Automated reminders go out 24 hours before each appointment via WhatsApp and voice call
- Patients who don't respond get an IVR auto-callback offering to confirm, cancel, or reschedule
- Receptionists manage the day from a live dashboard with full slot and appointment control
- Owners track revenue, no-show rates, and patient volume from a dedicated analytics view

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
  └─ Browser ──► React/Next.js Frontend ──► GET/PATCH/POST/DELETE /api/* ──► Backend
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

**Admin Dashboard (`/dashboard`)** — Receptionist control center. Live appointment queues (Confirmed, Waiting, Completed), upcoming appointments for the next 24 hours, and today's missed list. Receptionists can add new appointments, manage available slots, mark appointments as completed or missed, and delete appointments — all from the dashboard. Status updates reflect within 2 seconds.

**Owner Dashboard (`/owner`)** — Revenue and operations. Today's revenue, monthly totals, no-show rate, patient volume metrics, and a daily revenue trend chart. Supports month-picker for historical data.

**EMR View (`/emr`)** — Patient clinical history. Search patients by name or phone, view their last 10 encounters with expandable clinical notes.

---

## Slot & Appointment Management

Receptionists can manage availability directly from the dashboard without touching the database:

- **Add slots** — Set date, start time, and end time in IST. Slots appear immediately on WhatsApp for patients to book.
- **Delete slots** — Remove open slots that are no longer available.
- **Book appointments manually** — Enter patient name and phone, select a slot, and create the booking. The patient record is created automatically if they don't exist yet.
- **Delete appointments** — Remove appointments with a confirmation step. The slot is automatically re-opened when an appointment is deleted.

---

## Tech Stack

```
backend/
  app/main.py              FastAPI app — webhooks, REST API, CORS, slot/appointment management
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
  components/              AppointmentCard, AddAppointmentModal, KPICard, RevenueTrendChart, etc.
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
git clone https://github.com/LALA22-7/STARTUP.git
cp .env.example .env
# Fill in required values in .env (see docs/SETUP.md)
```

### 2. Start with Docker Compose

```bash
docker compose up --build
```

The backend starts at `http://localhost:8000` and the frontend at `http://localhost:3000`.

### 3. Seed the database

On first run, call the seed endpoint to create the default clinic:

```bash
curl -X POST http://localhost:8000/admin/seed
```

### 4. Manual start (development)

```bash
# Backend
cd backend
pip install -r requirements.txt
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
| POST | `/api/appointments` | Manually create an appointment |
| PATCH | `/api/appointments/{id}/status` | Update appointment status |
| DELETE | `/api/appointments/{id}` | Delete appointment and re-open its slot |
| GET | `/api/slots` | List all slots for a clinic |
| POST | `/api/slots` | Create a new bookable slot |
| DELETE | `/api/slots/{id}` | Delete an open slot |
| GET | `/api/analytics/daily` | Daily revenue and appointment counts |
| GET | `/api/analytics/monthly` | Monthly revenue, no-show rate, daily breakdown |
| GET | `/api/patients` | List patients (search by name or phone) |
| GET | `/api/patients/{id}/encounters` | Last 10 clinical encounters for a patient |
| POST | `/admin/seed` | Seed default clinic data (run once on fresh database) |
| POST | `/webhook` | Meta WhatsApp webhook receiver |
| GET | `/webhook` | Meta webhook verification |
| POST | `/prescription/send` | Generate and deliver prescription PDF via WhatsApp |
| POST | `/voice/*` | Twilio IVR TwiML routes |

---

## Environment Variables

Copy `.env.example` to `.env` and fill in your values. Required variables:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string (`postgresql+asyncpg://...`) |
| `META_PHONE_ID` | Meta WhatsApp Business phone number ID |
| `META_ACCESS_TOKEN` | Meta API access token |
| `META_VERIFY_TOKEN` | Webhook verification secret |
| `GROQ_API_KEY` | LLM key for the AI agent swarm |
| `GEMINI_API_KEY` | Gemini AI key |

Optional (features degrade gracefully when absent):

| Variable | Purpose |
|----------|---------|
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_PHONE_NUMBER` | Twilio outbound phone number |
| `GOOGLE_CREDENTIALS_JSON` | Full Google service account JSON as a string (for cloud deployments) |
| `GOOGLE_CREDENTIALS_FILE` | Path to Google Calendar service account JSON (for local/Docker) |
| `NEXT_PUBLIC_API_URL` | Backend URL consumed by the frontend (default: `http://localhost:8000`) |

See [docs/SETUP.md](docs/SETUP.md) for step-by-step credential setup and [docs/HOSTING.md](docs/HOSTING.md) for deployment instructions.

---

## Running Tests

```bash
# Backend — property-based and unit tests (31 tests)
cd backend
pytest tests/ -v

# Frontend — component tests (45 tests)
cd frontend
npx vitest --run
```

---

## Documentation

- [docs/SETUP.md](docs/SETUP.md) — Credential setup, database migrations, local development
- [docs/HOSTING.md](docs/HOSTING.md) — Deploying to Railway/Render (backend) and Vercel (frontend)
