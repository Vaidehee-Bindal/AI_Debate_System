import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import get_settings


def _db_path() -> Path:
    url = get_settings().database_url
    if url.startswith("sqlite:///"):
        return Path(url.replace("sqlite:///", "", 1))
    return Path("debates.db")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS debates (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL DEFAULT '',
                topic TEXT NOT NULL,
                rounds INTEGER NOT NULL,
                stance_style TEXT NOT NULL,
                status TEXT NOT NULL,
                current_round INTEGER NOT NULL DEFAULT 0,
                pro_score INTEGER NOT NULL DEFAULT 0,
                con_score INTEGER NOT NULL DEFAULT 0,
                winner TEXT,
                final_summary TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                debate_id TEXT NOT NULL,
                round INTEGER NOT NULL,
                speaker TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS claims (
                id TEXT PRIMARY KEY,
                debate_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                speaker TEXT NOT NULL,
                claim TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS fact_checks (
                id TEXT PRIMARY KEY,
                debate_id TEXT NOT NULL,
                claim_id TEXT NOT NULL,
                verdict TEXT NOT NULL,
                confidence INTEGER NOT NULL,
                rationale TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY,
                debate_id TEXT NOT NULL,
                fact_check_id TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                snippet TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scores (
                id TEXT PRIMARY KEY,
                debate_id TEXT NOT NULL,
                round INTEGER NOT NULL,
                pro_score INTEGER NOT NULL,
                con_score INTEGER NOT NULL,
                breakdown_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        debate_columns = {row[1] for row in conn.execute("PRAGMA table_info(debates)")}
        if "device_id" not in debate_columns:
            conn.execute("ALTER TABLE debates ADD COLUMN device_id TEXT NOT NULL DEFAULT ''")


def create_debate(topic: str, rounds: int, stance_style: str, device_id: str) -> dict[str, Any]:
    debate_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO debates (id, device_id, topic, rounds, stance_style, status)
            VALUES (?, ?, ?, ?, ?, 'created')
            """,
            (debate_id, device_id, topic, rounds, stance_style),
        )
    return get_debate(debate_id, device_id)


def add_message(debate_id: str, round_number: int, speaker: str, content: str) -> dict[str, Any]:
    item_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            "INSERT INTO messages (id, debate_id, round, speaker, content) VALUES (?, ?, ?, ?, ?)",
            (item_id, debate_id, round_number, speaker, content),
        )
    return {"id": item_id, "debate_id": debate_id, "round": round_number, "speaker": speaker, "content": content}


def add_claim(debate_id: str, message_id: str, speaker: str, claim: str) -> dict[str, Any]:
    item_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            "INSERT INTO claims (id, debate_id, message_id, speaker, claim) VALUES (?, ?, ?, ?, ?)",
            (item_id, debate_id, message_id, speaker, claim),
        )
    return {"id": item_id, "debate_id": debate_id, "message_id": message_id, "speaker": speaker, "claim": claim}


def add_fact_check(
    debate_id: str,
    claim_id: str,
    verdict: str,
    confidence: int,
    rationale: str,
    sources: list[dict[str, str]],
) -> dict[str, Any]:
    item_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO fact_checks (id, debate_id, claim_id, verdict, confidence, rationale)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (item_id, debate_id, claim_id, verdict, confidence, rationale),
        )
        for source in sources:
            conn.execute(
                """
                INSERT INTO sources (id, debate_id, fact_check_id, title, url, snippet)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    debate_id,
                    item_id,
                    source.get("title", "Source"),
                    source.get("url", ""),
                    source.get("snippet", ""),
                ),
            )
    return {
        "id": item_id,
        "debate_id": debate_id,
        "claim_id": claim_id,
        "verdict": verdict,
        "confidence": confidence,
        "rationale": rationale,
        "sources": sources,
    }


def add_score(debate_id: str, round_number: int, pro_score: int, con_score: int, breakdown: dict[str, Any]) -> dict[str, Any]:
    item_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO scores (id, debate_id, round, pro_score, con_score, breakdown_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (item_id, debate_id, round_number, pro_score, con_score, json.dumps(breakdown)),
        )
        conn.execute(
            """
            UPDATE debates
            SET current_round = ?, pro_score = ?, con_score = ?, status = 'running', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (round_number, pro_score, con_score, debate_id),
        )
    return {"id": item_id, "round": round_number, "pro_score": pro_score, "con_score": con_score, "breakdown": breakdown}


def finish_debate(debate_id: str, winner: str, final_summary: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE debates
            SET status = 'complete', winner = ?, final_summary = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (winner, final_summary, debate_id),
        )


def mark_error(debate_id: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE debates SET status = 'error', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (debate_id,))


def list_debates(device_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM debates WHERE device_id = ? ORDER BY created_at DESC", (device_id,)).fetchall()
    return [dict(row) for row in rows]


def get_debate(debate_id: str, device_id: str) -> dict[str, Any]:
    with connect() as conn:
        debate = conn.execute("SELECT * FROM debates WHERE id = ? AND device_id = ?", (debate_id, device_id)).fetchone()
        if debate is None:
            raise KeyError(debate_id)
        detail = dict(debate)
        detail["messages"] = [dict(row) for row in conn.execute("SELECT * FROM messages WHERE debate_id = ? ORDER BY created_at, rowid", (debate_id,))]
        detail["claims"] = [dict(row) for row in conn.execute("SELECT * FROM claims WHERE debate_id = ? ORDER BY created_at, rowid", (debate_id,))]
        fact_checks = [dict(row) for row in conn.execute("SELECT * FROM fact_checks WHERE debate_id = ? ORDER BY created_at, rowid", (debate_id,))]
        source_rows = [dict(row) for row in conn.execute("SELECT * FROM sources WHERE debate_id = ? ORDER BY rowid", (debate_id,))]
        sources_by_fact_check_id: dict[str, list[dict[str, Any]]] = {}
        for source in source_rows:
            fact_check_id = str(source.get("fact_check_id", ""))
            sources_by_fact_check_id.setdefault(fact_check_id, []).append(source)
        for fact_check in fact_checks:
            fact_check["sources"] = sources_by_fact_check_id.get(str(fact_check.get("id", "")), [])
        detail["fact_checks"] = fact_checks
        detail["scores"] = []
        for row in conn.execute("SELECT * FROM scores WHERE debate_id = ? ORDER BY round", (debate_id,)):
            score = dict(row)
            score["breakdown"] = json.loads(score.pop("breakdown_json"))
            detail["scores"].append(score)
        detail["sources"] = source_rows
    return detail


def get_sources(debate_id: str, device_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        debate = conn.execute("SELECT 1 FROM debates WHERE id = ? AND device_id = ?", (debate_id, device_id)).fetchone()
        if debate is None:
            raise KeyError(debate_id)
        return [dict(row) for row in conn.execute("SELECT * FROM sources WHERE debate_id = ?", (debate_id,))]


def delete_debate(debate_id: str, device_id: str) -> None:
    with connect() as conn:
        debate = conn.execute("SELECT 1 FROM debates WHERE id = ? AND device_id = ?", (debate_id, device_id)).fetchone()
        if debate is None:
            return
        conn.execute("DELETE FROM sources WHERE debate_id = ?", (debate_id,))
        conn.execute("DELETE FROM scores WHERE debate_id = ?", (debate_id,))
        conn.execute("DELETE FROM fact_checks WHERE debate_id = ?", (debate_id,))
        conn.execute("DELETE FROM claims WHERE debate_id = ?", (debate_id,))
        conn.execute("DELETE FROM messages WHERE debate_id = ?", (debate_id,))
        conn.execute("DELETE FROM debates WHERE id = ?", (debate_id,))


def clear_all(device_id: str) -> None:
    with connect() as conn:
        debate_ids = [row[0] for row in conn.execute("SELECT id FROM debates WHERE device_id = ?", (device_id,)).fetchall()]
        if not debate_ids:
            return
        placeholders = ",".join("?" for _ in debate_ids)
        conn.execute(f"DELETE FROM sources WHERE debate_id IN ({placeholders})", debate_ids)
        conn.execute(f"DELETE FROM scores WHERE debate_id IN ({placeholders})", debate_ids)
        conn.execute(f"DELETE FROM fact_checks WHERE debate_id IN ({placeholders})", debate_ids)
        conn.execute(f"DELETE FROM claims WHERE debate_id IN ({placeholders})", debate_ids)
        conn.execute(f"DELETE FROM messages WHERE debate_id IN ({placeholders})", debate_ids)
        conn.execute(f"DELETE FROM debates WHERE id IN ({placeholders})", debate_ids)
