from app import db


def test_history_isolated_per_device(tmp_path, monkeypatch):
    db_path = tmp_path / "debates.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    db.get_settings.cache_clear()

    try:
        db.init_db()
        alpha = db.create_debate("Alpha topic", 3, "balanced", "device-alpha")
        beta = db.create_debate("Beta topic", 3, "balanced", "device-beta")

        assert [item["id"] for item in db.list_debates("device-alpha")] == [alpha["id"]]
        assert [item["id"] for item in db.list_debates("device-beta")] == [beta["id"]]

        assert db.get_debate(alpha["id"], "device-alpha")["topic"] == "Alpha topic"

        try:
            db.get_debate(alpha["id"], "device-beta")
            raise AssertionError("Expected the wrong device to be denied access")
        except KeyError:
            pass

        db.delete_debate(alpha["id"], "device-beta")
        assert [item["id"] for item in db.list_debates("device-alpha")] == [alpha["id"]]

        db.delete_debate(alpha["id"], "device-alpha")
        assert db.list_debates("device-alpha") == []
        assert [item["id"] for item in db.list_debates("device-beta")] == [beta["id"]]

        db.clear_all("device-beta")
        assert db.list_debates("device-beta") == []
    finally:
        db.clear_all("device-alpha")
        db.clear_all("device-beta")
        db.get_settings.cache_clear()
