import json
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import db
from .config import get_settings
from .debate.graph import DebateGraphRunner
from .schemas import DebateCreate

app = FastAPI(title="AI Debate System")
settings = get_settings()

logging.basicConfig(level=logging.INFO)

allow_origins = [
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    db.init_db()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/debates")
def create_debate(payload: DebateCreate) -> dict:
    db.init_db()
    return db.create_debate(payload.topic.strip(), payload.rounds, payload.stance_style.strip() or "balanced")


@app.get("/api/debates")
def list_debates() -> list[dict]:
    db.init_db()
    return db.list_debates()


@app.get("/api/debates/{debate_id}")
def get_debate(debate_id: str) -> dict:
    try:
        return db.get_debate(debate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Debate not found") from exc


@app.get("/api/debates/{debate_id}/sources")
def get_sources(debate_id: str) -> list[dict]:
    return db.get_sources(debate_id)


@app.get("/api/debates/{debate_id}/stream")
async def stream_debate(debate_id: str) -> StreamingResponse:
    try:
        debate = db.get_debate(debate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Debate not found") from exc

    async def event_source():
        runner = DebateGraphRunner()
        async for item in runner.stream(debate):
            yield f"event: {item['event']}\n"
            yield f"data: {json.dumps(item['data'])}\n\n"
    # Add SSE headers to reduce proxy buffering issues
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(event_source(), media_type="text/event-stream", headers=headers)


@app.delete("/api/debates/{debate_id}")
def delete_debate(debate_id: str) -> dict:
    try:
        db.delete_debate(debate_id)
        return {"deleted": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/api/debates")
def delete_all_debates() -> dict:
    try:
        db.clear_all()
        return {"cleared": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.on_event("startup")
def _log_cors() -> None:
    logging.info(f"CORS allowed origins: {allow_origins}")
