# Implementation Plan: ClinicOS Platform Standardization

## Overview

Migrate ClinicOS from a Streamlit prototype to a production-grade monorepo with a React/Next.js frontend, a clean `/backend` directory structure, a REST API layer, and refreshed documentation. All existing backend logic (WhatsApp webhook, AI agent swarm, APScheduler reminders, Twilio IVR, ReportLab PDF, SQLAlchemy ORM) is preserved — only moved and extended.

## Tasks

- [x] 1. Reorganize project structure into monorepo layout
  - [x] 1.1 Create `/backend` directory and move existing Python source
    - Create `backend/` directory at repo root
    - Move `app/` → `backend/app/` (all Python files: main.py, database.py, analytics_service.py, reminders.py, pdf_service.py, calendar_sync_service.py, voice.py, init_db.py)
    - Move `agents/` → `backend/agents/` (all six `.agent.md` files)
    - Move `requirements.txt` → `backend/requirements.txt`
    - _Requirements: 1.1, 1.2_

  - [x] 1.2 Update Dockerfile and docker-compose.yml for new paths
    - Update `Dockerfile` to set `WORKDIR /backend` and copy from `./backend`
    - Update `docker-compose.yml` build context to `./backend`
    - Verify `uvicorn app.main:app` command still resolves correctly (no Python import changes needed)
    - _Requirements: 1.4, 1.5_

  - [x] 1.3 Remove legacy artifacts
    - Delete `MANUAL_SETUP_GUIDE.txt`, `CONSOLIDATION_SUMMARY.txt`, `PROJECT_STATUS.txt` from repo root
    - Delete `app/dashboard.py` (Streamlit prototype)
    - _Requirements: 1.3_

  - [x] 1.4 Create `/docs` directory scaffold
    - Create `docs/` directory at repo root (placeholder for SETUP.md and HOSTING.md)
    - _Requirements: 1.1_

- [x] 2. Add environment standardization files
  - [x] 2.1 Create `.env.example` with all variables
    - Add `.env.example` at repo root with all required and optional variables: DATABASE_URL, META_PHONE_ID, META_ACCESS_TOKEN, META_VERIFY_TOKEN, GROQ_API_KEY, GEMINI_API_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, GOOGLE_CREDENTIALS_FILE, NEXT_PUBLIC_API_URL
    - Include inline comments describing each variable's purpose
    - _Requirements: 10.4_

  - [x] 2.2 Add startup environment validation to backend
    - In `backend/app/main.py`, add a startup check before the FastAPI app accepts requests
    - Check for required variables: DATABASE_URL, META_PHONE_ID, META_ACCESS_TOKEN
    - If any are missing, log a descriptive error naming the missing variable and call `sys.exit(1)`
    - _Requirements: 10.3_

  - [x] 2.3 Verify `.gitignore` covers `.env`
    - Confirm `.env` is listed in `.gitignore`; add it if missing
    - _Requirements: 10.5_

- [x] 3. Checkpoint — Verify backend still starts
  - Ensure all tests pass, ask the user if questions arise.
  - Confirm `uvicorn app.main:app` starts without errors from within `backend/`
  - Confirm `GET /webhook` returns 403 (missing token) and `POST /prescription/send` schema is intact

