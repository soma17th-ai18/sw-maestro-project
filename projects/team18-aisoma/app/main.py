from __future__ import annotations

import json
import logging
from typing import Any

from urllib.parse import urlencode

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import settings
from app.db import db, utcnow
from app.oauth_google import google_flow
from app.reminders import create_scheduler
from app.schemas import ScheduleAnalysis
from app.webex import WebexClient, exchange_webex_code, webex_authorize_url, webex_token_expires_at
from app.workflow import handle_action, handle_message_webhook, perform_candidate_action

app = FastAPI(title="AI Soma Secretary")
scheduler = create_scheduler(db)
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list({settings.frontend_base_url, "http://localhost:3000", "http://127.0.0.1:3000"}),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    db.init()
    if not scheduler.running:
        scheduler.start()
    await auto_register_webhooks()


@app.on_event("shutdown")
async def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown()


async def auto_register_webhooks() -> None:
    if not settings.webex_bot_token or not settings.public_base_url.startswith("https://"):
        return
    try:
        await register_webhooks()
    except Exception as exc:
        logger.warning("Automatic Webex webhook registration failed: %s", exc)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "service": "ai-soma-secretary"}


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return """
    <html>
      <head><title>AI Soma Secretary</title></head>
      <body>
        <h1>AI Soma Secretary</h1>
        <p>Open the web console to connect Webex and Google Calendar.</p>
        <p>Console: <a href="http://localhost:3000">http://localhost:3000</a></p>
        <p>Health: <a href="/health">/health</a></p>
      </body>
    </html>
    """


def set_session_cookie(response: Response, user_id: int) -> None:
    token = db.create_session(user_id)
    set_session_token_cookie(response, token)


def set_session_token_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        samesite="lax",
        max_age=settings.session_days * 24 * 60 * 60,
    )


def current_user(token: str | None = Cookie(default=None, alias=settings.session_cookie_name)):
    user = db.get_session_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@app.get("/oauth/webex/start")
async def oauth_webex_start(
    person_id: str = Query(...),
    room_id: str | None = Query(default=None),
) -> RedirectResponse:
    settings.require("webex_client_id")
    state = db.create_auth_state("webex", person_id, room_id)
    return RedirectResponse(webex_authorize_url(state))


@app.get("/oauth/webex/callback")
async def oauth_webex_callback(code: str, state: str) -> Response:
    auth_state = db.pop_auth_state(state, "webex")
    login_flow = False
    if not auth_state:
        auth_state = db.pop_auth_state(state, "webex_login")
        login_flow = bool(auth_state)
    if not auth_state:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    token_payload = await exchange_webex_code(code)
    user_client = WebexClient(token_payload["access_token"])
    me = await user_client.get_me()
    webex_person_id = me["id"]
    user_id = db.upsert_user(
        webex_person_id,
        webex_email=(me.get("emails") or [None])[0],
        webex_display_name=me.get("displayName"),
        webex_access_token=token_payload["access_token"],
        webex_refresh_token=token_payload.get("refresh_token"),
        webex_token_expires_at=webex_token_expires_at(token_payload),
        bot_room_id=auth_state["room_id"],
    )
    user = db.fetchone("SELECT id FROM users WHERE webex_person_id = ?", (webex_person_id,))
    await ensure_user_direct_message_webhook(user_client, webex_person_id, int(user["id"]))
    if login_flow:
        token = db.create_session(user_id)
        redirect_url = f"{settings.frontend_base_url}/dashboard?{urlencode({'session_token': token})}"
        response = RedirectResponse(redirect_url)
        set_session_token_cookie(response, token)
        return response
    await maybe_notify_webex(
        auth_state["room_id"],
        webex_person_id,
        "Webex 연결이 완료되었습니다. 이제 Google Calendar 연결도 완료해주세요.",
    )
    return HTMLResponse("Webex 연결이 완료되었습니다. Webex로 돌아가세요.")


@app.get("/auth/webex/login")
async def auth_webex_login() -> RedirectResponse:
    settings.require("webex_client_id")
    state = db.create_auth_state("webex_login", None, None)
    return RedirectResponse(webex_authorize_url(state))


@app.get("/oauth/google/start")
async def oauth_google_start(
    person_id: str = Query(...),
    room_id: str | None = Query(default=None),
) -> RedirectResponse:
    state = db.create_auth_state("google", person_id, room_id)
    url, _ = google_flow(state).authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return RedirectResponse(url)


