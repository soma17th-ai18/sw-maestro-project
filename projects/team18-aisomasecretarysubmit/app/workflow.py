from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from app import cards
from app.calendar_service import insert_event
from app.config import settings
from app.db import Database, utcnow
from app.schemas import ScheduleAnalysis
from app.solar import SolarAnalyzer
from app.webex import WebexClient


START_WORDS = {"시작", "start", "help", "도움말"}


def text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def should_notify(analysis: ScheduleAnalysis) -> bool:
    return bool(analysis.is_schedule and analysis.confidence >= settings.confidence_threshold)


def candidate_status(analysis: ScheduleAnalysis) -> str:
    if not analysis.has_required_time:
        return "needs_edit"
    return "pending"


async def send_auth_links(database: Database, person_id: str, room_id: str | None) -> None:
    from app.webex import webex_authorize_url
    from app.oauth_google import google_flow

    webex_state = database.create_auth_state("webex", person_id, room_id)
    google_state = database.create_auth_state("google", person_id, room_id)
    webex_url = webex_authorize_url(webex_state)
    google_url, _ = google_flow(google_state).authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    bot = WebexClient(settings.webex_bot_token)
    await bot.create_message(
        markdown="AI 소마 비서 연결 링크입니다.",
        room_id=room_id,
        to_person_id=None if room_id else person_id,
        attachments=cards.auth_card(webex_url, google_url),
    )


async def handle_message_webhook(database: Database, payload: dict) -> dict:
    data = payload.get("data", {})
    message_id = data.get("id")
    if not message_id:
        return {"status": "ignored", "reason": "missing message id"}

    if database.fetchone("SELECT id FROM messages WHERE webex_message_id = ?", (message_id,)):
        return {"status": "ignored", "reason": "duplicate"}

    token = settings.webex_bot_token
    user_row = None
    webhook_row = database.fetchone("SELECT * FROM webhooks WHERE webhook_id = ?", (payload.get("id"),))
    if webhook_row and webhook_row["owner_type"] == "user" and webhook_row["owner_user_id"]:
        user_row = database.fetchone("SELECT * FROM users WHERE id = ?", (webhook_row["owner_user_id"],))
        if user_row and user_row["webex_access_token"]:
            token = user_row["webex_access_token"]

    client = WebexClient(token)
    message = await client.get_message(message_id)
    text = message.get("text") or message.get("markdown") or ""
    sender_id = message.get("personId")
    room_id = message.get("roomId") or data.get("roomId")
    room_type = message.get("roomType") or data.get("roomType")

    if not text.strip():
        return {"status": "ignored", "reason": "empty"}

    bot_person_id = await get_bot_person_id(database)
    if sender_id == bot_person_id:
        return {"status": "ignored", "reason": "bot message"}

    if user_row and sender_id == user_row["webex_person_id"] and not settings.process_own_messages:
        return {"status": "ignored", "reason": "own direct message"}

    if text.strip().lower() in START_WORDS:
        database.upsert_user(sender_id, bot_room_id=room_id)
        await send_auth_links(database, sender_id, room_id)
        return {"status": "auth_links_sent"}

    cur = database.execute(
        """
        INSERT INTO messages (webex_message_id, room_id, room_type, sender_person_id, text, text_hash, processed_status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (message_id, room_id, room_type, sender_id, text, text_hash(text), "received", utcnow()),
    )
    local_message_id = int(cur.lastrowid)

    if not user_row:
        user_row = database.fetchone("SELECT * FROM users WHERE webex_person_id = ?", (sender_id,))
    if not user_row and room_type == "group":
        user_row = database.fetchone(
            "SELECT * FROM users WHERE google_token_json IS NOT NULL AND webex_access_token IS NOT NULL ORDER BY id LIMIT 1"
        )
    if not user_row:
        return {"status": "ignored", "reason": "user not connected"}

    analysis = SolarAnalyzer().analyze(text, created_at=message.get("created"))
    status = candidate_status(analysis)
    if not should_notify(analysis):
        database.execute(
            "UPDATE messages SET processed_status = ? WHERE id = ?",
            ("not_schedule", local_message_id),
        )
        return {"status": "not_schedule", "confidence": analysis.confidence}

    candidate_id = create_candidate(database, int(user_row["id"]), local_message_id, analysis, status)
    card = cards.needs_edit_card(candidate_id, analysis) if status == "needs_edit" else cards.candidate_card(candidate_id, analysis)
    await WebexClient(settings.webex_bot_token).create_message(
        markdown="일정 후보를 감지했습니다.",
        to_person_id=user_row["webex_person_id"],
        attachments=card,
    )
    database.execute("UPDATE messages SET processed_status = ? WHERE id = ?", ("candidate_sent", local_message_id))
    return {"status": "candidate_sent", "candidate_id": candidate_id}


def create_candidate(database: Database, user_id: int, message_id: int | None, analysis: ScheduleAnalysis, status: str) -> int:
    cur = database.execute(
        """
        INSERT INTO candidates (user_id, message_id, analysis_json, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, message_id, analysis.model_dump_json(), status, utcnow(), utcnow()),
    )
    return int(cur.lastrowid)


