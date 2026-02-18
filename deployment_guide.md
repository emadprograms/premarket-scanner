# Pre-Market Scanner: Deployment Guide

This guide outlines how to host the **Pre-Market Scanner** online using a modern, multi-environment architecture. We will use **Render** (or Railway) for the Python backend and **Vercel** for the Next.js frontend.

## 1. Prerequisites
Before starting, ensure you have:
1.  **GitHub Repository**: Push your latest code to GitHub.
2.  **Turso Account**: Your database is already cloud-native. You need your `TURSO_DB_URL` and `TURSO_AUTH_TOKEN`.
3.  **Capital.com & Gemini Keys**: You need your API keys ready.
4.  **Infisical (Optional)**: If you use Infisical for secrets, you'll need your `INFISICAL_TOKEN`. Otherwise, we'll use environment variables.

---

## 2. Deploying the Backend (Render)
We will host the FastAPI backend as a **Web Service** on Render.

1.  **Create a New Web Service**:
    - Go to [dashboard.render.com](https://dashboard.render.com).
    - Click **New +** -> **Web Service**.
    - Connect your GitHub repository.

2.  **Configure the Service**:
    - **Name**: `premarket-scanner-backend`
    - **Region**: Choose one close to you (e.g., Ohio, Frankfurt).
    - **Branch**: `main` (or your working branch).
    - **Root Directory**: `backend` (Important! This tells Render where your `requirements.txt` is).
    - **Runtime**: **Python 3**.
    - **Build Command**: `pip install -r requirements.txt` (This will use `backend/requirements.txt`).
    - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`

3.  **Environment Variables**:
    - Scroll down to "Environment Variables" and add:
        - `TURSO_DB_URL`: `libsql://...`
        - `TURSO_AUTH_TOKEN`: `...`
        - `GEMINI_API_KEY`: `...` (or use Infisical if configured)
        - `CAPITAL_API_KEY`: `...`
        - `CAPITAL_PASSWORD`: `...`
        - `CAPITAL_IDENTIFIER`: `...`
        - `PYTHON_VERSION`: `3.11.0` (Optional, ensures consistent runtime).

4.  **Deploy**: Click **Create Web Service**. Wait for the build to finish. Once live, copy the **Service URL** (e.g., `https://premarket-scanner-backend.onrender.com`).

---

## 3. Deploying the Frontend (Vercel)
We will host the Next.js frontend on Vercel, which is optimized for it.

1.  **Create a New Project**:
    - Go to [vercel.com](https://vercel.com).
    - Click **Add New** -> **Project**.
    - Import your GitHub repository.

2.  **Configure the Project**:
    - **Framework Preset**: Next.js (Should be auto-detected).
    - **Root Directory**: Click "Edit" and select `frontend`.

3.  **Environment Variables**:
    - Expand "Environment Variables" and add:
        - `NEXT_PUBLIC_API_URL`: Paste your **Render Backend URL** (e.g., `https://premarket-scanner-backend.onrender.com`).
        - **Note**: Ensure there is NO trailing slash (e.g., `...onrender.com`, NOT `...onrender.com/`).

4.  **Deploy**: Click **Deploy**. Vercel will build your frontend and assign a domain (e.g., `premarket-scanner.vercel.app`).

---

## 4. Final Connection Check
1.  Open your Vercel URL.
2.  The frontend should load.
3.  Check the "System Status" in the footer. If the backend is connected, you should see:
    - **BACKEND**: ONLINE
    - **ECONOMY_CARD**: CACHED/MISSING (not "Network Error").

## Troubleshooting
- **CORS Errors**: If the frontend cannot talk to the backend, you may need to update `backend/main.py` CORS settings to explicitly allow your Vercel domain instead of just `*` (though `*` usually works for testing).
- **500 Errors**: Check the Render logs tab. It will show Python tracebacks if secrets are missing or code is failing.
