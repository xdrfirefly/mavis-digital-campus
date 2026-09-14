from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ai.config import combined_environment

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"
TOKEN_FILENAME = ".google-calendar-token.json"
DEFAULT_TIMEOUT_SECONDS = 20

_pending: dict[str, tuple[str, float, str]] = {}
_access_token: str | None = None
_access_expires_at = 0.0


class GoogleCalendarError(RuntimeError):
    pass


def token_path(root: Path) -> Path:
    return root / TOKEN_FILENAME


def credentials() -> tuple[str, str]:
    env = combined_environment()
    return env.get("GOOGLE_CALENDAR_CLIENT_ID", "").strip(), env.get("GOOGLE_CALENDAR_CLIENT_SECRET", "").strip()


def configured(root: Path) -> bool:
    client_id, _ = credentials()
    return bool(client_id and token_path(root).is_file())


def _post_form(url: str, values: dict[str, str], timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    request = Request(url, data=urlencode(values).encode("utf-8"), headers={"Accept": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed Google endpoint only
            return json.loads(response.read(1_000_000).decode("utf-8"))
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read(200_000).decode("utf-8")).get("error_description")
        except Exception:
            detail = None
        raise GoogleCalendarError(detail or f"Google authorization returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise GoogleCalendarError("Google Calendar could not be reached. Check the internet connection and try again.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GoogleCalendarError("Google returned an authorization response that could not be read safely.") from exc


def begin_authorization(redirect_uri: str) -> str:
    client_id, _ = credentials()
    if not client_id:
        raise GoogleCalendarError("Google Calendar OAuth credentials are not configured in .env.")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    _pending[state] = (verifier, time.time() + 600, redirect_uri)
    return f"{AUTH_URL}?{urlencode({'client_id':client_id,'redirect_uri':redirect_uri,'response_type':'code','scope':SCOPE,'access_type':'offline','prompt':'consent','state':state,'code_challenge':challenge,'code_challenge_method':'S256'})}"


def complete_authorization(root: Path, *, state: str, code: str, redirect_uri: str) -> None:
    pending = _pending.pop(state, None)
    if not pending or pending[1] < time.time() or not secrets.compare_digest(pending[2], redirect_uri):
        raise GoogleCalendarError("The Google Calendar connection request expired or could not be verified.")
    client_id, client_secret = credentials()
    values = {"client_id": client_id, "code": code, "code_verifier": pending[0], "grant_type": "authorization_code", "redirect_uri": redirect_uri}
    if client_secret:
        values["client_secret"] = client_secret
    result = _post_form(TOKEN_URL, values)
    refresh_token = str(result.get("refresh_token") or "").strip()
    if not refresh_token:
        raise GoogleCalendarError("Google did not return offline authorization. Disconnect access in Google and connect again.")
    path = token_path(root)
    path.write_text(json.dumps({"refresh_token": refresh_token}), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    _remember_access(result)


def _remember_access(result: dict[str, Any]) -> str:
    global _access_token, _access_expires_at
    token = str(result.get("access_token") or "").strip()
    if not token:
        raise GoogleCalendarError("Google did not return an access token.")
    _access_token = token
    _access_expires_at = time.time() + max(60, int(result.get("expires_in") or 3600) - 60)
    return token


def access_token(root: Path) -> str:
    if _access_token and _access_expires_at > time.time():
        return _access_token
    client_id, client_secret = credentials()
    try:
        saved = json.loads(token_path(root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GoogleCalendarError("Google Calendar is not connected.") from exc
    values = {"client_id": client_id, "refresh_token": str(saved.get("refresh_token") or ""), "grant_type": "refresh_token"}
    if client_secret:
        values["client_secret"] = client_secret
    return _remember_access(_post_form(TOKEN_URL, values))


def list_primary_events(root: Path, *, time_min: str, time_max: str, timezone_name: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> list[dict[str, Any]]:
    token = access_token(root)
    params: dict[str, Any] = {"timeMin": time_min, "timeMax": time_max, "timeZone": timezone_name, "singleEvents": "true", "showDeleted": "true", "maxResults": "2500", "orderBy": "startTime"}
    items: list[dict[str, Any]] = []
    while True:
        request = Request(f"{EVENTS_URL}?{urlencode(params)}", headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed Google endpoint only
                payload = json.loads(response.read(8_000_000).decode("utf-8"))
        except HTTPError as exc:
            raise GoogleCalendarError(f"Google Calendar refresh returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError) as exc:
            raise GoogleCalendarError("Google Calendar could not be reached. Cached Campus events were kept.") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GoogleCalendarError("Google Calendar returned event data that could not be read safely.") from exc
        for item in payload.get("items") or []:
            # Deliberate privacy boundary: only these Google-owned fields leave the provider.
            items.append({key: item.get(key) for key in ("id", "status", "summary", "start", "end", "originalStartTime", "location", "updated")})
        page = str(payload.get("nextPageToken") or "")
        if not page:
            return items
        params["pageToken"] = page


def disconnect(root: Path) -> None:
    global _access_token, _access_expires_at
    _access_token = None
    _access_expires_at = 0.0
    path = token_path(root)
    if path.exists():
        path.unlink()
