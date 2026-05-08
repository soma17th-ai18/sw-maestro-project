from __future__ import annotations

import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from app.config import settings


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    webex_person_id TEXT UNIQUE NOT NULL,
                    webex_email TEXT,
                    webex_display_name TEXT,
                    webex_access_token TEXT,
                    webex_refresh_token TEXT,
                    webex_token_expires_at TEXT,
                    google_token_json TEXT,
                    bot_room_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    webex_message_id TEXT UNIQUE NOT NULL,
                    room_id TEXT NOT NULL,
                    room_type TEXT,
                    sender_person_id TEXT,
                    text TEXT,
                    text_hash TEXT NOT NULL,
                    processed_status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    message_id INTEGER,
                    analysis_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    google_event_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(message_id) REFERENCES messages(id)
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id INTEGER NOT NULL,
                    fire_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    sent_at TEXT,
                    FOREIGN KEY(candidate_id) REFERENCES candidates(id)
                );

                CREATE TABLE IF NOT EXISTS webhooks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    webhook_id TEXT UNIQUE NOT NULL,
                    owner_type TEXT NOT NULL,
                    owner_user_id INTEGER,
                    resource TEXT NOT NULL,
                    event TEXT NOT NULL,
                    filter TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS auth_states (
                    state TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    webex_person_id TEXT,
                    room_id TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
                """
            )
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(webhooks)").fetchall()
            }
            if "owner_user_id" not in columns:
                conn.execute("ALTER TABLE webhooks ADD COLUMN owner_user_id INTEGER")

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self.connect() as conn:
            return conn.execute(sql, tuple(params))

    def fetchone(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(sql, tuple(params)).fetchone()

    def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(sql, tuple(params)).fetchall()

    def create_auth_state(self, provider: str, webex_person_id: str | None, room_id: str | None) -> str:
        state = secrets.token_urlsafe(24)
        self.execute(
            "INSERT INTO auth_states (state, provider, webex_person_id, room_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (state, provider, webex_person_id, room_id, utcnow()),
        )
        return state

    def pop_auth_state(self, state: str, provider: str) -> sqlite3.Row | None:
        row = self.fetchone(
            "SELECT * FROM auth_states WHERE state = ? AND provider = ?", (state, provider)
        )
        if row:
            self.execute("DELETE FROM auth_states WHERE state = ?", (state,))
        return row

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=settings.session_days)
        self.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, now.isoformat(), expires_at.isoformat()),
        )
        return token

    def get_session_user(self, token: str | None) -> sqlite3.Row | None:
        if not token:
            return None
        row = self.fetchone(
            """
            SELECT u.*
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > ?
            """,
            (token, utcnow()),
        )
        if not row:
            self.execute("DELETE FROM sessions WHERE token = ?", (token,))
        return row

    def delete_session(self, token: str | None) -> None:
        if token:
            self.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def upsert_user(
        self,
        webex_person_id: str,
        *,
        webex_email: str | None = None,
        webex_display_name: str | None = None,
        webex_access_token: str | None = None,
        webex_refresh_token: str | None = None,
        webex_token_expires_at: str | None = None,
        google_token_json: dict[str, Any] | None = None,
        bot_room_id: str | None = None,
    ) -> int:
        existing = self.fetchone("SELECT id FROM users WHERE webex_person_id = ?", (webex_person_id,))
        now = utcnow()
        google_payload = json.dumps(google_token_json) if google_token_json else None
        if existing:
            self.execute(
                """
                UPDATE users
                SET webex_email = COALESCE(?, webex_email),
                    webex_display_name = COALESCE(?, webex_display_name),
                    webex_access_token = COALESCE(?, webex_access_token),
                    webex_refresh_token = COALESCE(?, webex_refresh_token),
                    webex_token_expires_at = COALESCE(?, webex_token_expires_at),
                    google_token_json = COALESCE(?, google_token_json),
                    bot_room_id = COALESCE(?, bot_room_id),
                    updated_at = ?
                WHERE webex_person_id = ?
                """,
                (
                    webex_email,
                    webex_display_name,
                    webex_access_token,
                    webex_refresh_token,
                    webex_token_expires_at,
                    google_payload,
                    bot_room_id,
                    now,
                    webex_person_id,
                ),
            )
            return int(existing["id"])
        cur = self.execute(
            """
            INSERT INTO users (
                webex_person_id, webex_email, webex_display_name, webex_access_token,
                webex_refresh_token, webex_token_expires_at, google_token_json,
                bot_room_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                webex_person_id,
                webex_email,
                webex_display_name,
                webex_access_token,
                webex_refresh_token,
                webex_token_expires_at,
                google_payload,
                bot_room_id,
                now,
                now,
            ),
        )
        return int(cur.lastrowid)


db = Database(settings.database_path)
