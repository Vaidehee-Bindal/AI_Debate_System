from pathlib import Path

from app import db


def test_get_debate_attaches_sources_to_fact_checks(tmp_path, monkeypatch):
    db_path = tmp_path / "debates.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    db.get_settings.cache_clear()

    try:
        db.init_db()
        debate = db.create_debate("AI should be regulated", 3, "balanced", "device-a")
        message = db.add_message(debate["id"], 1, "Pro Agent", "AI should be regulated.")
        claim = db.add_claim(debate["id"], message["id"], "Pro Agent", "AI should be regulated.")

        sources = [
            {"title": "Regulation Brief", "url": "https://example.com/brief", "snippet": "A concise summary."},
            {"title": "Policy Note", "url": "https://example.com/note", "snippet": "A second reference."},
        ]
        fact_check = db.add_fact_check(debate["id"], claim["id"], "Needs Evidence", 45, "Insufficient support.", sources)

        detail = db.get_debate(debate["id"], "device-a")

        assert detail["fact_checks"]
        assert detail["fact_checks"][0]["id"] == fact_check["id"]
        assert detail["fact_checks"][0]["sources"] == [
            {
                "id": detail["sources"][0]["id"],
                "debate_id": debate["id"],
                "fact_check_id": fact_check["id"],
                "title": "Regulation Brief",
                "url": "https://example.com/brief",
                "snippet": "A concise summary.",
            },
            {
                "id": detail["sources"][1]["id"],
                "debate_id": debate["id"],
                "fact_check_id": fact_check["id"],
                "title": "Policy Note",
                "url": "https://example.com/note",
                "snippet": "A second reference.",
            },
        ]
        assert detail["sources"][0]["fact_check_id"] == fact_check["id"]
        assert detail["sources"][1]["fact_check_id"] == fact_check["id"]
    finally:
        db.clear_all("device-a")
        db.get_settings.cache_clear()