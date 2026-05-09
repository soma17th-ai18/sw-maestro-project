from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

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
- Use the `now` field to resolve relative dates like '오늘', '내일', '이번 주 목요일', '다음 주 월요일' into exact YYYY-MM-DD dates.
- If 오전/오후 is not explicitly stated, set needs_user_approval=true and add to ambiguities. Never default to 오전.
- For deadlines, use the deadline time as start_time when available.
- If not a schedule/deadline/task, return is_schedule=false and type="none".
- Keep Korean titles short and practical.
"""


def get_week_dates() -> dict:
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    this_week = {days[i]: (monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}
    next_monday = monday + timedelta(weeks=1)
    next_week = {days[i]: (next_monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}
    return {"this_week": this_week, "next_week": next_week}


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
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        print(f"[Solar] now={now}")
        user_content = {
            "now": now,
            "week_dates": get_week_dates(),
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
        print(f"[Solar] response={content}")
        result = parse_solar_json(content)
        if result.date:
            from datetime import date
            parsed_date = date.fromisoformat(result.date)
            if parsed_date < date.today():
                result.needs_user_approval = True
                if "과거 날짜입니다" not in result.ambiguities:
                    result.ambiguities.append("과거 날짜입니다")
        if result.start_time and not result.needs_user_approval:
            hour = int(result.start_time.split(":")[0])
            has_ampm = any(k in text for k in ["오전", "오후", "am", "AM", "pm", "PM"])
            has_time = bool(re.search(r"\d+\s*시", text))
            if has_time and not has_ampm and hour < 13:
                result.needs_user_approval = True
                if "오전/오후가 불분명합니다" not in result.ambiguities:
                    result.ambiguities.append("오전/오후가 불분명합니다")
        tomorrow_expressions = ["내일", "낼", "명일", "tomorrow", "tmr", "tmrw"]
        if any(expr in text for expr in tomorrow_expressions) and 0 <= datetime.now().hour < 6:
            result.needs_user_approval = True
            if "새벽에 보낸 메시지로 '내일'이 당일을 의미할 수 있습니다" not in result.ambiguities:
                result.ambiguities.append("새벽에 보낸 메시지로 '내일'이 당일을 의미할 수 있습니다")
        return result
