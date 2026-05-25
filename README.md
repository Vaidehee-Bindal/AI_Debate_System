# AI Debate System

Advanced MVP for a source-backed multi-agent debate system. The app uses a FastAPI backend, LangGraph orchestration, Groq for LLM calls, Tavily for evidence search, SQLite persistence, and a React/Tailwind live debate UI.

## Features

- Live Pro vs Con debate stream with moderator turns
- LangGraph debate pipeline with moderator, agents, claim extraction, fact checking, scoring, and summarization
- Tavily-backed source lookup for factual claims
- Groq model wrapper with deterministic fallback when API keys are missing
- SQLite debate history, messages, claims, fact checks, scores, sources, and summaries
- No-emoji guardrail for AI-generated content

## Setup

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy ..\.env.example .env
uvicorn app.main:app --reload --port 8000
```

### Frontend

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5174
```

Open `http://127.0.0.1:5174`.

## Environment

```env
GROQ_API_KEY=
TAVILY_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
DATABASE_URL=sqlite:///./debates.db
```

If `GROQ_API_KEY` or `TAVILY_API_KEY` is absent, the backend uses local fallback responses so the app remains demoable.