- [x] 4. Add backend REST API endpoints
  - [x] 4.1 Add Pydantic response models for API layer
    - Add to `backend/app/main.py`: `AppointmentResponse`, `AppointmentStatusUpdate`, `DailyAnalyticsResponse`, `MonthlyAnalyticsResponse`, `PatientResponse`, `EncounterResponse` Pydantic models as specified in the design
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 4.2 Add CORS middleware
    - Add `CORSMiddleware` to the FastAPI app in `backend/app/main.py`
    - Allow origins from `NEXT_PUBLIC_API_URL` env var (default `http://localhost:3000`)
    - Allow methods: GET, POST, PATCH, OPTIONS
    - _Requirements: 5.9_

  - [x] 4.3 Implement `GET /api/appointments`
    - Add endpoint to `backend/app/main.py` under `/api` prefix
    - Accept query params: `clinic_id` (required), `status` (optional), `date_from` (optional ISO date), `date_to` (optional ISO date)
    - Join `Appointments` with `Patients` to populate `patient_name`, `patient_phone`, `booking_id_display`
    - Return `List[AppointmentResponse]`
    - _Requirements: 5.1_

  - [x] 4.4 Implement `PATCH /api/appointments/{appointment_id}/status`
    - Add endpoint accepting `AppointmentStatusUpdate` body
    - Return HTTP 404 with `{"detail": "Appointment <id> not found"}` for unknown IDs
    - Return HTTP 422 for invalid status values (handled by Pydantic `Literal`)
    - Return updated `AppointmentResponse` on success
    - _Requirements: 5.2, 5.7, 5.8_

  - [x]* 4.5 Write property test for status round-trip (Property 1)
    - **Property 1: Appointment status update is reflected in subsequent reads**
    - Use Hypothesis to generate valid appointment IDs and status values; PATCH then GET and assert equality
    - **Validates: Requirements 5.2**

  - [x] 4.6 Implement `GET /api/analytics/daily`
    - Add endpoint delegating to `AnalyticsService.get_daily_revenue()`
    - Accept `date` query param (ISO date string, defaults to today IST)
    - Return `DailyAnalyticsResponse`
    - _Requirements: 5.3_

  - [x]* 4.7 Write property test for revenue formula (Property 2)
    - **Property 2: Daily revenue equals completed appointments times fee**
    - Use Hypothesis to generate appointment sets with varying statuses; assert `revenue == count(completed) * 500`
    - **Validates: Requirements 3.2, 5.3**

  - [x] 4.8 Implement `GET /api/analytics/monthly`
    - Add endpoint delegating to `AnalyticsService.get_monthly_revenue()`
    - Accept `year` and `month` query params
    - Return `MonthlyAnalyticsResponse`
    - _Requirements: 5.4_

  - [x]* 4.9 Write property test for no-show rate consistency (Property 3)
    - **Property 3: Monthly no-show rate is consistent with daily breakdown**
    - Use Hypothesis to generate random daily breakdown arrays; compute expected rate; assert it matches `no_show_rate`
    - **Validates: Requirements 3.2, 5.4**

  - [x] 4.10 Implement `GET /api/patients`
    - Add endpoint querying the `Patients` table
    - Accept `clinic_id` and optional `search` query param (case-insensitive filter on `full_name` or `phone`)
    - Return `List[PatientResponse]`
    - _Requirements: 5.5_

  - [x]* 4.11 Write property test for patient search subset (Property 4)
    - **Property 4: Patient search is a subset filter**
    - Use Hypothesis to generate patient lists and search strings; assert all returned patients contain the query in name or phone
    - **Validates: Requirements 4.4, 5.5**

  - [x] 4.12 Implement `GET /api/patients/{patient_id}/encounters`
    - Add endpoint querying `Encounters` for the given patient
    - Return at most 10 records sorted by `created_at` descending
    - Return `List[EncounterResponse]`
    - _Requirements: 5.6_

  - [x]* 4.13 Write property test for encounter ordering and bound (Property 5)
    - **Property 5: Encounter list is bounded and ordered**
    - Use Hypothesis to generate encounter lists of varying lengths; assert returned list has ≤ 10 items and is sorted descending by `created_at`
    - **Validates: Requirements 4.2, 5.6**

- [x] 5. Checkpoint — Verify all backend API endpoints
  - Ensure all tests pass, ask the user if questions arise.
  - Run `pytest backend/` and confirm all property tests pass
  - Manually verify `GET /api/appointments`, `PATCH /api/appointments/{id}/status`, `GET /api/analytics/daily`, `GET /api/analytics/monthly`, `GET /api/patients`, `GET /api/patients/{id}/encounters` return correct schemas

- [x] 6. Verify existing backend services (preserve, do not rewrite)
  - [x] 6.1 Verify WhatsApp bot booking flow
    - Confirm `process_whatsapp_logic` in `backend/app/main.py` handles: hi/hello/menu → interactive menu, Book Appointment → slots list, slot selection → booking confirmation with ID, concurrent booking protection via `with_for_update`
    - Confirm AI agent swarm routing: EMERGENCY/URGENT → alert, BOOKING → slots, CANCELLATION → acknowledgement
    - Add a smoke test asserting `POST /webhook` with a valid Meta payload returns `{"status": "success"}`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

  - [x]* 6.2 Write property test for slot booking exclusivity (Property 7)
    - **Property 7: Slot booking is exclusive under concurrency**
    - Use Hypothesis to generate slot configurations; attempt two concurrent `book_appointment_slot` calls for the same slot; assert exactly one succeeds and the other raises `SlotNotAvailableError` or `SlotAlreadyLockedError`
    - **Validates: Requirements 6.4**

  - [x] 6.3 Verify Reminder and Auto-Callback service
    - Confirm `start_scheduler()` / `stop_scheduler()` are called on FastAPI startup/shutdown events in `backend/app/main.py`
    - Confirm `check_and_send_reminders()` in `backend/app/reminders.py` queries booked appointments within 24 hours and sends WhatsApp reminders with CONFIRM/CANCEL/RESCHEDULE options
    - Confirm Twilio IVR call is skipped (with warning log) when TWILIO_* env vars are absent
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [x] 6.4 Verify Prescription PDF generation and delivery
    - Confirm `generate_prescription_pdf()` in `backend/app/pdf_service.py` produces non-empty PDF bytes containing clinic, patient, doctor, and medications fields
    - Confirm `send_prescription_pdf()` in `backend/app/main.py` uploads to Meta API, sends WhatsApp document, and falls back to text on failure
    - Confirm `POST /prescription/send` returns HTTP 200 on success and HTTP 502 on Meta API failure
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x]* 6.5 Write property test for filename sanitization (Property 6)
    - **Property 6: Prescription filename sanitization removes unsafe characters**
    - Use Hypothesis to generate arbitrary Unicode strings as patient names; assert the resulting filename matches `^[a-zA-Z0-9_]+\.pdf$`
    - **Validates: Requirements 8.6**

