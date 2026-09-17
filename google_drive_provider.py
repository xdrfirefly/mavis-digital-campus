from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from ai.config import combined_environment

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_API = "https://www.googleapis.com/drive/v3"
SCOPE = "https://www.googleapis.com/auth/drive.file"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
SHORTCUT_MIME_TYPE = "application/vnd.google-apps.shortcut"
TOKEN_FILENAME = ".google-drive-token.json"
DEFAULT_TIMEOUT_SECONDS = 20
MAX_ROOT_CHILDREN = 100

_pending: dict[str, tuple[str, float, str]] = {}
_access_token: str | None = None
_access_expires_at = 0.0


class GoogleDriveError(RuntimeError):
    pass


def token_path(root: Path) -> Path:
    return root / TOKEN_FILENAME


def credentials() -> tuple[str, str]:
    env = combined_environment()
    return env.get("GOOGLE_DRIVE_CLIENT_ID", "").strip(), env.get("GOOGLE_DRIVE_CLIENT_SECRET", "").strip()


def configured(root: Path) -> bool:
    client_id, _ = credentials()
    if not client_id:
        return False
    try:
        saved = json.loads(token_path(root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(str(saved.get("refresh_token") or "").strip())


def _post_form(url: str, values: dict[str, str], timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    request = Request(url, data=urlencode(values).encode("utf-8"), headers={"Accept": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed Google endpoint only
            return json.loads(response.read(1_000_000).decode("utf-8"))
    except HTTPError as exc:
        raise GoogleDriveError(f"Google Drive authorization returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise GoogleDriveError("Google Drive could not be reached. Check the internet connection and try again.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GoogleDriveError("Google returned an authorization response that could not be read safely.") from exc


def _get_json(url: str, token: str, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    request = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": "Mavis-Digital-Campus/0.9.8"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed Google endpoint only
            return json.loads(response.read(4_000_000).decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            raise GoogleDriveError("The approved Google Drive root is missing or inaccessible.") from exc
        raise GoogleDriveError(f"Google Drive verification returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise GoogleDriveError("Google Drive could not be reached. The approved root was not changed.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GoogleDriveError("Google Drive returned data that could not be read safely.") from exc


def begin_authorization(redirect_uri: str) -> str:
    client_id, _ = credentials()
    if not client_id:
        raise GoogleDriveError("Google Drive OAuth credentials are not configured in .env.")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    _pending[state] = (verifier, time.time() + 600, redirect_uri)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "trigger_onepick": "true",
        "allow_folder_selection": "true",
        "allow_multiple": "false",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _safe_id(value: str) -> str:
    clean = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,}", clean):
        raise GoogleDriveError("Google Drive returned an invalid resource selection.")
    return clean


def _account(token: str) -> dict[str, str]:
    payload = _get_json(f"{DRIVE_API}/about?{urlencode({'fields':'user(permissionId)'})}", token)
    permission_id = str((payload.get("user") or {}).get("permissionId") or "").strip()
    if not permission_id:
        raise GoogleDriveError("Google Drive did not return a stable account identity.")
    return {"account_permission_id": permission_id}


def _folder(token: str, folder_id: str) -> dict[str, str]:
    folder_id = _safe_id(folder_id)
    fields = "id,name,mimeType,trashed,capabilities(canListChildren)"
    payload = _get_json(f"{DRIVE_API}/files/{quote(folder_id, safe='')}?{urlencode({'fields':fields,'supportsAllDrives':'true'})}", token)
    if payload.get("trashed"):
        raise GoogleDriveError("The approved Google Drive root is in the trash.")
    mime_type = str(payload.get("mimeType") or "")
    if mime_type == SHORTCUT_MIME_TYPE:
        raise GoogleDriveError("Google Drive shortcuts cannot be approved as the Campus root.")
    if mime_type != FOLDER_MIME_TYPE:
        raise GoogleDriveError("The selected Google Drive item is not a folder.")
    if not bool((payload.get("capabilities") or {}).get("canListChildren")):
        raise GoogleDriveError("The selected Google Drive folder cannot be listed by this account.")
    returned_id = _safe_id(str(payload.get("id") or ""))
    if not secrets.compare_digest(returned_id, folder_id):
        raise GoogleDriveError("Google Drive returned a different root than the one approved.")
    return {"approved_root_id": returned_id, "approved_root_name": str(payload.get("name") or "Google Drive folder")[:300]}


def complete_authorization(root: Path, *, state: str, code: str, redirect_uri: str, picked_file_ids: str) -> dict[str, str]:
    pending = _pending.pop(state, None)
    if not pending or pending[1] < time.time() or not secrets.compare_digest(pending[2], redirect_uri):
        raise GoogleDriveError("The Google Drive connection request expired or could not be verified.")
    selected = [item.strip() for item in str(picked_file_ids or "").split(",") if item.strip()]
    if len(selected) != 1:
        raise GoogleDriveError("Select exactly one Google Drive folder as the Campus root.")
    root_id = _safe_id(selected[0])
    client_id, client_secret = credentials()
    values = {"client_id": client_id, "code": code, "code_verifier": pending[0], "grant_type": "authorization_code", "redirect_uri": redirect_uri}
    if client_secret:
        values["client_secret"] = client_secret
    result = _post_form(TOKEN_URL, values)
    refresh_token = str(result.get("refresh_token") or "").strip()
    access = str(result.get("access_token") or "").strip()
    if not refresh_token or not access:
        raise GoogleDriveError("Google did not return offline Drive authorization. Disconnect access in Google and connect again.")
    binding = {**_folder(access, root_id), **_account(access)}
    path = token_path(root)
    path.write_text(json.dumps({"refresh_token": refresh_token}), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    _remember_access(result)
    return binding


def _remember_access(result: dict[str, Any]) -> str:
    global _access_token, _access_expires_at
    token = str(result.get("access_token") or "").strip()
    if not token:
        raise GoogleDriveError("Google did not return a Drive access token.")
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
        raise GoogleDriveError("Google Drive is not connected.") from exc
    values = {"client_id": client_id, "refresh_token": str(saved.get("refresh_token") or ""), "grant_type": "refresh_token"}
    if client_secret:
        values["client_secret"] = client_secret
    return _remember_access(_post_form(TOKEN_URL, values))


def verify_approved_root(root: Path, *, approved_root_id: str, account_permission_id: str) -> dict[str, str]:
    token = access_token(root)
    account = _account(token)
    if not account_permission_id or not secrets.compare_digest(account["account_permission_id"], str(account_permission_id)):
        raise GoogleDriveError("Google Drive is connected to a different account. Disconnect and approve a new root.")
    return {**_folder(token, approved_root_id), **account}


def list_approved_root_children(root: Path, *, approved_root_id: str, account_permission_id: str) -> list[dict[str, str]]:
    token = access_token(root)
    account = _account(token)
    if not account_permission_id or not secrets.compare_digest(account["account_permission_id"], str(account_permission_id)):
        raise GoogleDriveError("Google Drive is connected to a different account. Disconnect and approve a new root.")
    folder = _folder(token, approved_root_id)
    root_id = folder["approved_root_id"]
    query = f"'{root_id}' in parents and trashed = false"
    fields = "files(id,name,mimeType,modifiedTime,trashed)"
    params = {"q": query, "pageSize": str(MAX_ROOT_CHILDREN), "orderBy": "folder,name", "fields": fields, "spaces": "drive", "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
    payload = _get_json(f"{DRIVE_API}/files?{urlencode(params)}", token)
    children: list[dict[str, str]] = []
    for item in payload.get("files") or []:
        mime_type = str(item.get("mimeType") or "")
        if item.get("trashed") or mime_type == SHORTCUT_MIME_TYPE:
            continue
        children.append({
            "id": _safe_id(str(item.get("id") or "")),
            "name": str(item.get("name") or "Untitled")[:300],
            "mime_type": mime_type[:200],
            "kind": "folder" if mime_type == FOLDER_MIME_TYPE else "file",
            "modified_time": str(item.get("modifiedTime") or "")[:40],
        })
    return children[:MAX_ROOT_CHILDREN]


def disconnect(root: Path) -> None:
    global _access_token, _access_expires_at
    _access_token = None
    _access_expires_at = 0.0
    path = token_path(root)
    if path.exists():
        path.unlink()
