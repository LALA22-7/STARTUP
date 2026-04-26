# ClinicOS Setup Guide

This guide walks through everything needed to run ClinicOS locally or prepare it for deployment: obtaining API credentials, configuring environment variables, and initializing the database.

---

## Prerequisites

| Requirement | Minimum Version |
|-------------|----------------|
| Python | 3.10 |
| PostgreSQL | 14 |
| Node.js | 18 |
| npm | 9 |

---

## 1. Clone and Configure Environment

```bash
git clone <repository-url>
cd clinicos
cp .env.example .env
```

Open `.env` and fill in the values described in the sections below. The backend will refuse to start if `DATABASE_URL`, `META_PHONE_ID`, or `META_ACCESS_TOKEN` are missing.

---

## 2. Database Setup

### 2.1 Create the PostgreSQL database

```bash
psql -U postgres -c "CREATE DATABASE clinicos;"
```

Set `DATABASE_URL` in `.env`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@localhost:5432/clinicos
```

### 2.2 Run database migrations

ClinicOS uses SQLAlchemy's `create_all` to create tables on first run. The `init_db.py` script also seeds a default clinic record so the app has something to work with immediately.

```bash
cd backend
pip install -r requirements.txt
python app/init_db.py
```

This creates all eight ORM tables:

| Table | Description |
|-------|-------------|
| `Clinics` | Clinic profiles (name, timezone) |
| `Doctors` | Doctor records linked to a clinic |
| `Patients` | Patient records (name, email, phone) |
| `Availability_Schedules` | Bookable time slots per clinic |
| `Appointments` | Confirmed bookings linking patient, doctor, and slot |
| `Encounters` | Clinical records stored as JSONB (symptoms, diagnosis, notes) |
| `CallLogs` | Log of WhatsApp and voice call events |
| `AuditLogs` | Audit trail for patient record access |

To inspect the schema after creation:

```bash
psql -U postgres -d clinicos -c "\dt"
```

---

## 3. Meta WhatsApp Business API

ClinicOS uses the Meta WhatsApp Business API to send and receive messages. You need a Meta Developer account and a WhatsApp Business number.

### 3.1 Create a Meta Developer App

1. Go to [developers.facebook.com](https://developers.facebook.com) and log in.
2. Click **My Apps → Create App**.
3. Choose **Business** as the app type.
4. Under **Add Products**, find **WhatsApp** and click **Set Up**.

### 3.2 Get your Phone Number ID (`META_PHONE_ID`)

1. In the left sidebar, go to **WhatsApp → API Setup**.
2. Under **From**, you will see a test phone number with a numeric **Phone Number ID** below it.
3. Copy that ID — this is your `META_PHONE_ID`.

For production, add your own WhatsApp Business number under **Phone Numbers** and use its ID instead.

### 3.3 Get your Access Token (`META_ACCESS_TOKEN`)

1. On the same **API Setup** page, click **Generate Access Token** (or use a System User token for production).
2. Copy the token — this is your `META_ACCESS_TOKEN`.

For production deployments, create a **System User** in Meta Business Manager and generate a permanent token with `whatsapp_business_messaging` permission.

### 3.4 Set your Verify Token (`META_VERIFY_TOKEN`)

This is a secret string you choose. It must match what you enter in the Meta webhook configuration.

```env
META_VERIFY_TOKEN=my_secret_verify_token_123
```

### 3.5 Configure the Webhook in Meta

1. In **WhatsApp → Configuration**, click **Edit** next to Webhook.
2. Set **Callback URL** to your public backend URL: `https://your-domain.com/webhook`
3. Set **Verify Token** to the same value as `META_VERIFY_TOKEN` in your `.env`.
4. Subscribe to the **messages** webhook field.

The backend must be publicly accessible (use [ngrok](https://ngrok.com) for local testing):

```bash
ngrok http 8000
# Use the https URL as your Callback URL
```

### 3.6 Set the variables in `.env`

```env
META_PHONE_ID=123456789012345
META_ACCESS_TOKEN=EAABsbCS...
META_VERIFY_TOKEN=my_secret_verify_token_123
```

---

## 4. AI / LLM Keys

The AI agent swarm (Triage, Booking, Sentiment, Clinical, Webhook, Orchestrator) uses Groq for fast inference.

### 4.1 Groq API Key

1. Sign up at [console.groq.com](https://console.groq.com).
2. Go to **API Keys → Create API Key**.
3. Copy the key.

```env
GROQ_API_KEY=gsk_...
```

### 4.2 Gemini API Key

1. Go to [aistudio.google.com](https://aistudio.google.com).
2. Click **Get API Key → Create API Key**.
3. Copy the key.

```env
GEMINI_API_KEY=AIza...
```

---

## 5. Twilio IVR / Auto-Callback (Optional)

Twilio is used for outbound voice reminders and no-show recovery calls. If these variables are not set, IVR calls are skipped and a warning is logged — WhatsApp reminders still work.

### 5.1 Create a Twilio account

1. Sign up at [twilio.com](https://www.twilio.com).
2. Verify your phone number.
3. From the **Console Dashboard**, copy your **Account SID** and **Auth Token**.

### 5.2 Get a Twilio phone number

1. In the Twilio Console, go to **Phone Numbers → Manage → Buy a Number**.
2. Search for a number with Voice capability.
3. Purchase the number (trial accounts get a free number).

### 5.3 Configure the IVR webhook

In the Twilio Console, set the **A Call Comes In** webhook for your number to:

```
https://your-domain.com/voice
```

### 5.4 Set the variables in `.env`

```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+12025551234
```

---

## 6. Google Calendar Integration (Optional)

If not configured, calendar sync is silently disabled.

### 6.1 Create a Google Cloud service account

1. Go to [console.cloud.google.com](https://console.cloud.google.com).
2. Create a project (or select an existing one).
3. Enable the **Google Calendar API** under **APIs & Services → Library**.
4. Go to **IAM & Admin → Service Accounts → Create Service Account**.
5. Grant the role **Editor** (or a custom role with calendar write access).
6. Under **Keys**, click **Add Key → Create New Key → JSON**.
7. Download the JSON file and save it as `google_credentials.json` in the repo root.

### 6.2 Share your calendar with the service account

1. Open Google Calendar.
2. Find the calendar you want to sync, click the three-dot menu → **Settings and sharing**.
3. Under **Share with specific people**, add the service account email (found in the JSON file as `client_email`).
4. Grant **Make changes to events** permission.

### 6.3 Set the variable in `.env`

```env
GOOGLE_CREDENTIALS_FILE=/backend/google_credentials.json
```

---

## 7. Frontend Configuration

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

For production, replace with your deployed backend URL (e.g., `https://clinicos-api.up.railway.app`).

---

## 8. Start the Application

### Backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

The scheduler starts automatically. API docs are at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` in your browser.

### Docker Compose (recommended)

```bash
docker compose up --build
```

---

## 9. Verify the Setup

```bash
# Webhook verification (should return 403 — missing token)
curl http://localhost:8000/webhook

# Appointments endpoint (should return empty array or data)
curl "http://localhost:8000/api/appointments?clinic_id=1"

# Daily analytics
curl "http://localhost:8000/api/analytics/daily"
```

Run the test suite:

```bash
# Backend property and unit tests
cd backend
pytest tests/ -v

# Frontend component tests
cd frontend
npm run test -- --run
```