- [x] 7. Scaffold Next.js frontend application
  - [x] 7.1 Initialize Next.js 14 project with TypeScript and Tailwind CSS
    - Run `npx create-next-app@14 frontend --typescript --tailwind --app --no-src-dir --import-alias "@/*"`
    - Install dependencies: `shadcn-ui`, `recharts`, `@tanstack/react-query`, `lucide-react`
    - Configure `tailwind.config.ts` with ClinicOS color palette: primary `#0f8b8d`, accent `#2a6fdb`, sidebar `#0f172a`
    - _Requirements: 2.8_

  - [x] 7.2 Create TypeScript types and API client
    - Create `frontend/lib/types.ts` with all interfaces: `Appointment`, `AppointmentStatus`, `DailyAnalytics`, `MonthlyAnalytics`, `Patient`, `Encounter` as defined in the design
    - Create `frontend/lib/api.ts` with typed fetch wrappers: `getAppointments`, `patchAppointmentStatus`, `getDailyAnalytics`, `getMonthlyAnalytics`, `getPatients`, `getPatientEncounters`
    - Read base URL from `NEXT_PUBLIC_API_URL` environment variable
    - _Requirements: 2.5, 2.6, 3.6, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 7.3 Create root layout with Sidebar navigation
    - Create `frontend/app/layout.tsx` with dark sidebar (`#0f172a`) containing navigation links to `/dashboard`, `/owner`, `/emr`
    - Implement `frontend/components/Sidebar.tsx` with active link highlighted in teal (`#0f8b8d`)
    - Apply teal/blue color palette globally via Tailwind CSS
    - _Requirements: 2.8_

  - [x]* 7.4 Write unit tests for Sidebar component
    - Use Vitest + React Testing Library
    - Assert Sidebar renders all three navigation links: Dashboard, Owner, EMR
    - Assert active link receives teal highlight class
    - _Requirements: 2.8_

