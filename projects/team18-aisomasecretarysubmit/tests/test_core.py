import json

from app.calendar_service import build_event_body
from app.schemas import ScheduleAnalysis
from app.solar import parse_solar_json
from app.workflow import candidate_status, should_notify, text_hash


def test_parse_solar_json_and_notify():
    analysis = parse_solar_json(
        json.dumps(
            {
                "is_schedule": True,
                "type": "calendar_event",
                "title": "멘토링",
                "date": "2026-05-07",
                "start_time": "15:00",
                "end_time": "16:00",
                "confidence": 0.91,
                "needs_user_approval": True,
                "ambiguities": [],
                "reminder_offsets": [60],
                "source_summary": "목요일 오후 3시 멘토링",
            },
            ensure_ascii=False,
        )
    )
    assert analysis.title == "멘토링"
    assert should_notify(analysis)
    assert candidate_status(analysis) == "pending"


def test_schedule_notifies_even_when_model_says_no_approval_needed():
    analysis = ScheduleAnalysis(
        is_schedule=True,
        type="calendar_event",
        title="미팅",
        date="2026-05-07",
        start_time="21:30",
        confidence=0.95,
        needs_user_approval=False,
    )
    assert should_notify(analysis)


def test_ambiguous_schedule_needs_edit():
    analysis = ScheduleAnalysis(
        is_schedule=True,
        type="calendar_event",
        title="회의",
        date="2026-05-07",
        start_time="09:00",
        confidence=0.8,
        ambiguities=["오전/오후 불명확"],
    )
    assert candidate_status(analysis) == "needs_edit"


def test_non_schedule_does_not_notify():
    analysis = ScheduleAnalysis(is_schedule=False, type="none", confidence=0.1)
    assert not should_notify(analysis)


def test_text_hash_is_stable():
    assert text_hash("  hello ") == text_hash("hello")


def test_build_google_calendar_event_body():
    analysis = ScheduleAnalysis(
        is_schedule=True,
        type="calendar_event",
        title="기획 회의",
        date="2026-05-07",
        start_time="15:00",
        end_time="16:00",
        confidence=0.9,
        reminder_offsets=[60, 10],
        source_summary="회의 공지",
    )
    body = build_event_body(analysis, "원문")
    assert body["summary"] == "기획 회의"
    assert body["start"]["dateTime"] == "2026-05-07T15:00:00"
    assert body["reminders"]["overrides"][0]["minutes"] == 60
