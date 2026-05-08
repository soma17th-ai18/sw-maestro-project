from __future__ import annotations

from app.schemas import ScheduleAnalysis


def _text_block(text: str, *, weight: str | None = None, size: str | None = None) -> dict:
    block = {"type": "TextBlock", "text": text, "wrap": True}
    if weight:
        block["weight"] = weight
    if size:
        block["size"] = size
    return block


def adaptive_card(body: list[dict], actions: list[dict] | None = None) -> list[dict]:
    return [
        {
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.3",
                "body": body,
                "actions": actions or [],
            },
        }
    ]


def auth_card(webex_url: str, google_url: str) -> list[dict]:
    body = [
        _text_block("AI 소마 비서 연결", weight="Bolder", size="Medium"),
        _text_block("Webex 메시지 수집과 Google Calendar 등록 권한을 연결해주세요."),
    ]
    actions = [
        {"type": "Action.OpenUrl", "title": "Webex 연결", "url": webex_url},
        {"type": "Action.OpenUrl", "title": "Google 연결", "url": google_url},
    ]
    return adaptive_card(body, actions)


def candidate_card(candidate_id: int, analysis: ScheduleAnalysis) -> list[dict]:
    when = analysis.date or "날짜 미정"
    if analysis.start_time:
        when += f" {analysis.start_time}"
    if analysis.end_time:
        when += f"-{analysis.end_time}"
    body = [
        _text_block("일정 후보를 감지했습니다", weight="Bolder", size="Medium"),
        _text_block(f"제목: {analysis.title or '제목 미정'}"),
        _text_block(f"시간: {when}"),
        _text_block(f"유형: {analysis.type}"),
    ]
    if analysis.source_summary:
        body.append(_text_block(f"출처 요약: {analysis.source_summary}"))
    if analysis.ambiguities:
        body.append(_text_block("확인이 필요해요: " + ", ".join(analysis.ambiguities)))
    actions = [
        {"type": "Action.Submit", "title": "등록", "data": {"action": "approve", "candidate_id": candidate_id}},
        {"type": "Action.ShowCard", "title": "수정", "card": {
            "type": "AdaptiveCard",
            "body": [
                {"type": "Input.Text", "id": "correction", "isMultiline": True, "placeholder": "예: 오후 3시가 아니라 오후 4시, 제목은 멘토링"}
            ],
            "actions": [
                {"type": "Action.Submit", "title": "다시 분석", "data": {"action": "edit", "candidate_id": candidate_id}}
            ],
        }},
        {"type": "Action.Submit", "title": "무시", "data": {"action": "ignore", "candidate_id": candidate_id}},
    ]
    return adaptive_card(body, actions)


def needs_edit_card(candidate_id: int, analysis: ScheduleAnalysis) -> list[dict]:
    body = [
        _text_block("일정 후보지만 정보가 부족합니다", weight="Bolder", size="Medium"),
        _text_block(f"제목: {analysis.title or '제목 미정'}"),
        _text_block("수정 내용을 입력하면 다시 분석할게요."),
    ]
    if analysis.ambiguities:
        body.append(_text_block("확인 필요: " + ", ".join(analysis.ambiguities)))
    actions = [
        {"type": "Action.ShowCard", "title": "수정 입력", "card": {
            "type": "AdaptiveCard",
            "body": [
                {"type": "Input.Text", "id": "correction", "isMultiline": True, "placeholder": "예: 내일 오전 9시 회의"}
            ],
            "actions": [
                {"type": "Action.Submit", "title": "다시 분석", "data": {"action": "edit", "candidate_id": candidate_id}}
            ],
        }},
        {"type": "Action.Submit", "title": "무시", "data": {"action": "ignore", "candidate_id": candidate_id}},
    ]
    return adaptive_card(body, actions)