- [x] 8. Implement Admin Dashboard (`/dashboard`)
  - [x] 8.1 Create `AppointmentCard` component
    - Create `frontend/components/AppointmentCard.tsx`
    - Display: patient name, phone number, scheduled time in IST, color-coded status badge, booking ID
    - Include action buttons for status transitions: Confirmed → Completed, Confirmed → Missed
    - On button click, call `patchAppointmentStatus` and reflect updated status within 2 seconds of server response
    - Implement optimistic UI update with rollback on PATCH failure
    - _Requirements: 2.6, 2.7_

  - [x]* 8.2 Write unit tests for AppointmentCard
    - Assert card renders patient name, phone, status badge, and booking ID
    - Assert status-change button triggers `patchAppointmentStatus` call
    - Assert optimistic update rolls back on API error
    - _Requirements: 2.6, 2.7_

  - [x] 8.3 Implement Admin Dashboard page
    - Create `frontend/app/dashboard/page.tsx`
    - Fetch appointments via React Query with `refetchInterval: 30000` (30-second polling)
    - Render three columns: Confirmed (status=booked), Waiting (status=waiting), Completed (status=completed)
    - Render Upcoming section: appointments within next 24 hours, sorted by `scheduled_start` ascending
    - Render Missed section: appointments with status=missed for current calendar day in IST
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 9. Implement Owner Dashboard (`/owner`)
  - [x] 9.1 Create `KPICard` component
    - Create `frontend/components/KPICard.tsx`
    - Accept props: `label`, `value`, optional `delta` indicator
    - Apply card-based layout with teal/blue palette
    - _Requirements: 3.2_

  - [x] 9.2 Create `RevenueTrendChart` component
    - Create `frontend/components/RevenueTrendChart.tsx`
    - Use Recharts `LineChart` with teal stroke (`#0f8b8d`) and `ResponsiveContainer`
    - Accept `data: DailyAnalytics[]` prop; render one data point per day
    - Render without crashing when `data` is empty
    - _Requirements: 3.3_

  - [x]* 9.3 Write unit tests for KPICard and RevenueTrendChart
    - Assert `KPICard` renders label and value
    - Assert `RevenueTrendChart` renders without crashing given empty data array
    - _Requirements: 3.2, 3.3_

  - [x] 9.4 Implement Owner Dashboard page
    - Create `frontend/app/owner/page.tsx`
    - Render four KPI cards: Today's Revenue (completed × ₹500), Today's Completed, Monthly Revenue, No-Show Rate
    - Render patient volume cards: Total Patients, Returning Patients, Average Visits per Patient
    - Render `RevenueTrendChart` for current month's daily breakdown
    - Render Missed Appointment Analytics section (daily + monthly no-show counts)
    - Add `MonthPicker` component; on month change, re-fetch monthly analytics with selected `year` and `month`
    - Add "Refresh" button that manually triggers re-fetch of all metrics
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 10. Implement EMR View (`/emr`)
  - [x] 10.1 Create `PatientSearch` component
    - Create `frontend/components/PatientSearch.tsx`
    - Controlled input with debounced query (300ms) forwarded to `GET /api/patients?search=`
    - Display search results as a selectable patient list showing: full name, phone, registration date
    - _Requirements: 4.4, 4.6_

  - [x] 10.2 Create `EncounterCard` component
    - Create `frontend/components/EncounterCard.tsx`
    - Expandable card showing encounter `created_at` timestamp in collapsed state
    - On expand, display full JSON record contents: summary, source, and any clinical fields
    - _Requirements: 4.3_

  - [x] 10.3 Implement EMR View page
    - Create `frontend/app/emr/page.tsx`
    - Render `PatientSearch` at top; on patient selection, fetch encounters via `getPatientEncounters`
    - Render patient header: full name, phone, registration date
    - Render last 10 encounters sorted by `created_at` descending as `EncounterCard` list
    - Render "No clinical records found" message when encounter list is empty
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 11. Checkpoint — Verify frontend builds and renders
  - Ensure all tests pass, ask the user if questions arise.
  - Run `vitest --run` inside `frontend/` and confirm all component tests pass
  - Run `next build` inside `frontend/` and confirm zero TypeScript or build errors
  - Verify all three routes (`/dashboard`, `/owner`, `/emr`) render without runtime errors

- [x] 12. Write new documentation suite
  - [x] 12.1 Write `README.md` at repo root
    - Describe ClinicOS business value: 20–40% no-show reduction, WhatsApp-first approach, dual-channel (WhatsApp + IVR) booking model
    - Include system architecture overview: Patient → WhatsApp → Meta_API → Backend → AI_Agent_Swarm → Database → Reminder_Service → Patient
    - Replace existing 1000-line README with concise, business-focused content
    - _Requirements: 9.1, 9.4_

  - [x] 12.2 Write `docs/SETUP.md`
    - Step-by-step instructions for: obtaining Meta WhatsApp API keys (META_PHONE_ID, META_ACCESS_TOKEN, META_VERIFY_TOKEN), setting up Twilio IVR credentials, running database migrations
    - Include migration section referencing all eight ORM tables: Clinics, Doctors, Patients, Availability_Schedules, Appointments, Encounters, CallLogs, AuditLogs
    - _Requirements: 9.2, 9.5_

  - [x] 12.3 Write `docs/HOSTING.md`
    - Deployment instructions for: Backend on Railway or Render, Frontend on Vercel
    - Environment variable configuration for each platform
    - Estimated monthly hosting costs targeting Indian clinics
    - _Requirements: 9.3, 9.6_

- [x] 13. Final checkpoint — Full integration verification
  - Ensure all tests pass, ask the user if questions arise.
  - Run `pytest backend/` — all unit and property tests pass
  - Run `vitest --run` inside `frontend/` — all component tests pass
  - Run `docker compose up --build` and confirm backend starts, passes startup env validation, and serves `GET /api/appointments`
  - Confirm frontend `next build` succeeds with no errors

## Notes

- Tasks marked with `*` are optional test sub-tasks; all have been implemented and are passing
- All `from app.xxx import yyy` imports inside `/backend` remain unchanged — no Python import paths were modified
- Property tests use Hypothesis with minimum 100 iterations per property (`max_examples=100`)
- Frontend tests use `vitest --run` (single-pass) rather than watch mode
- 31 backend tests passing (including 7 Hypothesis property tests) and 45 frontend tests passing
- Existing backend files (`main.py`, `database.py`, `analytics_service.py`, `reminders.py`, `pdf_service.py`, `voice.py`, all `.agent.md` files) were moved, not rewritten
- The `AgentManager` path resolution (`os.path.join(os.path.dirname(__file__), "..", "agents")`) continues to work because `agents/` is a sibling of `app/` inside `/backend`
