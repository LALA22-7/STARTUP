# Requirements Document

## Introduction

ClinicOS is a WhatsApp-first SaaS platform for Indian clinics. The goal of this feature is to standardize the existing codebase — migrating from a Streamlit prototype to a production-grade platform with a React/Next.js frontend, a clean project structure, and fully aligned UI/UX. The platform must preserve all existing backend logic (WhatsApp bot, AI agent swarm, reminders, PDF prescriptions, analytics) while delivering three distinct dashboard views: an Admin (Receptionist) Dashboard, an Owner (Money View) Dashboard, and a Lightweight EMR view. The primary business outcome is reducing patient no-shows by 20–40% for Indian clinics through automated WhatsApp reminders and IVR auto-callbacks.

---

## Glossary

- **ClinicOS**: The WhatsApp-first SaaS platform for Indian clinics being standardized in this spec.
- **Platform**: The combined frontend, backend, and documentation that constitute ClinicOS.
- **Frontend**: The React/Next.js web application serving the Admin Dashboard, Owner Dashboard, and EMR view.
- **Backend**: The FastAPI server handling WhatsApp webhooks, AI agent swarm, booking logic, reminders, and PDF generation.
- **WhatsApp_Bot**: The automated conversational flow powered by the Meta WhatsApp Business API and the AI agent swarm.
- **Admin_Dashboard**: The receptionist-facing Control Center view showing appointment queues and status tracking.
- **Owner_Dashboard**: The clinic owner-facing Money View showing revenue, patient volume, and no-show analytics.
- **EMR_View**: The Lightweight Electronic Medical Records view for patient encounter history and clinical notes.
- **Reminder_Service**: The APScheduler-based service that sends automated WhatsApp and IVR reminders before appointments.
- **Auto_Callback**: The IVR (Twilio) outbound call triggered for patients who do not respond to WhatsApp reminders.
- **Prescription_Service**: The service that generates PDF prescriptions via ReportLab and delivers them via WhatsApp.
- **Meta_API**: The Meta WhatsApp Business API used for sending and receiving WhatsApp messages.
- **IVR**: Interactive Voice Response system (Twilio) used for voice reminders and auto-callbacks.
- **AI_Agent_Swarm**: The six-agent system (Triage, Booking, Sentiment, Clinical, Webhook, Orchestrator) that processes incoming WhatsApp messages.
- **Slot**: A time block in the Availability_Schedules table representing a bookable appointment window.
- **Appointment**: A confirmed booking linking a Patient, a Slot, a Clinic, and optionally a Doctor.
- **Encounter**: A clinical record stored in the Encounters table capturing symptoms, diagnosis, and treatment notes.
- **No_Show**: An appointment with status "missed" — the patient did not attend.
- **IST**: Indian Standard Time (Asia/Kolkata, UTC+5:30), the timezone used for all display values.
- **Legacy_Artifacts**: Files from the prototype phase including the 1000-line README.md, MANUAL_SETUP_GUIDE.txt, CONSOLIDATION_SUMMARY.txt, PROJECT_STATUS.txt, and the Streamlit dashboard.

---

## Requirements

### Requirement 1: Project Structure Reorganization

**User Story:** As a developer onboarding to ClinicOS, I want a clean, predictable directory structure, so that I can navigate the codebase without reading legacy documentation.

#### Acceptance Criteria

1. THE Platform SHALL organize source code into three top-level directories: `/frontend` for the React/Next.js application, `/backend` for the FastAPI server and all Python services, and `/docs` for architecture diagrams and API contracts.
2. WHEN the project is reorganized, THE Platform SHALL preserve all existing backend logic including `app/main.py`, `app/database.py`, `app/analytics_service.py`, `app/reminders.py`, `app/pdf_service.py`, `app/calendar_sync_service.py`, `app/voice.py`, and the `agents/` folder by relocating them under `/backend`.
3. THE Platform SHALL remove Legacy_Artifacts (`MANUAL_SETUP_GUIDE.txt`, `CONSOLIDATION_SUMMARY.txt`, `PROJECT_STATUS.txt`, and `app/dashboard.py`) from the repository root and `/app` directory.
4. WHEN the project structure is reorganized, THE Platform SHALL update `docker-compose.yml`, `Dockerfile`, and all import paths so that the Backend continues to start and serve requests without errors.
5. THE Platform SHALL retain `docker-compose.yml` and `Dockerfile` at the repository root, updated to reflect the new `/backend` path.

