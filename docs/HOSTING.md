# ClinicOS Hosting Guide

This guide covers deploying ClinicOS to production: the backend on Railway or Render, the frontend on Vercel, and a managed PostgreSQL database. All options are affordable for Indian clinics and require no server administration.

---

## Architecture Overview

```
Internet
  │
  ├─ WhatsApp patients ──► Meta API ──► Backend (Railway / Render)
  │                                          │
  │                                     PostgreSQL (Railway / Render / Supabase)
  │
  └─ Clinic staff ──► Browser ──► Frontend (Vercel) ──► Backend API
```

The backend and frontend are deployed independently. The frontend calls the backend over HTTPS using the `NEXT_PUBLIC_API_URL` environment variable.

---

## Estimated Monthly Costs (Indian Clinics)

| Service | Plan | Estimated Cost (INR/month) |
|---------|------|---------------------------|
| Railway (backend) | Hobby — $5/month | ~₹420 |
| Railway (PostgreSQL) | Hobby — $5/month | ~₹420 |
| Vercel (frontend) | Hobby — Free | ₹0 |
| Meta WhatsApp API | Per-conversation pricing | ₹0–₹500 (low volume) |
| Twilio IVR (optional) | ~$0.014/min | ₹50–₹300 (low volume) |
| **Total** | | **~₹840–₹1,640/month** |

Render's free tier can reduce backend costs to ₹0 with the trade-off of cold starts (30–60 second spin-up after inactivity). For a clinic with regular daytime traffic, Railway's Hobby plan is recommended.

---

## Option A: Deploy Backend on Railway

Railway is the recommended option for ClinicOS. It supports Dockerfile deployments, managed PostgreSQL, and persistent processes (no cold starts on paid plans).

### 1. Create a Railway account

Sign up at [railway.app](https://railway.app). Connect your GitHub account.

### 2. Create a new project

1. Click **New Project → Deploy from GitHub repo**.
2. Select your ClinicOS repository.
3. Railway will detect the `Dockerfile` at the repo root.

### 3. Add a PostgreSQL database

1. In your Railway project, click **New → Database → Add PostgreSQL**.
2. Railway provisions a database and injects `DATABASE_URL` automatically into your service.

### 4. Set environment variables

In your Railway service, go to **Variables** and add:

```
META_PHONE_ID=<your value>
META_ACCESS_TOKEN=<your value>
META_VERIFY_TOKEN=<your value>
GROQ_API_KEY=<your value>
GEMINI_API_KEY=<your value>
TWILIO_ACCOUNT_SID=<your value>          # optional
TWILIO_AUTH_TOKEN=<your value>           # optional
TWILIO_PHONE_NUMBER=<your value>         # optional
GOOGLE_CREDENTIALS_FILE=/backend/google_credentials.json  # optional
NEXT_PUBLIC_API_URL=https://<your-frontend>.vercel.app
```

`DATABASE_URL` is injected automatically by Railway when you add the PostgreSQL plugin.

### 5. Configure the start command

Railway reads the `Dockerfile` at the repo root. The default command (`uvicorn app.main:app --host 0.0.0.0 --port 8000`) is already set in the Dockerfile. No changes needed.

### 6. Get your public URL

After deployment, Railway assigns a URL like `https://clinicos-production.up.railway.app`. Use this as:
- The Meta webhook Callback URL: `https://clinicos-production.up.railway.app/webhook`
- The `NEXT_PUBLIC_API_URL` value in Vercel

### 7. Initialize the database

Run the init script once via Railway's shell:

```bash
python app/init_db.py
```

Or connect directly with psql using the connection string from Railway's PostgreSQL plugin.

---

## Option B: Deploy Backend on Render

Render offers a free tier suitable for low-traffic clinics during initial rollout.

### 1. Create a Render account

Sign up at [render.com](https://render.com). Connect your GitHub account.

### 2. Create a Web Service

1. Click **New → Web Service**.
2. Connect your GitHub repository.
3. Set **Root Directory** to `backend`.
4. Set **Runtime** to **Docker**.
5. Set **Start Command** to `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

### 3. Add a PostgreSQL database

1. Click **New → PostgreSQL**.
2. Choose the **Free** plan (or **Starter** at ~$7/month for persistent storage).
3. Copy the **Internal Database URL** and set it as `DATABASE_URL` in your web service's environment variables.

### 4. Set environment variables

In your Render web service, go to **Environment** and add the same variables listed in the Railway section above.

### 5. Free tier limitations

The Render free tier spins down after 15 minutes of inactivity. The first request after a cold start takes 30–60 seconds. For a production clinic, upgrade to the **Starter** plan (~$7/month, ~₹580) to avoid cold starts.

---

## Deploy Frontend on Vercel

### 1. Create a Vercel account

Sign up at [vercel.com](https://vercel.com). Connect your GitHub account.

### 2. Import the project

1. Click **Add New → Project**.
2. Select your ClinicOS repository.
3. Set **Root Directory** to `frontend`.
4. Vercel auto-detects Next.js — no framework configuration needed.

### 3. Set environment variables

In Vercel's project settings, go to **Settings → Environment Variables** and add:

```
NEXT_PUBLIC_API_URL=https://<your-backend-url>
```

Replace `<your-backend-url>` with your Railway or Render backend URL.

### 4. Deploy

Click **Deploy**. Vercel builds the Next.js app and assigns a URL like `https://clinicos.vercel.app`.

For a custom domain (e.g., `dashboard.yourclinic.in`), go to **Settings → Domains** and add your domain. Vercel provisions an SSL certificate automatically.

---

## Connecting Frontend and Backend

After both are deployed:

1. In Vercel, set `NEXT_PUBLIC_API_URL` to your backend URL (Railway or Render).
2. In your backend environment variables, set `NEXT_PUBLIC_API_URL` to your Vercel frontend URL — this is used by the CORS middleware to allow browser requests.
3. Redeploy both services after updating environment variables.

Verify the connection:

```bash
curl https://<your-backend-url>/api/appointments?clinic_id=1
```

---

## Meta Webhook Configuration for Production

Once the backend is deployed, update the Meta webhook:

1. Go to [developers.facebook.com](https://developers.facebook.com) → your app → **WhatsApp → Configuration**.
2. Set **Callback URL** to `https://<your-backend-url>/webhook`.
3. Set **Verify Token** to the same value as `META_VERIFY_TOKEN` in your backend environment.
4. Click **Verify and Save**.
5. Subscribe to the **messages** webhook field.

---

## Google Credentials in Production

If using Google Calendar sync, the `google_credentials.json` file must be available inside the container. The recommended approach is to encode it as a base64 environment variable and decode it at startup.

Alternatively, mount it as a secret file in Railway or Render:

- **Railway**: Use the **Files** tab to upload `google_credentials.json` and set `GOOGLE_CREDENTIALS_FILE` to its path.
- **Render**: Use **Secret Files** under your service's environment settings.

---

## Monitoring and Logs

- **Railway**: Logs are available in the **Deployments** tab. Set up alerts under **Settings → Notifications**.
- **Render**: Logs are in the **Logs** tab of your web service.
- **Vercel**: Build and runtime logs are in the **Deployments** section.

The backend logs startup validation errors, missing environment variables, and scheduler activity. Check logs if reminders are not sending or the webhook is not responding.

---

## Updating the Application

Push changes to your GitHub repository. Both Railway and Render auto-deploy on push to the main branch. Vercel also deploys automatically.

To run database migrations after a schema change:

```bash
# Via Railway shell
python app/init_db.py

# Or connect directly with psql
psql $DATABASE_URL -c "\dt"
```
