from __future__ import annotations

import json
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.config import settings
from app.schemas import ScheduleAnalysis


def build_event_body(analysis: ScheduleAnalysis, source_text: str | None = None) -> dict[str, Any]:
    start = analysis.start_datetime()
    end = analysis.end_datetime()
    if not start or not end:
        raise ValueError("Calendar event requires date and start_time")
    description_parts = []
    if analysis.source_summary:
        description_parts.append(f"Webex 요약: {analysis.source_summary}")
    if source_text:
        description_parts.append(f"원문: {source_text}")
    return {
        "summary": analysis.title or "Webex 일정",
        "description": "\n\n".join(description_parts),
        "start": {"dateTime": start.isoformat(), "timeZone": settings.timezone},
        "end": {"dateTime": end.isoformat(), "timeZone": settings.timezone},
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": offset} for offset in analysis.reminder_offsets[:5]],
        },
    }


def insert_event(google_token_json: str, analysis: ScheduleAnalysis, source_text: str | None = None) -> str:
    token_info = json.loads(google_token_json)
    creds = Credentials.from_authorized_user_info(token_info, scopes=[settings.google_calendar_scope])
    service = build("calendar", "v3", credentials=creds)
    event = service.events().insert(
        calendarId="primary",
        body=build_event_body(analysis, source_text),
    ).execute()
    return event["id"]