async def get_bot_person_id(database: Database) -> str | None:
    row = database.fetchone("SELECT webex_person_id FROM users WHERE webex_person_id LIKE 'bot:%'")
    if row:
        return row["webex_person_id"].removeprefix("bot:")
    me = await WebexClient(settings.webex_bot_token).get_me()
    person_id = me.get("id")
    if person_id:
        database.upsert_user(f"bot:{person_id}", webex_display_name=me.get("displayName"))
    return person_id


async def handle_action(database: Database, action_payload: dict) -> dict:
    inputs = action_payload.get("inputs", {})
    action = inputs.get("action")
    candidate_id = int(inputs.get("candidate_id", 0))
    correction = inputs.get("correction", "")
    return await perform_candidate_action(database, candidate_id, action, correction=correction)


async def perform_candidate_action(
    database: Database,
    candidate_id: int,
    action: str | None,
    *,
    correction: str = "",
    notify_webex: bool = True,
) -> dict:
    candidate = database.fetchone("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
    if not candidate:
        return {"status": "ignored", "reason": "candidate not found"}

    user = database.fetchone("SELECT * FROM users WHERE id = ?", (candidate["user_id"],))
    analysis = ScheduleAnalysis.model_validate(json.loads(candidate["analysis_json"]))

    if action == "ignore":
        database.execute("UPDATE candidates SET status = ?, updated_at = ? WHERE id = ?", ("ignored", utcnow(), candidate_id))
        await notify_user(user, "일정 후보를 무시했습니다.", enabled=notify_webex)
        return {"status": "ignored"}

    if action == "edit":
        source_text = source_text_for_candidate(database, candidate)
        new_analysis = SolarAnalyzer().analyze(source_text, correction=correction)
        new_status = candidate_status(new_analysis)
        database.execute(
            "UPDATE candidates SET analysis_json = ?, status = ?, updated_at = ? WHERE id = ?",
            (new_analysis.model_dump_json(), new_status, utcnow(), candidate_id),
        )
        card = cards.needs_edit_card(candidate_id, new_analysis) if new_status == "needs_edit" else cards.candidate_card(candidate_id, new_analysis)
        await notify_user(user, "수정 내용을 반영해 다시 분석했습니다.", attachments=card, enabled=notify_webex)
        return {"status": "reanalyzed", "candidate_status": new_status}

    if action == "approve":
        if not user["google_token_json"]:
            await notify_user(user, "Google Calendar 연결이 필요합니다. 먼저 Google 연결을 완료해주세요.", enabled=notify_webex)
            return {"status": "needs_google"}
        if not analysis.has_required_time:
            await notify_user(user, "날짜/시간이 아직 불명확해 등록하지 않았습니다. 수정 후 다시 등록해주세요.", enabled=notify_webex)
            return {"status": "needs_edit"}
        source_text = source_text_for_candidate(database, candidate)
        event_id = insert_event(user["google_token_json"], analysis, source_text)
        database.execute(
            "UPDATE candidates SET status = ?, google_event_id = ?, updated_at = ? WHERE id = ?",
            ("registered", event_id, utcnow(), candidate_id),
        )
        schedule_reminders(database, candidate_id, analysis)
        await notify_user(user, f"Google Calendar에 등록했습니다: **{analysis.title or 'Webex 일정'}**", enabled=notify_webex)
        return {"status": "registered", "event_id": event_id}

    return {"status": "ignored", "reason": "unknown action"}


async def notify_user(user, markdown: str, *, attachments: list[dict] | None = None, enabled: bool = True) -> None:
    if not enabled or not settings.webex_bot_token or not user:
        return
    await WebexClient(settings.webex_bot_token).create_message(
        markdown=markdown,
        to_person_id=user["webex_person_id"],
        attachments=attachments,
    )


def source_text_for_candidate(database: Database, candidate) -> str:
    if not candidate["message_id"]:
        return ""
    row = database.fetchone("SELECT text FROM messages WHERE id = ?", (candidate["message_id"],))
    return row["text"] if row else ""


def schedule_reminders(database: Database, candidate_id: int, analysis: ScheduleAnalysis) -> None:
    start = analysis.start_datetime()
    if not start:
        return
    for offset in analysis.reminder_offsets[:5]:
        fire_at = (start - timedelta(minutes=offset)).isoformat()
        database.execute(
            "INSERT INTO reminders (candidate_id, fire_at, status, created_at) VALUES (?, ?, ?, ?)",
            (candidate_id, fire_at, "scheduled", utcnow()),
        )