@app.get("/oauth/google/callback")
async def oauth_google_callback(request: Request, state: str) -> Response:
    auth_state = db.pop_auth_state(state, "google")
    login_flow = False
    if not auth_state:
        auth_state = db.pop_auth_state(state, "google_login")
        login_flow = bool(auth_state)
    if not auth_state:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    flow = google_flow(state)
    flow.fetch_token(authorization_response=str(request.url))
    creds = json.loads(flow.credentials.to_json())
    db.upsert_user(
        auth_state["webex_person_id"],
        google_token_json=creds,
        bot_room_id=auth_state["room_id"],
    )
    if login_flow:
        return RedirectResponse(f"{settings.frontend_base_url}/settings?google=connected")
    await maybe_notify_webex(
        auth_state["room_id"],
        auth_state["webex_person_id"],
        "Google Calendar 연결이 완료되었습니다. 이제 일정 후보를 등록할 수 있습니다.",
    )
    return HTMLResponse("Google Calendar 연결이 완료되었습니다. Webex로 돌아가세요.")


@app.get("/auth/google/login")
async def auth_google_login(user=Depends(current_user)) -> RedirectResponse:
    state = db.create_auth_state("google_login", user["webex_person_id"], user["bot_room_id"])
    url, _ = google_flow(state).authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return RedirectResponse(url)


