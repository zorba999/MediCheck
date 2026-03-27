# MediCheck — AI Symptom Checker
Powered by OpenGradient SDK · TEE-protected · PRIVATE settlement

## Files
- `backend.py` — Python Flask server (holds private key, calls OpenGradient SDK)
- `frontend.html` — Clean UI, calls backend via SSE streaming
- `medicheck_preview.html` — Standalone preview (no backend needed, simulated response)

## Setup & Run

### 1. Install dependencies
```bash
pip install opengradient flask flask-cors
```

### 2. Configure private key
Create a `.env` file in the root directory and add your OpenGradient private key:
```env
OG_PRIVATE_KEY=your_private_key_here
```

### 3. Run backend
```bash
python backend.py
```
Backend starts on `http://localhost:5000`

### 4. Open frontend
Open `frontend.html` directly in your browser (no server needed).

## API Endpoints
- `GET  /api/status` — health check
- `POST /api/assess` — symptom assessment (SSE streaming)

## Request format
```json
{
  "symptoms": "headache and fever for 3 days",
  "age": "31–45",
  "duration": "3–7 days",
  "history": "no known conditions"
}
```

## Tech Stack
- OpenGradient SDK (`og.LLM`)
- Model: `claude-sonnet-4-6` via TEE
- Settlement: `PRIVATE` (nothing on-chain)
- Payment: `$OPG` on Base Sepolia
- Backend: Python + Flask
- Frontend: Vanilla HTML/CSS/JS
