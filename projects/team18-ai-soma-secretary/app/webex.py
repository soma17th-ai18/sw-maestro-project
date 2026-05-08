from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.config import settings


def webex_authorize_url(state: str) -> str:
    query = urlencode(
        {
            "client_id": settings.webex_client_id,
            "response_type": "code",
            "redirect_uri": settings.webex_redirect_uri,
            "scope": settings.webex_scopes,
            "state": state,
        }
    )
    return f"https://webexapis.com/v1/authorize?{query}"


async def exchange_webex_code(code: str) -> dict:
    settings.require("webex_client_id", "webex_client_secret")
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.post(
            f"{settings.webex_oauth_base}/access_token",
            data={
                "grant_type": "authorization_code",
                "client_id": settings.webex_client_id,
                "client_secret": settings.webex_client_secret,
                "code": code,
                "redirect_uri": settings.webex_redirect_uri,
            },
        )
        res.raise_for_status()
        return res.json()


def webex_token_expires_at(token_payload: dict) -> str:
    seconds = int(token_payload.get("expires_in", 0))
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


class WebexClient:
    def __init__(self, token: str):
        self.token = token

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    async def get_me(self) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.get(f"{settings.webex_api_base}/people/me", headers=self.headers)
            res.raise_for_status()
            return res.json()

    async def get_message(self, message_id: str) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.get(f"{settings.webex_api_base}/messages/{message_id}", headers=self.headers)
            res.raise_for_status()
            return res.json()

    async def create_message(
        self,
        *,
        markdown: str,
        room_id: str | None = None,
        to_person_id: str | None = None,
        attachments: list[dict] | None = None,
    ) -> dict:
        body: dict = {"markdown": markdown}
        if room_id:
            body["roomId"] = room_id
        if to_person_id:
            body["toPersonId"] = to_person_id
        if attachments:
            body["attachments"] = attachments
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.post(f"{settings.webex_api_base}/messages", headers=self.headers, json=body)
            res.raise_for_status()
            return res.json()

    async def get_attachment_action(self, action_id: str) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.get(f"{settings.webex_api_base}/attachment/actions/{action_id}", headers=self.headers)
            res.raise_for_status()
            return res.json()

    async def create_webhook(
        self,
        *,
        name: str,
        target_url: str,
        resource: str,
        event: str,
        filter_value: str | None = None,
    ) -> dict:
        body = {"name": name, "targetUrl": target_url, "resource": resource, "event": event}
        if filter_value:
            body["filter"] = filter_value
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.post(f"{settings.webex_api_base}/webhooks", headers=self.headers, json=body)
            res.raise_for_status()
            return res.json()

    async def list_webhooks(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.get(f"{settings.webex_api_base}/webhooks", headers=self.headers)
            res.raise_for_status()
            return res.json().get("items", [])
