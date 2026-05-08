import json

import anyio
from fastapi.testclient import TestClient

import app.main as main
import app.workflow as workflow
from app.db import Database, utcnow
from app.schemas import ScheduleAnalysis
from app.workflow import create_candidate


def make_database(tmp_path):
    database = Database(str(tmp_path / "test.sqlite3"))
    database.init()
    return database


def insert_message(database: Database, text: str) -> int:
    cur = database.execute(
        """
        INSERT INTO messages (webex_message_id, room_id, room_type, sender_person_id, text, text_hash, processed_status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("message-1", "room-1", "direct", "person-1", text, "hash-1", "candidate_sent", utcnow()),
    )
    return int(cur.lastrowid)


def make_candidate(database: Database, user_id: int, message_id: int, *, status: str = "pending", ambiguities=None) -> int:
    analysis = ScheduleAnalysis(
        is_schedule=True,
        type="calendar_event",
        title="소마 멘토링",
        date="2026-05-09",
        start_time="15:00",
        end_time="16:00",
        confidence=0.92,
        ambiguities=ambiguities or [],
        source_summary="내일 오후 3시 소마 멘토링",
    )
    return create_candidate(database, user_id, message_id, analysis, status)


def client_for_user(monkeypatch, database: Database, user):
    monkeypatch.setattr(main, "db", database)
    main.app.dependency_overrides[main.current_user] = lambda: user
    return TestClient(main.app)


def test_candidates_api_only_returns_current_user_candidates(tmp_path, monkeypatch):
    database = make_database(tmp_path)
    user_id = database.upsert_user("person-1", webex_display_name="User One")
    other_user_id = database.upsert_user("person-2", webex_display_name="User Two")
    message_id = insert_message(database, "내일 오후 3시 소마 멘토링")
    make_candidate(database, user_id, message_id)
    make_candidate(database, other_user_id, message_id)
    user = database.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))

    client = client_for_user(monkeypatch, database, user)
    response = client.get("/api/candidates")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["candidates"]) == 1
    assert payload["candidates"][0]["analysis"]["title"] == "소마 멘토링"
    main.app.dependency_overrides.clear()


def test_approve_api_requires_google_connection(tmp_path, monkeypatch):
    database = make_database(tmp_path)
    user_id = database.upsert_user("person-1", webex_display_name="User One")
    message_id = insert_message(database, "내일 오후 3시 소마 멘토링")
    candidate_id = make_candidate(database, user_id, message_id)
    user = database.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
    monkeypatch.setattr(workflow, "notify_user", async_noop)

    client = client_for_user(monkeypatch, database, user)
    response = client.post(f"/api/candidates/{candidate_id}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "needs_google"
    main.app.dependency_overrides.clear()


def test_approve_api_keeps_ambiguous_candidate_needing_edit(tmp_path, monkeypatch):
    database = make_database(tmp_path)
    user_id = database.upsert_user(
        "person-1",
        webex_display_name="User One",
        google_token_json={"token": "fake"},
    )
    message_id = insert_message(database, "다음 회의 잡아줘")
    candidate_id = make_candidate(database, user_id, message_id, status="needs_edit", ambiguities=["오전/오후 불명확"])
    user = database.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
    monkeypatch.setattr(workflow, "notify_user", async_noop)

    client = client_for_user(monkeypatch, database, user)
    response = client.post(f"/api/candidates/{candidate_id}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "needs_edit"
    main.app.dependency_overrides.clear()


def test_edit_api_updates_candidate_from_solar_reanalysis(tmp_path, monkeypatch):
    database = make_database(tmp_path)
    user_id = database.upsert_user("person-1", webex_display_name="User One")
    message_id = insert_message(database, "회의 잡아줘")
    candidate_id = make_candidate(database, user_id, message_id, status="needs_edit", ambiguities=["시간 불명확"])
    user = database.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
    monkeypatch.setattr(workflow, "notify_user", async_noop)
    monkeypatch.setattr(workflow, "SolarAnalyzer", FakeSolarAnalyzer)

    client = client_for_user(monkeypatch, database, user)
    response = client.post(f"/api/candidates/{candidate_id}/edit", json={"correction": "오후 4시"})

    assert response.status_code == 200
    assert response.json()["candidate_status"] == "pending"
    row = database.fetchone("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
    analysis = json.loads(row["analysis_json"])
    assert analysis["start_time"] == "16:00"
    main.app.dependency_overrides.clear()


def test_webex_action_delegates_to_common_candidate_action(monkeypatch):
    calls = []

    async def fake_action(database, candidate_id, action, *, correction="", notify_webex=True):
        calls.append((candidate_id, action, correction, notify_webex))
        return {"status": "ok"}

    monkeypatch.setattr(workflow, "perform_candidate_action", fake_action)
    result = anyio.run(
        workflow.handle_action,
        None,
        {"inputs": {"candidate_id": "42", "action": "edit", "correction": "오후 4시"}},
    )

    assert result == {"status": "ok"}
    assert calls == [(42, "edit", "오후 4시", True)]


async def async_noop(*args, **kwargs):
    return None


class FakeSolarAnalyzer:
    def analyze(self, text: str, *, created_at: str | None = None, correction: str | None = None):
        return ScheduleAnalysis(
            is_schedule=True,
            type="calendar_event",
            title="소마 멘토링",
            date="2026-05-09",
            start_time="16:00",
            end_time="17:00",
            confidence=0.95,
            ambiguities=[],
            source_summary="수정된 소마 멘토링",
        )