---

### Requirement 2: Frontend — Admin Dashboard (Control Center)

**User Story:** As a clinic receptionist, I want a real-time appointment control center, so that I can track confirmed, waiting, and completed patients without switching between tools.

#### Acceptance Criteria

1. THE Frontend SHALL render an Admin_Dashboard page accessible at the `/dashboard` route.
2. WHEN the Admin_Dashboard loads, THE Frontend SHALL display three appointment queue columns: "Confirmed" (status = booked), "Waiting" (arrived but not yet seen), and "Completed" (status = completed).
3. WHEN the Admin_Dashboard loads, THE Frontend SHALL display an "Upcoming" section listing all appointments scheduled within the next 24 hours, sorted by `scheduled_start` ascending.
4. WHEN the Admin_Dashboard loads, THE Frontend SHALL display a "Missed" section listing all appointments with status = "missed" for the current calendar day in IST.
5. THE Frontend SHALL fetch appointment data from the Backend REST API and refresh the display at most every 30 seconds without requiring a full page reload.
6. WHEN a receptionist updates an appointment status (Confirmed → Completed or Confirmed → Missed), THE Frontend SHALL send a PATCH request to the Backend and reflect the updated status within 2 seconds of the server response.
7. THE Admin_Dashboard SHALL display each appointment card with: patient name, phone number, scheduled time in IST, appointment status badge, and booking ID.
8. THE Frontend SHALL match the visual style defined in the ClinicOS PDF specification: teal/blue color palette (`#0f8b8d` primary, `#2a6fdb` accent), card-based layout, and dark sidebar navigation.

---

### Requirement 3: Frontend — Owner Dashboard (Money View)

**User Story:** As a clinic owner, I want a financial and operational overview, so that I can track daily and monthly revenue and understand no-show impact on income.

#### Acceptance Criteria

1. THE Frontend SHALL render an Owner_Dashboard page accessible at the `/owner` route.
2. WHEN the Owner_Dashboard loads, THE Frontend SHALL display four KPI cards: "Today's Revenue" (completed appointments × ₹500), "Today's Completed Appointments", "Monthly Revenue", and "No-Show Rate" (missed / total × 100%).
3. WHEN the Owner_Dashboard loads, THE Frontend SHALL display a daily revenue trend line chart for the current calendar month, with one data point per day.
4. WHEN the Owner_Dashboard loads, THE Frontend SHALL display patient volume metrics: "Total Patients", "Returning Patients", and "Average Visits per Patient".
5. THE Owner_Dashboard SHALL display a "Missed Appointment Analytics" section showing the count of No_Shows for the current day and current month.
6. THE Frontend SHALL fetch all Owner_Dashboard metrics from the Backend REST API and support manual refresh via a "Refresh" button.
7. WHERE the clinic owner selects a past month from a month picker, THE Frontend SHALL display revenue and no-show data for that selected month.

---

### Requirement 4: Frontend — Lightweight EMR View

**User Story:** As a doctor or receptionist, I want to view a patient's clinical history, so that I can provide informed care without paper records.

#### Acceptance Criteria

1. THE Frontend SHALL render an EMR_View page accessible at the `/emr` route.
2. WHEN a patient is selected from the patient search, THE EMR_View SHALL display the patient's last 10 Encounters sorted by `created_at` descending.
3. WHEN an Encounter is expanded, THE EMR_View SHALL display the full JSON record contents including summary, source, and any clinical fields present.
4. THE EMR_View SHALL provide a patient search input that filters patients by full name or phone number.
5. WHEN no Encounters exist for a selected patient, THE EMR_View SHALL display a "No clinical records found" message.
6. THE EMR_View SHALL display each patient record with: full name, phone number, and registration date.

---

### Requirement 5: Backend REST API for Dashboard Data

**User Story:** As the Frontend, I need structured REST API endpoints, so that I can fetch appointment, revenue, and patient data without direct database access.

#### Acceptance Criteria

