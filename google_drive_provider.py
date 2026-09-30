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
MAX_FOLDER_CHILDREN = 100
MAX_PARENT_DEPTH = 32
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
MAX_NATIVE_EXPORT_BYTES = 10 * 1024 * 1024
DOWNLOAD_CHUNK_BYTES = 64 * 1024

GOOGLE_NATIVE_MIME_PREFIX = "application/vnd.google-apps."
GOOGLE_DOC_MIME_TYPE = f"{GOOGLE_NATIVE_MIME_PREFIX}document"
GOOGLE_SHEET_MIME_TYPE = f"{GOOGLE_NATIVE_MIME_PREFIX}spreadsheet"
GOOGLE_SLIDE_MIME_TYPE = f"{GOOGLE_NATIVE_MIME_PREFIX}presentation"
GOOGLE_DRAWING_MIME_TYPE = f"{GOOGLE_NATIVE_MIME_PREFIX}drawing"

_NATIVE_EXPORT_FORMATS = {
    GOOGLE_DOC_MIME_TYPE: {
        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "extension": ".docx",
    },
    GOOGLE_SHEET_MIME_TYPE: {
        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "extension": ".xlsx",
    },
    GOOGLE_SLIDE_MIME_TYPE: {
        "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "extension": ".pptx",
    },
    GOOGLE_DRAWING_MIME_TYPE: {"mime_type": "application/pdf", "extension": ".pdf"},
}

_ITEM_FIELDS = (
    "id,name,mimeType,parents,trashed,size,modifiedTime,md5Checksum,"
    "capabilities(canDownload,canListChildren),shortcutDetails(targetId,targetMimeType)"
)

