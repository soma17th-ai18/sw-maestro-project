from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    webex_bot_token: str = os.getenv("WEBEX_BOT_TOKEN", "")
    webex_client_id: str = os.getenv("WEBEX_CLIENT_ID", "")
    webex_client_secret: str = os.getenv("WEBEX_CLIENT_SECRET", "")
    webex_redirect_uri: str = os.getenv(
        "WEBEX_REDIRECT_URI", "http://localhost:8000/oauth/webex/callback"
    )
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri: str = os.getenv(
        "GOOGLE_REDIRECT_URI", "http://localhost:8000/oauth/google/callback"
    )
    upstage_api_key: str = os.getenv("UPSTAGE_API_KEY", "")
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
    frontend_base_url: str = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")
    database_path: str = os.getenv("DATABASE_PATH", "./soma_secretary.db")
    session_cookie_name: str = os.getenv("SESSION_COOKIE_NAME", "soma_session")
    session_days: int = int(os.getenv("SESSION_DAYS", "7"))
    timezone: str = os.getenv("TIMEZONE", "Asia/Seoul")
    confidence_threshold: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.65"))
    process_own_messages: bool = os.getenv("PROCESS_OWN_MESSAGES", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    process_user_group_messages: bool = os.getenv("PROCESS_USER_GROUP_MESSAGES", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    webex_api_base: str = "https://webexapis.com/v1"
    webex_oauth_base: str = "https://webexapis.com/v1"
    upstage_base_url: str = "https://api.upstage.ai/v1"
    upstage_model: str = "solar-pro3"
    google_calendar_scope: str = "https://www.googleapis.com/auth/calendar.events"
    webex_scopes: str = "spark:messages_read spark:rooms_read spark:people_read spark:memberships_read"

    def require(self, *names: str) -> None:
        missing = [name for name in names if not getattr(self, name)]
        if missing:
            joined = ", ".join(missing)
            raise RuntimeError(f"Missing required environment values: {joined}")


settings = Settings()