1. THE Backend SHALL expose a `GET /api/appointments` endpoint that returns all appointments for a given `clinic_id`, optionally filtered by `status`, `date_from`, and `date_to` query parameters.
2. THE Backend SHALL expose a `PATCH /api/appointments/{appointment_id}/status` endpoint that accepts a `status` field and updates the appointment status, returning the updated appointment object.
3. THE Backend SHALL expose a `GET /api/analytics/daily` endpoint that returns daily revenue, completed count, missed count, and total count for a given `date` query parameter (defaults to today in IST).
4. THE Backend SHALL expose a `GET /api/analytics/monthly` endpoint that returns monthly revenue, no-show rate, and daily breakdown for a given `year` and `month` query parameter.
5. THE Backend SHALL expose a `GET /api/patients` endpoint that returns all patients for a given `clinic_id`, supporting `search` query parameter for name or phone filtering.
6. THE Backend SHALL expose a `GET /api/patients/{patient_id}/encounters` endpoint that returns the last 10 Encounters for the specified patient, sorted by `created_at` descending.
7. WHEN an invalid `appointment_id` is provided to the status update endpoint, THE Backend SHALL return HTTP 404 with a descriptive error message.
8. WHEN an invalid `status` value is provided (not one of: booked, completed, missed, waiting), THE Backend SHALL return HTTP 422 with a descriptive validation error.
9. THE Backend SHALL include CORS headers permitting requests from the Frontend origin so that the browser does not block API calls.

---

### Requirement 6: WhatsApp Bot Booking Flow

**User Story:** As a patient, I want to book a clinic appointment entirely through WhatsApp, so that I don't need to call or visit the clinic.

#### Acceptance Criteria

1. WHEN a patient sends "hi", "hello", or "menu" to the clinic's WhatsApp number, THE WhatsApp_Bot SHALL respond with an interactive button menu offering "Book Appointment" and "Ask a Question".
2. WHEN a patient selects "Book Appointment", THE WhatsApp_Bot SHALL retrieve up to 3 open Slots from the database and present them as a WhatsApp list message.
3. WHEN a patient selects a Slot from the list, THE WhatsApp_Bot SHALL create a Patient record (if one does not already exist for that phone number) and an Appointment record with status = "booked", then send a confirmation message containing the booking ID and appointment time in IST.
4. IF the selected Slot is no longer available at the time of booking (concurrent booking), THEN THE WhatsApp_Bot SHALL notify the patient that the slot was taken and re-present available slots.
5. WHEN a patient sends a message containing "book appointment" (case-insensitive), THE WhatsApp_Bot SHALL present available slots as defined in criterion 2.
6. WHEN the AI_Agent_Swarm classifies an incoming message as "EMERGENCY" or "URGENT", THE WhatsApp_Bot SHALL send an urgent alert message with the clinic's emergency contact number before any other response.
7. WHEN the AI_Agent_Swarm classifies an incoming message as "BOOKING", THE WhatsApp_Bot SHALL present available slots as defined in criterion 2.
8. WHEN the AI_Agent_Swarm classifies an incoming message as "CANCELLATION", THE WhatsApp_Bot SHALL acknowledge the cancellation request and inform the patient that a receptionist will confirm.

---

### Requirement 7: Automated Reminder and Auto-Callback Service

**User Story:** As a clinic owner, I want automated reminders sent to patients before their appointments, so that no-shows are reduced by 20–40%.

#### Acceptance Criteria

1. THE Reminder_Service SHALL run on a schedule and check for Appointments with status = "booked" that are scheduled within the next 24 hours.
2. WHEN an upcoming Appointment is found and the Patient has a phone number, THE Reminder_Service SHALL send a WhatsApp reminder message via the Meta_API containing the appointment time in IST and options to CONFIRM, CANCEL, or RESCHEDULE.
3. WHEN a WhatsApp reminder is sent, THE Reminder_Service SHALL also trigger an IVR voice call via the Auto_Callback service if Twilio credentials are configured.
4. WHEN a patient does not respond to a WhatsApp reminder within the reminder window, THE Reminder_Service SHALL trigger an Auto_Callback IVR call to the patient's phone number.
5. WHEN an Auto_Callback IVR call is initiated, THE Auto_Callback SHALL play a message identifying the clinic, stating the appointment time, and offering keypad options: press 1 to confirm, press 2 to cancel, press 3 to speak with a receptionist.
6. IF Twilio credentials (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER) are not configured, THEN THE Reminder_Service SHALL skip IVR calls and log a warning without raising an exception.
7. WHEN an Appointment has status = "missed", THE Auto_Callback SHALL initiate a no-show recovery call offering the patient an option to reschedule.