_pending: dict[str, tuple[str, float, str]] = {}
_selection_pending: dict[str, tuple[str, float, str, str, int]] = {}
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
        try:
            payload = json.loads(exc.read(64_000).decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        if str(payload.get("error") or "") == "invalid_grant":
            raise GoogleDriveError(
                "Google Drive authorization has expired or been revoked. Disconnect and reconnect the approved root."
            ) from exc
        raise GoogleDriveError(f"Google Drive authorization returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise GoogleDriveError("Google Drive could not be reached. Check the internet connection and try again.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GoogleDriveError("Google returned an authorization response that could not be read safely.") from exc


def _get_json(url: str, token: str, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    request = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": "Mavis-Digital-Campus/0.9.9"})
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


def begin_selection_authorization(
    redirect_uri: str, *, selection_kind: str, max_items: int = 1
) -> dict[str, str]:
    """Begin a file/folder grant without changing the approved-root binding."""
    client_id, _ = credentials()
    if not client_id:
        raise GoogleDriveError("Google Drive OAuth credentials are not configured in .env.")
    kind = str(selection_kind or "").strip().lower()
    if kind not in {"file", "folder"}:
        raise GoogleDriveError("Google Drive selection must request files or folders.")
    bounded_items = 1 if kind == "folder" else max(1, min(int(max_items or 1), 20))
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    _selection_pending[state] = (verifier, time.time() + 600, redirect_uri, kind, bounded_items)
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
        "allow_folder_selection": "true" if kind == "folder" else "false",
        "allow_multiple": "true" if bounded_items > 1 else "false",
    }
    return {"authorization_url": f"{AUTH_URL}?{urlencode(params)}", "state": state}


def _safe_id(value: str) -> str:
    clean = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,}", clean):
        raise GoogleDriveError("Google Drive returned an invalid resource selection.")
    return clean


def native_export_format(mime_type: str) -> dict[str, str]:
    mapped = _NATIVE_EXPORT_FORMATS.get(str(mime_type or "").strip())
    if not mapped:
        raise GoogleDriveError("This Google-native file type is not supported for local export.")
    return dict(mapped)


def _account(token: str) -> dict[str, str]:
    payload = _get_json(f"{DRIVE_API}/about?{urlencode({'fields':'user(permissionId)'})}", token)
    permission_id = str((payload.get("user") or {}).get("permissionId") or "").strip()
    if not permission_id:
        raise GoogleDriveError("Google Drive did not return a stable account identity.")
    return {"account_permission_id": permission_id}


def _item_payload(token: str, item_id: str, *, root_item: bool = False) -> dict[str, Any]:
    item_id = _safe_id(item_id)
    params = {"fields": _ITEM_FIELDS, "supportsAllDrives": "true"}
    try:
        payload = _get_json(f"{DRIVE_API}/files/{quote(item_id, safe='')}?{urlencode(params)}", token)
    except GoogleDriveError as exc:
        if "missing or inaccessible" in str(exc):
            label = "approved Google Drive root" if root_item else "requested Google Drive item"
            raise GoogleDriveError(f"The {label} is missing or inaccessible.") from exc
        raise
    returned_id = _safe_id(str(payload.get("id") or ""))
    if not secrets.compare_digest(returned_id, item_id):
        raise GoogleDriveError("Google Drive returned a different item than the one requested.")
    if payload.get("trashed"):
        label = "approved Google Drive root" if root_item else "requested Google Drive item"
        raise GoogleDriveError(f"The {label} is in the trash.")
    if str(payload.get("mimeType") or "") == SHORTCUT_MIME_TYPE:
        raise GoogleDriveError("Google Drive shortcuts are not allowed inside the approved-root boundary.")
    return payload


def _normalized_item(payload: dict[str, Any], *, inside_approved_root: bool) -> dict[str, Any]:
    item_id = _safe_id(str(payload.get("id") or ""))
    mime_type = str(payload.get("mimeType") or "")[:200]
    name = str(payload.get("name") or "Untitled")[:300]
    capabilities = payload.get("capabilities") or {}
    parents = [_safe_id(str(value)) for value in (payload.get("parents") or [])]
    size_value = payload.get("size")
    try:
        size_bytes = int(size_value) if size_value not in (None, "") else None
    except (TypeError, ValueError):
        size_bytes = None

    export = _NATIVE_EXPORT_FORMATS.get(mime_type)
    if mime_type == FOLDER_MIME_TYPE:
        kind = "folder"
        download_kind = "none"
    elif export:
        kind = "file"
        download_kind = "export"
    elif mime_type.startswith(GOOGLE_NATIVE_MIME_PREFIX):
        kind = "file"
        download_kind = "unsupported"
    else:
        kind = "file"
        download_kind = "blob"

    extension = str(export.get("extension") or "") if export else ""
    local_name = name if not extension or name.lower().endswith(extension) else name + extension
    return {
        "id": item_id,
        "name": name,
        "local_name": local_name,
        "mime_type": mime_type,
        "kind": kind,
        "parents": parents,
        "modified_time": str(payload.get("modifiedTime") or "")[:40],
        "size_bytes": size_bytes,
        "md5_checksum": str(payload.get("md5Checksum") or "")[:64],
        "can_download": bool(capabilities.get("canDownload")),
        "can_list_children": bool(capabilities.get("canListChildren")),
        "download_kind": download_kind,
        "export_mime_type": str(export.get("mime_type") or "") if export else "",
        "export_extension": extension,
        "inside_approved_root": bool(inside_approved_root),
    }


def _folder(token: str, folder_id: str) -> dict[str, str]:
    folder_id = _safe_id(folder_id)
    payload = _item_payload(token, folder_id, root_item=True)
    mime_type = str(payload.get("mimeType") or "")
    if mime_type != FOLDER_MIME_TYPE:
        raise GoogleDriveError("The selected Google Drive item is not a folder.")
    if not bool((payload.get("capabilities") or {}).get("canListChildren")):
        raise GoogleDriveError("The selected Google Drive folder cannot be listed by this account.")
    returned_id = _safe_id(str(payload.get("id") or ""))
    if not secrets.compare_digest(returned_id, folder_id):
        raise GoogleDriveError("Google Drive returned a different root than the one approved.")
    return {"approved_root_id": returned_id, "approved_root_name": str(payload.get("name") or "Google Drive folder")[:300]}


def _bound_context(
    root: Path, *, approved_root_id: str, account_permission_id: str
) -> tuple[str, dict[str, str], dict[str, str]]:
    token = access_token(root)
    account = _account(token)
    if not account_permission_id or not secrets.compare_digest(account["account_permission_id"], str(account_permission_id)):
        raise GoogleDriveError("Google Drive is connected to a different account. Disconnect and approve a new root.")
    folder = _folder(token, approved_root_id)
    return token, folder, account


def _verify_payload_descendant(token: str, payload: dict[str, Any], approved_root_id: str) -> None:
    root_id = _safe_id(approved_root_id)
    current_id = _safe_id(str(payload.get("id") or ""))
    if secrets.compare_digest(current_id, root_id):
        return
    current = payload
    visited = {current_id}
    for _depth in range(MAX_PARENT_DEPTH):
        parents = [_safe_id(str(value)) for value in (current.get("parents") or [])]
        if len(parents) != 1:
            raise GoogleDriveError("The requested Google Drive item is not a verified descendant of the approved root.")
        parent_id = parents[0]
        if secrets.compare_digest(parent_id, root_id):
            return
        if parent_id in visited:
            raise GoogleDriveError("Google Drive returned a parent cycle while verifying the approved-root boundary.")
        visited.add(parent_id)
        current = _item_payload(token, parent_id)
        if str(current.get("mimeType") or "") != FOLDER_MIME_TYPE:
            raise GoogleDriveError("The requested Google Drive item's parent chain is invalid.")
    raise GoogleDriveError(f"Google Drive parent depth exceeds the approved limit of {MAX_PARENT_DEPTH}.")


def _approved_item_context(
    root: Path,
    *,
    approved_root_id: str,
    account_permission_id: str,
    item_id: str,
) -> tuple[str, dict[str, Any]]:
    token, folder, _ = _bound_context(
        root, approved_root_id=approved_root_id, account_permission_id=account_permission_id
    )
    root_id = folder["approved_root_id"]
    payload = _item_payload(token, item_id, root_item=secrets.compare_digest(_safe_id(item_id), root_id))
    _verify_payload_descendant(token, payload, root_id)
    return token, _normalized_item(payload, inside_approved_root=True)


def inspect_approved_item_ancestry(
    root: Path,
    *,
    approved_root_id: str,
    account_permission_id: str,
    item_id: str,
) -> dict[str, Any]:
    """Inspect an item using only authoritative parent metadata.

    A file grant can reveal an authoritative parent ID without granting access to
    that folder. That state is returned explicitly so the caller can request a
    separate human folder approval. Fully visible chains outside the approved
    root still fail closed.
    """
    token, folder, _ = _bound_context(
        root, approved_root_id=approved_root_id, account_permission_id=account_permission_id
    )
    root_id = folder["approved_root_id"]
    payload = _item_payload(token, item_id, root_item=secrets.compare_digest(_safe_id(item_id), root_id))
    item = _normalized_item(payload, inside_approved_root=False)
    chain: list[dict[str, Any]] = []
    current = payload
    visited: set[str] = set()
    for _depth in range(MAX_PARENT_DEPTH + 1):
        current_id = _safe_id(str(current.get("id") or ""))
        if current_id in visited:
            raise GoogleDriveError("Google Drive returned a parent cycle while verifying the approved-root boundary.")
        visited.add(current_id)
        chain.append(_normalized_item(current, inside_approved_root=secrets.compare_digest(current_id, root_id)))
        if secrets.compare_digest(current_id, root_id):
            verified_item = {**item, "inside_approved_root": True}
            return {"status": "verified", "verified": True, "item": verified_item, "chain": chain}
        parents = [_safe_id(str(value)) for value in (current.get("parents") or [])]
        if len(parents) != 1:
            raise GoogleDriveError("The requested Google Drive item is not a verified descendant of the approved root.")
        parent_id = parents[0]
        try:
            parent = _item_payload(token, parent_id)
        except GoogleDriveError as exc:
            if "missing or inaccessible" in str(exc):
                return {
                    "status": "additional_folder_approval_required",
                    "verified": False,
                    "item": item,
                    "chain": chain,
                    "required_parent_id": parent_id,
                }
            raise
        if str(parent.get("mimeType") or "") != FOLDER_MIME_TYPE:
            raise GoogleDriveError("The requested Google Drive item's parent chain is invalid.")
        current = parent
    raise GoogleDriveError(f"Google Drive parent depth exceeds the approved limit of {MAX_PARENT_DEPTH}.")


def verify_item_in_approved_root(
    root: Path,
    *,
    approved_root_id: str,
    account_permission_id: str,
    item_id: str,
) -> dict[str, Any]:
    _, item = _approved_item_context(
        root,
        approved_root_id=approved_root_id,
        account_permission_id=account_permission_id,
        item_id=item_id,
    )
    return item


def get_approved_item_metadata(
    root: Path,
    *,
    approved_root_id: str,
    account_permission_id: str,
    item_id: str,
) -> dict[str, Any]:
    return verify_item_in_approved_root(
        root,
        approved_root_id=approved_root_id,
        account_permission_id=account_permission_id,
        item_id=item_id,
    )


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


def complete_selection_authorization(
    root: Path,
    *,
    state: str,
    code: str,
    redirect_uri: str,
    picked_file_ids: str,
    approved_root_id: str,
    account_permission_id: str,
) -> dict[str, Any]:
    """Complete an explicit file/folder grant without touching root metadata."""
    pending = _selection_pending.pop(state, None)
    if not pending or pending[1] < time.time() or not secrets.compare_digest(pending[2], redirect_uri):
        raise GoogleDriveError("The Google Drive selection request expired or could not be verified.")
    selection_kind, max_items = pending[3], pending[4]
    selected = [_safe_id(item.strip()) for item in str(picked_file_ids or "").split(",") if item.strip()]
    if not selected:
        raise GoogleDriveError("Select at least one Google Drive item.")
    if len(selected) > max_items:
        raise GoogleDriveError(f"Select no more than {max_items} Google Drive item(s).")
    if len(set(selected)) != len(selected):
        raise GoogleDriveError("Google Drive returned a duplicate item selection.")
    client_id, client_secret = credentials()
    values = {
        "client_id": client_id,
        "code": code,
        "code_verifier": pending[0],
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    if client_secret:
        values["client_secret"] = client_secret
    result = _post_form(TOKEN_URL, values)
    refresh_token = str(result.get("refresh_token") or "").strip()
    access = str(result.get("access_token") or "").strip()
    if not refresh_token or not access:
        raise GoogleDriveError("Google did not return offline Drive authorization. Try the selection again.")
    account = _account(access)
    if not account_permission_id or not secrets.compare_digest(
        account["account_permission_id"], str(account_permission_id)
    ):
        raise GoogleDriveError("Google Drive selection used a different account. The existing connection was preserved.")
    _folder(access, approved_root_id)
    path = token_path(root)
    temp_path = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        temp_path.write_text(json.dumps({"refresh_token": refresh_token}), encoding="utf-8")
        try:
            temp_path.chmod(0o600)
        except OSError:
            pass
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)
    _remember_access(result)
    return {"selected_ids": selected, "selection_kind": selection_kind}


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
    _, folder, account = _bound_context(
        root, approved_root_id=approved_root_id, account_permission_id=account_permission_id
    )
    return {**folder, **account}


def list_approved_folder_children(
    root: Path,
    *,
    approved_root_id: str,
    account_permission_id: str,
    folder_id: str,
    limit: int = MAX_FOLDER_CHILDREN,
) -> list[dict[str, Any]]:
    token, folder = _approved_item_context(
        root,
        approved_root_id=approved_root_id,
        account_permission_id=account_permission_id,
        item_id=folder_id,
    )
    if folder["kind"] != "folder":
        raise GoogleDriveError("The requested Google Drive item is not a folder.")
    if not folder["can_list_children"]:
        raise GoogleDriveError("The requested Google Drive folder cannot be listed by this account.")
    bounded_limit = max(1, min(int(limit or MAX_FOLDER_CHILDREN), MAX_FOLDER_CHILDREN))
    query = f"'{folder['id']}' in parents and trashed = false"
    fields = f"files({_ITEM_FIELDS})"
    params = {
        "q": query,
        "pageSize": str(bounded_limit),
        "orderBy": "folder,name",
        "fields": fields,
        "spaces": "drive",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }
    payload = _get_json(f"{DRIVE_API}/files?{urlencode(params)}", token)
    children: list[dict[str, Any]] = []
    for raw in payload.get("files") or []:
        mime_type = str(raw.get("mimeType") or "")
        if raw.get("trashed") or mime_type == SHORTCUT_MIME_TYPE:
            continue
        children.append(_normalized_item(raw, inside_approved_root=True))
        if len(children) >= bounded_limit:
            break
    return children


def list_approved_root_children(root: Path, *, approved_root_id: str, account_permission_id: str) -> list[dict[str, str]]:
    items = list_approved_folder_children(
        root,
        approved_root_id=approved_root_id,
        account_permission_id=account_permission_id,
        folder_id=approved_root_id,
        limit=MAX_ROOT_CHILDREN,
    )
    return [
        {
            "id": str(item["id"]),
            "name": str(item["name"]),
            "mime_type": str(item["mime_type"]),
            "kind": str(item["kind"]),
            "modified_time": str(item["modified_time"]),
        }
        for item in items
    ]


def _download_url(item: dict[str, Any]) -> tuple[str, int]:
    item_id = _safe_id(str(item.get("id") or ""))
    if item.get("download_kind") == "blob":
        params = {"alt": "media", "supportsAllDrives": "true"}
        return f"{DRIVE_API}/files/{quote(item_id, safe='')}?{urlencode(params)}", MAX_DOWNLOAD_BYTES
    if item.get("download_kind") == "export":
        export_mime = str(item.get("export_mime_type") or "")
        if not export_mime:
            raise GoogleDriveError("The Google-native export format is missing.")
        params = {"mimeType": export_mime}
        return f"{DRIVE_API}/files/{quote(item_id, safe='')}/export?{urlencode(params)}", MAX_NATIVE_EXPORT_BYTES
    if item.get("download_kind") == "unsupported":
        raise GoogleDriveError("This Google-native file type is not supported for local export.")
    raise GoogleDriveError("Google Drive folders cannot be downloaded as files.")


def _stream_download_to_path(
    url: str,
    token: str,
    destination: Path,
    *,
    max_bytes: int,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_name(f".{destination.name}.drive-{secrets.token_hex(8)}.tmp")
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/octet-stream",
            "User-Agent": "Mavis-Digital-Campus/0.9.9",
        },
    )
    size = 0
    hasher = hashlib.sha256()
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed Google endpoint only
            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > max_bytes:
                        raise GoogleDriveError(f"Google Drive content exceeds the {max_bytes}-byte size limit.")
                except ValueError:
                    pass
            with temp_path.open("wb") as handle:
                while True:
                    chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise GoogleDriveError(f"Google Drive content exceeds the {max_bytes}-byte size limit.")
                    handle.write(chunk)
                    hasher.update(chunk)
        temp_path.replace(destination)
    except GoogleDriveError:
        raise
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise GoogleDriveError("Google Drive does not permit this file to be downloaded.") from exc
        if exc.code == 404:
            raise GoogleDriveError("The requested Google Drive item is missing or inaccessible.") from exc
        raise GoogleDriveError(f"Google Drive download returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise GoogleDriveError("Google Drive could not be reached while downloading the selected file.") from exc
    except OSError as exc:
        raise GoogleDriveError("The Google Drive file could not be stored safely on this computer.") from exc
    finally:
        temp_path.unlink(missing_ok=True)
    return {"size_bytes": size, "sha256": hasher.hexdigest(), "destination": str(destination)}


def download_approved_item(
    root: Path,
    *,
    approved_root_id: str,
    account_permission_id: str,
    item_id: str,
    destination: Path,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> dict[str, Any]:
    token, item = _approved_item_context(
        root,
        approved_root_id=approved_root_id,
        account_permission_id=account_permission_id,
        item_id=item_id,
    )
    if not item.get("can_download"):
        raise GoogleDriveError("Google Drive does not permit this file to be downloaded.")
    url, provider_limit = _download_url(item)
    requested_limit = max(1, min(int(max_bytes or MAX_DOWNLOAD_BYTES), MAX_DOWNLOAD_BYTES))
    effective_limit = min(requested_limit, provider_limit)
    known_size = item.get("size_bytes")
    if known_size is not None and int(known_size) > effective_limit:
        raise GoogleDriveError(f"Google Drive content exceeds the {effective_limit}-byte size limit.")
    result = _stream_download_to_path(
        url, token, Path(destination), max_bytes=effective_limit, timeout=DEFAULT_TIMEOUT_SECONDS
    )
    return {
        **result,
        "id": item["id"],
        "name": item["name"],
        "local_name": item["local_name"],
        "source_mime_type": item["mime_type"],
        "download_kind": item["download_kind"],
        "export_mime_type": item.get("export_mime_type") or "",
        "inside_approved_root": True,
    }


def disconnect(root: Path) -> None:
    global _access_token, _access_expires_at
    _access_token = None
    _access_expires_at = 0.0
    path = token_path(root)
    if path.exists():
        path.unlink()
