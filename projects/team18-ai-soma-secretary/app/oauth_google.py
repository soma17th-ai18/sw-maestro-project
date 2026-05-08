from __future__ import annotations

from google_auth_oauthlib.flow import Flow

from app.config import settings


def google_flow(state: str | None = None) -> Flow:
    settings.require("google_client_id", "google_client_secret")
    config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }
    return Flow.from_client_config(
        config,
        scopes=[settings.google_calendar_scope],
        redirect_uri=settings.google_redirect_uri,
        state=state,
    )
