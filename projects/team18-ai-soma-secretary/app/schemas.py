from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ScheduleAnalysis(BaseModel):
    is_schedule: bool = False
    type: Literal["calendar_event", "deadline", "task", "none"] = "none"
    title: str | None = None
    date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_user_approval: bool = True
    ambiguities: list[str] = Field(default_factory=list)
    reminder_offsets: list[int] = Field(default_factory=lambda: [60])
    source_summary: str | None = None

    @field_validator("date")
    @classmethod
    def valid_date(cls, value: str | None) -> str | None:
        if value:
            date.fromisoformat(value)
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def valid_time(cls, value: str | None) -> str | None:
        if value:
            time.fromisoformat(value)
        return value

    @property
    def has_required_time(self) -> bool:
        return bool(self.date and self.start_time)

    def start_datetime(self) -> datetime | None:
        if not self.date or not self.start_time:
            return None
        return datetime.fromisoformat(f"{self.date}T{self.start_time}")

    def end_datetime(self) -> datetime | None:
        if not self.date:
            return None
        if self.end_time:
            return datetime.fromisoformat(f"{self.date}T{self.end_time}")
        start = self.start_datetime()
        return start + timedelta(hours=1) if start else None