@app.post("/webhooks/webex/messages")
async def webex_messages_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return await handle_message_webhook(db, payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/webhooks/webex/actions")
async def webex_actions_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    action_id = payload.get("data", {}).get("id")
    if not action_id:
        return {"status": "ignored", "reason": "missing action id"}
    try:
        details = await WebexClient(settings.webex_bot_token).get_attachment_action(action_id)
        return await handle_action(db, details)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/session")
async def api_session(user=Depends(current_user)) -> dict[str, Any]:
    return {"authenticated": True, "user": user_payload(user)}


@app.post("/api/logout")
async def api_logout(
    response: Response,
    token: str | None = Cookie(default=None, alias=settings.session_cookie_name),
) -> dict[str, Any]:
    db.delete_session(token)
    response.delete_cookie(settings.session_cookie_name)
    return {"ok": True}


@app.post("/api/session/claim")
async def api_session_claim(payload: dict[str, Any], response: Response) -> dict[str, Any]:
    token = str(payload.get("session_token") or "")
    user = db.get_session_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session token")
    set_session_token_cookie(response, token)
    return {"authenticated": True, "user": user_payload(user)}


@app.get("/api/dashboard")
async def api_dashboard(user=Depends(current_user)) -> dict[str, Any]:
    counts = {"pending": 0, "needs_edit": 0, "registered": 0, "ignored": 0}
    for row in db.fetchall(
        "SELECT status, COUNT(*) AS count FROM candidates WHERE user_id = ? GROUP BY status",
        (user["id"],),
    ):
        counts[row["status"]] = row["count"]
    recent = candidate_rows(user["id"], limit=5)
    return {
        "counts": counts,
        "recent": [candidate_payload(row) for row in recent],
        "connections": connection_payload(user),
    }


@app.get("/api/candidates")
async def api_candidates(status: str | None = Query(default=None), user=Depends(current_user)) -> dict[str, Any]:
    allowed = {"pending", "needs_edit", "registered", "ignored"}
    if status and status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid status")
    rows = candidate_rows(user["id"], status=status)
    return {"candidates": [candidate_payload(row) for row in rows]}


@app.get("/api/candidates/{candidate_id}")
async def api_candidate_detail(candidate_id: int, user=Depends(current_user)) -> dict[str, Any]:
    row = candidate_row(user["id"], candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"candidate": candidate_payload(row, include_source=True)}


@app.post("/api/candidates/{candidate_id}/approve")
async def api_candidate_approve(candidate_id: int, user=Depends(current_user)) -> dict[str, Any]:
    require_candidate_owner(user["id"], candidate_id)
    return await perform_candidate_action(db, candidate_id, "approve", notify_webex=True)


@app.post("/api/candidates/{candidate_id}/edit")
async def api_candidate_edit(candidate_id: int, payload: dict[str, Any], user=Depends(current_user)) -> dict[str, Any]:
    require_candidate_owner(user["id"], candidate_id)
    correction = str(payload.get("correction") or "").strip()
    if not correction:
        raise HTTPException(status_code=400, detail="correction is required")
    return await perform_candidate_action(db, candidate_id, "edit", correction=correction, notify_webex=True)


@app.post("/api/candidates/{candidate_id}/ignore")
async def api_candidate_ignore(candidate_id: int, user=Depends(current_user)) -> dict[str, Any]:
    require_candidate_owner(user["id"], candidate_id)
    return await perform_candidate_action(db, candidate_id, "ignore", notify_webex=True)


@app.get("/api/settings")
async def api_settings(user=Depends(current_user)) -> dict[str, Any]:
    required_env = [
        ("WEBEX_BOT_TOKEN", settings.webex_bot_token),
        ("WEBEX_CLIENT_ID", settings.webex_client_id),
        ("WEBEX_CLIENT_SECRET", settings.webex_client_secret),
        ("GOOGLE_CLIENT_ID", settings.google_client_id),
        ("GOOGLE_CLIENT_SECRET", settings.google_client_secret),
        ("UPSTAGE_API_KEY", settings.upstage_api_key),
        ("PUBLIC_BASE_URL", settings.public_base_url),
    ]
    missing = [name for name, value in required_env if not value]
    webhooks = db.fetchall(
        "SELECT owner_type, resource, event, filter FROM webhooks ORDER BY id DESC LIMIT 10"
    )
    return {
        "connections": connection_payload(user),
        "health": {"ok": True, "service": "ai-soma-secretary"},
        "webhooks": [dict(row) for row in webhooks],
        "missing_env": missing,
        "auth_urls": {
            "webex": "/auth/webex/login",
            "google": "/auth/google/login",
        },
    }


@app.post("/api/settings/webhooks/register")
async def api_register_webhooks(user=Depends(current_user)) -> dict[str, Any]:
    return await register_webhooks()


@app.post("/admin/webhooks/register")
async def register_webhooks() -> dict[str, Any]:
    settings.require("public_base_url", "webex_bot_token")
    results = []
    bot_client = WebexClient(settings.webex_bot_token)
    results.append(
        await register_one_webhook(
            bot_client,
            owner_type="bot",
            owner_user_id=None,
            name="AI Soma Bot direct messages",
            resource="messages",
            event="created",
            filter_value="roomType=direct",
            target_path="/webhooks/webex/messages",
        )
    )
    results.append(
        await register_one_webhook(
            bot_client,
            owner_type="bot",
            owner_user_id=None,
            name="AI Soma Bot group messages",
            resource="messages",
            event="created",
            filter_value="roomType=group",
            target_path="/webhooks/webex/messages",
        )
    )
    results.append(
        await register_one_webhook(
            bot_client,
                owner_type="bot",
                owner_user_id=None,
                name="AI Soma card actions",
            resource="attachmentActions",
            event="created",
            filter_value=None,
            target_path="/webhooks/webex/actions",
        )
    )
    users = db.fetchall("SELECT * FROM users WHERE webex_access_token IS NOT NULL")
    for user in users:
        client = WebexClient(user["webex_access_token"])
        results.append(
            await register_one_webhook(
                client,
                owner_type="user",
                owner_user_id=int(user["id"]),
                name=f"AI Soma direct messages {user['id']}",
                resource="messages",
                event="created",
                filter_value="roomType=direct",
                target_path="/webhooks/webex/messages",
            )
        )
        if settings.process_user_group_messages:
            results.append(
                await register_one_webhook(
                    client,
                    owner_type="user",
                    owner_user_id=int(user["id"]),
                    name=f"AI Soma group messages {user['id']}",
                    resource="messages",
                    event="created",
                    filter_value="roomType=group",
                    target_path="/webhooks/webex/messages",
                )
            )
    return {"registered": results}


def user_payload(user) -> dict[str, Any]:
    return {
        "id": user["id"],
        "webex_person_id": user["webex_person_id"],
        "email": user["webex_email"],
        "display_name": user["webex_display_name"],
    }


def connection_payload(user) -> dict[str, bool]:
    return {
        "webex_connected": bool(user["webex_access_token"]),
        "google_connected": bool(user["google_token_json"]),
    }


def candidate_rows(user_id: int, *, status: str | None = None, limit: int | None = None) -> list:
    sql = """
        SELECT c.*, m.text AS source_text, m.room_type, m.sender_person_id, m.created_at AS message_created_at
        FROM candidates c
        LEFT JOIN messages m ON m.id = c.message_id
        WHERE c.user_id = ?
    """
    params: list[Any] = [user_id]
    if status:
        sql += " AND c.status = ?"
        params.append(status)
    sql += " ORDER BY c.created_at DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return db.fetchall(sql, params)


def candidate_row(user_id: int, candidate_id: int):
    rows = db.fetchall(
        """
        SELECT c.*, m.text AS source_text, m.room_type, m.sender_person_id, m.created_at AS message_created_at
        FROM candidates c
        LEFT JOIN messages m ON m.id = c.message_id
        WHERE c.user_id = ? AND c.id = ?
        """,
        (user_id, candidate_id),
    )
    return rows[0] if rows else None


def require_candidate_owner(user_id: int, candidate_id: int) -> None:
    if not db.fetchone("SELECT id FROM candidates WHERE user_id = ? AND id = ?", (user_id, candidate_id)):
        raise HTTPException(status_code=404, detail="Candidate not found")


def candidate_payload(row, *, include_source: bool = False) -> dict[str, Any]:
    analysis = ScheduleAnalysis.model_validate(json.loads(row["analysis_json"]))
    payload = {
        "id": row["id"],
        "status": row["status"],
        "google_event_id": row["google_event_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "message": {
            "room_type": row["room_type"],
            "sender_person_id": row["sender_person_id"],
            "created_at": row["message_created_at"],
            "source_text": row["source_text"] if include_source else None,
        },
        "analysis": analysis.model_dump(),
    }
    if not include_source:
        payload["message"].pop("source_text")
    return payload


async def ensure_user_direct_message_webhook(client: WebexClient, webex_person_id: str, owner_user_id: int) -> None:
    await register_one_webhook(
        client,
        owner_type="user",
        owner_user_id=owner_user_id,
        name=f"AI Soma direct messages {webex_person_id[:8]}",
        resource="messages",
        event="created",
        filter_value="roomType=direct",
        target_path="/webhooks/webex/messages",
    )
    if settings.process_user_group_messages:
        await register_one_webhook(
            client,
            owner_type="user",
            owner_user_id=owner_user_id,
            name=f"AI Soma group messages {webex_person_id[:8]}",
            resource="messages",
            event="created",
            filter_value="roomType=group",
            target_path="/webhooks/webex/messages",
        )


async def register_one_webhook(
    client: WebexClient,
    *,
    owner_type: str,
    owner_user_id: int | None,
    name: str,
    resource: str,
    event: str,
    filter_value: str | None,
    target_path: str,
) -> dict[str, Any]:
    target_url = settings.public_base_url.rstrip("/") + target_path
    existing = await find_existing_webhook(
        client,
        target_url=target_url,
        resource=resource,
        event=event,
        filter_value=filter_value,
    )
    if existing:
        remember_webhook(existing["id"], owner_type, owner_user_id, resource, event, filter_value)
        return {
            "id": existing["id"],
            "owner_type": owner_type,
            "resource": resource,
            "event": event,
            "reused": True,
        }
    hook = await client.create_webhook(
        name=name,
        target_url=target_url,
        resource=resource,
        event=event,
        filter_value=filter_value,
    )
    remember_webhook(hook["id"], owner_type, owner_user_id, resource, event, filter_value)
    return {"id": hook["id"], "owner_type": owner_type, "resource": resource, "event": event}


async def find_existing_webhook(
    client: WebexClient,
    *,
    target_url: str,
    resource: str,
    event: str,
    filter_value: str | None,
) -> dict[str, Any] | None:
    for hook in await client.list_webhooks():
        if (
            hook.get("targetUrl") == target_url
            and hook.get("resource") == resource
            and hook.get("event") == event
            and (hook.get("filter") or None) == filter_value
        ):
            return hook
    return None


def remember_webhook(
    webhook_id: str,
    owner_type: str,
    owner_user_id: int | None,
    resource: str,
    event: str,
    filter_value: str | None,
) -> None:
    db.execute(
        """
        INSERT OR IGNORE INTO webhooks (webhook_id, owner_type, owner_user_id, resource, event, filter, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (webhook_id, owner_type, owner_user_id, resource, event, filter_value, utcnow()),
    )


async def maybe_notify_webex(room_id: str | None, person_id: str, markdown: str) -> None:
    if not settings.webex_bot_token:
        return
    await WebexClient(settings.webex_bot_token).create_message(
        markdown=markdown,
        room_id=room_id,
        to_person_id=None if room_id else person_id,
    )