---

### Requirement 8: Prescription PDF Generation and WhatsApp Delivery

**User Story:** As a doctor, I want to generate a prescription PDF and send it to the patient via WhatsApp, so that patients receive their prescriptions instantly without paper.

#### Acceptance Criteria

1. THE Prescription_Service SHALL generate a PDF prescription containing: clinic name, clinic address, clinic phone, patient name, doctor name, prescription date in IST, a medications table (medicine name, dosage, frequency, duration), and special instructions.
2. WHEN a prescription PDF is generated, THE Prescription_Service SHALL upload the PDF to the Meta_API media endpoint and obtain a media ID.
3. WHEN a media ID is obtained, THE Prescription_Service SHALL send the PDF as a WhatsApp document message to the patient's phone number with a caption identifying the patient and doctor.
4. THE Backend SHALL expose a `POST /prescription/send` endpoint accepting: `to_phone`, `patient_name`, `doctor_name`, `medications` (list of objects), and `instructions`; and SHALL return HTTP 200 on successful delivery.
5. IF the Meta_API media upload fails, THEN THE Prescription_Service SHALL send a fallback WhatsApp text message informing the patient to contact the clinic, and SHALL return HTTP 502 from the endpoint.
6. THE Prescription_Service SHALL sanitize the patient name when constructing the PDF filename, replacing spaces with underscores and removing non-alphanumeric characters.

---

### Requirement 9: New Documentation Suite

**User Story:** As a developer or clinic operator setting up ClinicOS, I want clear, business-focused documentation, so that I can deploy and configure the platform without reading legacy setup guides.

#### Acceptance Criteria

1. THE Platform SHALL include a `README.md` at the repository root that describes ClinicOS's business value, specifically the 20–40% no-show reduction outcome, the WhatsApp-first approach, and the dual-channel (WhatsApp + IVR) booking model.
2. THE Platform SHALL include a `SETUP.md` file in the `/docs` directory with step-by-step instructions for: obtaining and configuring Meta WhatsApp API keys (META_PHONE_ID, META_ACCESS_TOKEN, META_VERIFY_TOKEN), setting up Twilio IVR credentials (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER), and running database migrations for the Lightweight EMR schema.
3. THE Platform SHALL include a `HOSTING.md` file in the `/docs` directory with deployment instructions for: hosting the Backend on Railway or Render, hosting the Frontend on Vercel, and configuring environment variables for each platform.
4. THE README.md SHALL include a system architecture overview describing the flow: Patient → WhatsApp → Meta_API → Backend → AI_Agent_Swarm → Database → Reminder_Service → Patient.
5. THE SETUP.md SHALL include a database migration section referencing all six ORM tables: Clinics, Doctors, Patients, Availability_Schedules, Appointments, Encounters, CallLogs, and AuditLogs.
6. THE HOSTING.md SHALL describe an affordable SaaS deployment model targeting Indian clinics, with estimated monthly hosting costs for Railway/Render (Backend) and Vercel (Frontend).

---

### Requirement 10: Configuration and Environment Standardization

**User Story:** As a developer deploying ClinicOS, I want all configuration managed through environment variables with clear documentation, so that I can deploy to any environment without modifying source code.

#### Acceptance Criteria

1. THE Platform SHALL read all secrets and configuration values exclusively from environment variables: DATABASE_URL, META_PHONE_ID, META_ACCESS_TOKEN, META_VERIFY_TOKEN, GROQ_API_KEY, GEMINI_API_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, and GOOGLE_CREDENTIALS_FILE.
2. THE Backend SHALL load environment variables using `python-dotenv` at startup before any database or API client is initialized.
3. IF a required environment variable (DATABASE_URL, META_PHONE_ID, META_ACCESS_TOKEN) is missing at startup, THEN THE Backend SHALL log a descriptive error message identifying the missing variable and exit with a non-zero status code.
4. THE Platform SHALL provide a `.env.example` file at the repository root listing all required and optional environment variables with placeholder values and inline comments describing each variable's purpose.
5. THE Platform SHALL ensure the `.env` file is listed in `.gitignore` so that secrets are never committed to version control.
