from __future__ import annotations

import json
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.db import Database, utcnow
from app.schemas import ScheduleAnalysis
from app.webex import WebexClient


async def send_due_reminders(database: Database) -> None:
    now = datetime.now().isoformat()
    rows = database.fetchall(
        """
        SELECT r.id AS reminder_id, c.analysis_json, u.webex_person_id
        FROM reminders r
        JOIN candidates c ON c.id = r.candidate_id
        JOIN users u ON u.id = c.user_id
        WHERE r.status = 'scheduled' AND r.fire_at <= ?
        """,
        (now,),
    )
    if not rows:
        return
    bot = WebexClient(settings.webex_bot_token)
    for row in rows:
        analysis = ScheduleAnalysis.model_validate(json.loads(row["analysis_json"]))
        title = analysis.title or "Webex 일정"
        when = f"{analysis.date or ''} {analysis.start_time or ''}".strip()
        await bot.create_message(
            markdown=f"[Reminder] 곧 **{title}** 일정이 있습니다. ({when})",
            to_person_id=row["webex_person_id"],
        )
        database.execute(
            "UPDATE reminders SET status = ?, sent_at = ? WHERE id = ?",
            ("sent", utcnow(), row["reminder_id"]),
        )


def create_scheduler(database: Database) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(send_due_reminders, "interval", seconds=30, args=[database])
    return scheduler
