# Design Document: ClinicOS Platform Standardization

## Overview

ClinicOS is a WhatsApp-first SaaS platform for Indian clinics. This standardization effort migrates the platform from a Streamlit prototype to a production-grade architecture with a React/Next.js frontend, a clean monorepo directory structure, and a REST API layer that decouples the dashboard from the database.

The core backend logic — WhatsApp webhook, AI agent swarm, APScheduler reminders, Twilio IVR, ReportLab PDF generation, and the SQLAlchemy ORM — is preserved entirely. The primary changes are:

1. **Directory reorganization**: `/app` → `/backend/app`, `agents/` → `/backend/agents/`
2. **Frontend replacement**: Streamlit dashboard → React/Next.js with three views (Admin, Owner, EMR)
3. **API layer addition**: New `/api/*` endpoints alongside the existing webhook endpoints
4. **Documentation refresh**: Legacy `.txt` files replaced with structured Markdown docs

The business outcome is a deployable, maintainable platform that reduces patient no-shows by 20–40% through automated WhatsApp reminders and IVR auto-callbacks.

---

## Architecture

### High-Level System Flow

```mermaid
flowchart TD
    Patient -->|WhatsApp message| MetaAPI[Meta WhatsApp API]
    Patient -->|Voice call| Twilio[Twilio IVR]
    MetaAPI -->|POST /webhook| Backend
    Twilio -->|POST /voice/*| Backend
    Backend -->|AI analysis| AgentSwarm[AI Agent Swarm\n6 agents via Groq]
    Backend -->|Read/Write| DB[(PostgreSQL)]
    Backend -->|Outbound messages| MetaAPI
    Backend -->|Outbound calls| Twilio
    Backend -->|Sync| GoogleCal[Google Calendar]
    Scheduler[APScheduler\nHourly] -->|check_and_send_reminders| Backend
    Frontend[React/Next.js\nDashboard] -->|GET/PATCH /api/*| Backend
    Receptionist -->|Browser| Frontend
    Owner -->|Browser| Frontend
    Doctor -->|Browser| Frontend
```

### Monorepo Directory Structure

```
/
├── frontend/                    # React/Next.js application
│   ├── app/                     # Next.js 14 App Router pages
│   │   ├── dashboard/page.tsx   # Admin Dashboard (receptionist)
│   │   ├── owner/page.tsx       # Owner Dashboard (money view)
│   │   ├── emr/page.tsx         # Lightweight EMR view
│   │   └── layout.tsx           # Root layout with sidebar
│   ├── components/              # Shared UI components
│   │   ├── ui/                  # shadcn/ui primitives
│   │   ├── AppointmentCard.tsx
│   │   ├── KPICard.tsx
│   │   ├── RevenueTrendChart.tsx
│   │   ├── PatientSearch.tsx
│   │   └── Sidebar.tsx
│   ├── lib/
│   │   ├── api.ts               # Typed API client (fetch wrappers)
│   │   └── utils.ts
│   ├── package.json
│   ├── tailwind.config.ts
│   └── tsconfig.json
│
├── backend/                     # FastAPI application (migrated from /app)
│   ├── app/
│   │   ├── main.py              # FastAPI app, webhooks, API routes
│   │   ├── database.py          # SQLAlchemy ORM models
│   │   ├── analytics_service.py
│   │   ├── reminders.py
│   │   ├── pdf_service.py
│   │   ├── calendar_sync_service.py
│   │   ├── voice.py
│   │   └── init_db.py
│   ├── agents/                  # AI agent .agent.md files
│   ├── requirements.txt
│   └── Dockerfile
│
├── docs/
│   ├── SETUP.md
│   ├── HOSTING.md
│   └── architecture.md
│
├── docker-compose.yml           # Updated build context → ./backend
├── .env.example
└── README.md                    # New business-focused README
```

### Import Path Strategy

The backend Python package structure inside `/backend` keeps `app` as the top-level package name. The `Dockerfile` sets `WORKDIR /backend` and runs `uvicorn app.main:app`, so all existing `from app.xxx import yyy` imports remain unchanged. No Python import paths need to be modified.

---

## Components and Interfaces

### Backend Components

#### 1. FastAPI Application (`backend/app/main.py`)

Existing endpoints preserved as-is:
- `GET /webhook` — Meta webhook verification
- `POST /webhook` — WhatsApp message ingestion
- `POST /prescription/send` — Prescription PDF delivery
- `POST /voice/*` — Twilio IVR router (via `voice.py` router)

