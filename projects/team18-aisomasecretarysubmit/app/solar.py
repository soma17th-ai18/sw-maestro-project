from __future__ import annotations

import json
from datetime import datetime

from openai import OpenAI

from app.config import settings
from app.schemas import ScheduleAnalysis


SYSTEM_PROMPT = """You are an AI schedule extractor for Korean Webex messages.
Return only valid JSON matching this schema:
{
  "is_schedule": boolean,
  "type": "calendar_event" | "deadline" | "task" | "none",
  "title": string | null,
  "date": "YYYY-MM-DD" | null,
  "start_time": "HH:MM" | null,
  "end_time": "HH:MM" | null,
  "confidence": number,
  "needs_user_approval": boolean,
  "ambiguities": string[],
  "reminder_offsets": number[],
  "source_summary": string | null
}
Rules:
- Use Asia/Seoul unless the message says otherwise.
- If 오전/오후 is ambiguous, include ambiguity and do not invent certainty.
- For deadlines, use the deadline time as start_time when available.
- If not a schedule/deadline/task, return is_schedule=false and type="none".
- Keep Korean titles short and practical.
"""


def parse_solar_json(raw: str) -> ScheduleAnalysis:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    data = json.loads(cleaned)
    return ScheduleAnalysis.model_validate(data)


class SolarAnalyzer:
    def __init__(self):
        settings.require("upstage_api_key")
        self.client = OpenAI(api_key=settings.upstage_api_key, base_url=settings.upstage_base_url)

    def analyze(self, text: str, *, created_at: str | None = None, correction: str | None = None) -> ScheduleAnalysis:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        user_content = {
            "now": now,
            "message_created_at": created_at,
            "message": text,
            "correction": correction,
        }
        response = self.client.chat.completions.create(
            model=settings.upstage_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content or "{}"
        return parse_solar_json(content)