New endpoints added under `/api` prefix:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/appointments` | List appointments with optional filters |
| PATCH | `/api/appointments/{id}/status` | Update appointment status |
| GET | `/api/analytics/daily` | Daily revenue and appointment stats |
| GET | `/api/analytics/monthly` | Monthly revenue, no-show rate, daily breakdown |
| GET | `/api/patients` | List patients with optional name/phone search |
| GET | `/api/patients/{id}/encounters` | Last 10 encounters for a patient |

CORS middleware is added to allow requests from the frontend origin.

#### 2. Analytics Service (`backend/app/analytics_service.py`)

Existing `AnalyticsService` class is reused directly by the new API endpoints. No changes required to the service logic.

#### 3. Reminder Service (`backend/app/reminders.py`)

Existing `check_and_send_reminders()` and `send_voice_reminder()` functions are preserved. The APScheduler runs inside the FastAPI process, started on the `startup` event.

#### 4. Voice IVR Router (`backend/app/voice.py`)

Existing Twilio TwiML routes preserved. The `APIRouter` with prefix `/voice` is included in `main.py` unchanged.

#### 5. PDF Service (`backend/app/pdf_service.py`)

`generate_prescription_pdf()` is preserved. Called by the `/prescription/send` endpoint.

#### 6. AI Agent Swarm (`backend/agents/`)

Six `.agent.md` files loaded dynamically by `AgentManager._load_agents()`. The path resolution `os.path.join(os.path.dirname(__file__), "..", "agents")` continues to work because `agents/` is now a sibling of `app/` inside `/backend`.

### Frontend Components

#### Page: Admin Dashboard (`/dashboard`)

```
AdminDashboard
├── KPIStrip (today's count, open slots, estimated revenue)
├── AppointmentColumns
│   ├── ConfirmedColumn (status = booked)
│   ├── WaitingColumn (status = waiting)
│   └── CompletedColumn (status = completed)
├── UpcomingSection (next 24 hours, sorted by scheduled_start)
└── MissedSection (status = missed, today in IST)
```

Each `AppointmentCard` displays: patient name, phone, scheduled time (IST), status badge, booking ID, and status-change action buttons.

Data is fetched via React Query with a 30-second polling interval (`refetchInterval: 30000`).

#### Page: Owner Dashboard (`/owner`)

```
OwnerDashboard
├── MonthPicker
├── KPICards (Today Revenue, Today Completed, Monthly Revenue, No-Show Rate)
├── PatientVolumeCards (Total, Returning, Avg Visits)
├── RevenueTrendChart (Recharts LineChart, one point per day)
└── MissedAnalyticsSection (daily + monthly no-show counts)
```

Data is fetched on mount and on manual "Refresh" button click. Month picker triggers a new API call with `year` and `month` parameters.

#### Page: EMR View (`/emr`)

```
EMRView
├── PatientSearchInput (filters by name or phone)
├── PatientList (search results)
└── EncounterHistory
    ├── PatientHeader (name, phone, registration date)
    └── EncounterList (last 10, sorted by created_at desc)
        └── EncounterCard (expandable, shows full JSON record)
```

#### Shared Components

- **`Sidebar`**: Dark sidebar (`#0f172a`) with navigation links to `/dashboard`, `/owner`, `/emr`. Active link highlighted in teal (`#0f8b8d`).
- **`KPICard`**: Metric card with label, value, and optional delta indicator.
- **`RevenueTrendChart`**: Recharts `LineChart` with teal stroke (`#0f8b8d`), responsive container.
- **`AppointmentCard`**: Card with status badge (color-coded), patient info, and action buttons.
- **`PatientSearch`**: Controlled input with debounced query forwarded to `/api/patients?search=`.

### API Client (`frontend/lib/api.ts`)

Typed fetch wrappers for all backend endpoints. Base URL read from `NEXT_PUBLIC_API_URL` environment variable. All functions return typed response objects.

```typescript
// Example signatures
getAppointments(params: AppointmentQueryParams): Promise<Appointment[]>
patchAppointmentStatus(id: number, status: AppointmentStatus): Promise<Appointment>
getDailyAnalytics(date?: string): Promise<DailyAnalytics>
getMonthlyAnalytics(year: number, month: number): Promise<MonthlyAnalytics>
getPatients(search?: string): Promise<Patient[]>
getPatientEncounters(patientId: number): Promise<Encounter[]>
```

---

## Data Models

### Existing ORM Models (unchanged)

All models live in `backend/app/database.py` and map to the existing PostgreSQL schema.

| Table | Key Fields |
|-------|-----------|
| `Clinics` | id, name, timezone, created_at |
| `Patients` | id, full_name, email, phone, created_at |
| `Doctors` | id, clinic_id, full_name, specialization, is_active |
| `Availability_Schedules` | id, clinic_id, slot_start, slot_end, is_open |
| `Appointments` | id, clinic_id, patient_id, doctor_id, schedule_id, scheduled_start, scheduled_end, status |
| `Encounters` | id, patient_id, record (JSONB), created_at |
| `CallLogs` | id, call_type, direction, created_at |
| `AuditLogs` | id, queried_patient_id, action, created_at |

Appointment `status` values: `booked`, `completed`, `missed`, `waiting`.

### API Request/Response Schemas (Pydantic)

New Pydantic models added to `main.py` for the `/api/*` endpoints:

```python
class AppointmentResponse(BaseModel):
    id: int
    clinic_id: int
    patient_id: int
    doctor_id: Optional[int]
    scheduled_start: datetime
    scheduled_end: datetime
    status: str
    patient_name: str
    patient_phone: Optional[str]
    booking_id_display: str  # zero-padded, e.g. "0042"

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
    phone: Optional[str]
    email: str
    created_at: datetime

class EncounterResponse(BaseModel):
    id: int
    patient_id: int
    record: dict
    created_at: datetime
```

### Frontend TypeScript Types

Mirror the Pydantic schemas in `frontend/lib/types.ts`:

```typescript
type AppointmentStatus = "booked" | "completed" | "missed" | "waiting";

interface Appointment {
  id: number;
  clinic_id: number;
  patient_id: number;
  doctor_id: number | null;
  scheduled_start: string; // ISO 8601
  scheduled_end: string;
  status: AppointmentStatus;
  patient_name: string;
  patient_phone: string | null;
  booking_id_display: string;
}

interface DailyAnalytics {
  date: string;
  total_appointments: number;
  completed: number;
  missed: number;
  revenue: number;
}

interface MonthlyAnalytics {
  month: string;
  total_revenue: number;
  total_appointments: number;
  completed_appointments: number;
  missed_appointments: number;
  no_show_rate: number;
  daily_breakdown: DailyAnalytics[];
}

interface Patient {
  id: number;
  full_name: string;
  phone: string | null;
  email: string;
  created_at: string;
}

interface Encounter {
  id: number;
  patient_id: number;
  record: Record<string, unknown>;
  created_at: string;
}
```

### Environment Variables

All configuration is read from environment variables. The `.env.example` documents:

```
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/clinic_booking

# Meta WhatsApp API (required)
META_PHONE_ID=
META_ACCESS_TOKEN=
META_VERIFY_TOKEN=

# AI (required for agent swarm)
GROQ_API_KEY=
GEMINI_API_KEY=

# Twilio IVR (optional — IVR calls skipped if missing)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=

# Google Calendar (optional)
GOOGLE_CREDENTIALS_FILE=/backend/google_credentials.json

# Frontend (Next.js)
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Appointment status update is reflected in subsequent reads

*For any* appointment in the database, after a PATCH request updates its status to a valid value, a subsequent GET request for that appointment SHALL return the updated status value.

**Validates: Requirements 5.2**

### Property 2: Daily revenue equals completed appointments times fee

*For any* date and clinic, the `revenue` field returned by `GET /api/analytics/daily` SHALL equal the count of appointments with `status = "completed"` on that date multiplied by ₹500.

**Validates: Requirements 3.2, 5.3**

### Property 3: Monthly no-show rate is consistent with daily breakdown

*For any* year and month, the `no_show_rate` in the monthly analytics response SHALL equal `(sum of missed across daily_breakdown) / (sum of total_appointments across daily_breakdown) × 100`, within floating-point tolerance.

**Validates: Requirements 3.2, 5.4**

### Property 4: Patient search is a subset filter

*For any* non-empty search string, every patient returned by `GET /api/patients?search=<query>` SHALL have a `full_name` or `phone` that contains the query string (case-insensitive). No patient whose name and phone both exclude the query string SHALL appear in the results.

**Validates: Requirements 4.4, 5.5**

### Property 5: Encounter list is bounded and ordered

*For any* patient, `GET /api/patients/{id}/encounters` SHALL return at most 10 records, and the records SHALL be sorted by `created_at` in descending order (most recent first).

**Validates: Requirements 4.2, 5.6**

### Property 6: Prescription filename sanitization removes unsafe characters

*For any* patient name string, the filename produced by the prescription service SHALL contain only alphanumeric characters and underscores, and SHALL NOT contain spaces, slashes, or other filesystem-unsafe characters.

**Validates: Requirements 8.6**

### Property 7: Slot booking is exclusive under concurrency

*For any* availability slot, after a successful `book_appointment_slot` transaction, the slot's `is_open` field SHALL be `False` and no second transaction for the same slot SHALL succeed — it SHALL raise `SlotNotAvailableError` or `SlotAlreadyLockedError`.

**Validates: Requirements 6.4**

---

## Error Handling

### Backend Error Handling

| Scenario | HTTP Status | Response |
|----------|-------------|----------|
| Invalid `appointment_id` in PATCH | 404 | `{"detail": "Appointment <id> not found"}` |
| Invalid `status` value in PATCH | 422 | Pydantic validation error with field details |
| Concurrent slot booking conflict | 409 | `{"detail": "Slot is no longer available"}` |
| Missing required env var at startup | — | Log error + `sys.exit(1)` |
| Meta API media upload failure | 502 | `{"detail": "Prescription PDF delivery failed"}` |
| Twilio credentials missing | — | Log warning, skip IVR call, continue |
| Database connection failure | 503 | `{"detail": "Database unavailable"}` |

### Frontend Error Handling

- **API errors**: React Query's `onError` callback displays a toast notification with the error message.
- **Network timeout**: Requests time out after 10 seconds; a retry button is shown.
- **Empty states**: Each dashboard section renders a descriptive empty-state message (e.g., "No appointments today", "No clinical records found").
- **Status update failure**: Optimistic UI update is rolled back if the PATCH request fails; the original status is restored.

### Startup Validation

At FastAPI startup, the backend checks for required environment variables (`DATABASE_URL`, `META_PHONE_ID`, `META_ACCESS_TOKEN`). If any are missing, it logs a descriptive error identifying the missing variable and exits with code 1 before accepting any requests.

---

## Testing Strategy

### Assessment: PBT Applicability

This feature is a mix of infrastructure reorganization, REST API additions, and a React frontend. The pure-logic components — analytics calculations, prescription filename sanitization, slot booking exclusivity, and search filtering — are suitable for property-based testing. UI rendering, Docker configuration, and infrastructure wiring are not.

### Unit Tests (Backend)

Focus areas:
- `AnalyticsService` methods: verify revenue calculation, no-show rate formula, daily breakdown aggregation
- `generate_prescription_pdf`: verify PDF bytes are non-empty and filename sanitization logic
- Pydantic schema validation: verify `AppointmentStatusUpdate` rejects invalid status values
- `book_appointment_slot`: verify slot locking behavior with concurrent sessions

### Property-Based Tests (Backend)

Use **Hypothesis** (Python PBT library). Each property test runs a minimum of 100 iterations.

**Property 1 — Status round-trip** *(Feature: clinicos-platform-standardization, Property 1: appointment status update is reflected in subsequent reads)*
Generate random valid appointment IDs and valid status values; PATCH then GET and assert equality.

**Property 2 — Revenue formula** *(Feature: clinicos-platform-standardization, Property 2: daily revenue equals completed appointments times fee)*
Generate random sets of appointments with varying statuses; compute expected revenue as `count(completed) * 500`; assert it matches the analytics service output.

**Property 3 — No-show rate consistency** *(Feature: clinicos-platform-standardization, Property 3: monthly no-show rate is consistent with daily breakdown)*
Generate random daily breakdown arrays; compute expected rate from the array; assert it matches the `no_show_rate` field.

**Property 4 — Patient search subset** *(Feature: clinicos-platform-standardization, Property 4: patient search is a subset filter)*
Generate random patient lists and search strings; assert all returned patients contain the query in name or phone.

**Property 5 — Encounter ordering and bound** *(Feature: clinicos-platform-standardization, Property 5: encounter list is bounded and ordered)*
Generate random encounter lists of varying lengths; assert the returned list has ≤ 10 items and is sorted descending by `created_at`.

**Property 6 — Filename sanitization** *(Feature: clinicos-platform-standardization, Property 6: prescription filename sanitization removes unsafe characters)*
Generate arbitrary Unicode strings as patient names; assert the resulting filename matches `^[a-zA-Z0-9_]+\.pdf$`.

**Property 7 — Slot booking exclusivity** *(Feature: clinicos-platform-standardization, Property 7: slot booking is exclusive under concurrency)*
Generate random slot configurations; attempt two concurrent bookings for the same slot; assert exactly one succeeds and the other raises the appropriate error.

### Integration Tests

- Docker Compose stack starts cleanly and the backend responds to `GET /webhook` with 403 (missing token)
- `POST /webhook` with a valid Meta payload returns `{"status": "success"}`
- `GET /api/appointments` returns a JSON array (may be empty) with correct schema
- `POST /prescription/send` with mocked Meta API returns HTTP 200

### Frontend Tests

- **Unit tests** (Vitest + React Testing Library): `AppointmentCard` renders patient name, phone, status badge, and booking ID; `RevenueTrendChart` renders without crashing given empty data; `PatientSearch` debounces input correctly.
- **Snapshot tests**: Sidebar navigation renders all three links; KPICard renders label and value.
- No property-based tests for UI components — snapshot and example-based tests are appropriate here.

### Test Configuration

- Backend: `pytest` with `pytest-asyncio` for async tests, `hypothesis` for PBT
- Frontend: `vitest --run` for single-pass CI execution
- Minimum 100 iterations per Hypothesis property test (default Hypothesis `max_examples=100`)
