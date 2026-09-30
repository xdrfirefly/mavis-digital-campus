from __future__ import annotations

import secrets
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any

from google_drive_provider import (
    MAX_DOWNLOAD_BYTES,
    MAX_NATIVE_EXPORT_BYTES,
    GoogleDriveError,
    begin_selection_authorization,
    complete_selection_authorization,
    download_approved_item,
    inspect_approved_item_ancestry,
)
from library_intake import IncomingFileStager, LibraryIntakeError, register_staged_incoming


MAX_DRIVE_SELECTION_FILES = 20
MAX_DRIVE_BATCH_BYTES = 500 * 1024 * 1024
REVIEW_TTL_SECONDS = 30 * 60
COPY_CHUNK_BYTES = 64 * 1024


class DriveLibraryImportError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class DriveLibraryWorkflow:
    """Ephemeral, framework-neutral Drive selection and snapshot reviews."""

    def __init__(self) -> None:
        self._reviews: dict[str, dict[str, Any]] = {}
        self._selections: dict[str, dict[str, Any]] = {}

    def _purge(self) -> None:
        cutoff = time.time() - REVIEW_TTL_SECONDS
        self._reviews = {key: value for key, value in self._reviews.items() if value["created_at"] >= cutoff}
        self._selections = {key: value for key, value in self._selections.items() if value["created_at"] >= cutoff}

    @staticmethod
    def _validated_item(inspection: dict[str, Any]) -> dict[str, Any]:
        item = dict(inspection.get("item") or {})
        if item.get("kind") != "file":
            raise DriveLibraryImportError("folder_as_file", "Google Drive folders cannot be imported as files.")
        if not item.get("can_download"):
            raise DriveLibraryImportError("download_disabled", "Google Drive does not permit this file to be downloaded.")
        download_kind = str(item.get("download_kind") or "")
        if download_kind == "unsupported":
            raise DriveLibraryImportError(
                "unsupported_native_type", "This Google-native file type is not supported for Library import."
            )
        if download_kind not in {"blob", "export"}:
            raise DriveLibraryImportError("unsupported_file", "This Google Drive item cannot be imported as a file.")
        return item

    @staticmethod
    def _review_status(items: list[dict[str, Any]]) -> str:
        if any(item["status"] == "rejected" for item in items):
            return "rejected"
        if any(item["status"] == "additional_folder_approval_required" for item in items):
            return "additional_folder_approval_required"
        return "ready"

    @staticmethod
    def _public_item(item: dict[str, Any]) -> dict[str, Any]:
        metadata = item.get("metadata") or {}
        return {
            "item_key": item["item_key"],
            "name": str(metadata.get("name") or "Unavailable item"),
            "local_name": str(metadata.get("local_name") or metadata.get("name") or "Unavailable item"),
            "mime_type": str(metadata.get("mime_type") or ""),
            "size_bytes": metadata.get("size_bytes"),
            "download_kind": str(metadata.get("download_kind") or ""),
            "export_mime_type": str(metadata.get("export_mime_type") or ""),
            "export_extension": str(metadata.get("export_extension") or ""),
            "status": item["status"],
            "ancestry_verified": item["status"] == "ready",
            "additional_folder_approval_required": item["status"] == "additional_folder_approval_required",
            "message": item.get("message") or "",
        }

    def _public_review(self, review: dict[str, Any]) -> dict[str, Any]:
        items = [self._public_item(item) for item in review["items"]]
        return {
            "review_id": review["review_id"],
            "status": self._review_status(review["items"]),
            "items": items,
            "count": len(items),
            "ready_count": sum(item["status"] == "ready" for item in review["items"]),
            "requires_human_confirmation": True,
            "quarantined": True,
            "local_snapshot": True,
            "synchronized": False,
            "drive_writeback": False,
            "rose_searchable": False,
        }

    def _inspect_item(
        self,
        *,
        root: Path,
        approved_root_id: str,
        account_permission_id: str,
        item_id: str,
        item_key: str | None = None,
    ) -> dict[str, Any]:
        key = item_key or secrets.token_urlsafe(18)
        try:
            inspection = inspect_approved_item_ancestry(
                root,
                approved_root_id=approved_root_id,
                account_permission_id=account_permission_id,
                item_id=item_id,
            )
            metadata = self._validated_item(inspection)
            if inspection["status"] == "verified":
                return {
                    "item_key": key,
                    "external_id": item_id,
                    "metadata": metadata,
                    "status": "ready",
                    "required_parent_id": "",
                    "message": "Authoritative ancestry reaches the approved Drive root.",
                }
            return {
                "item_key": key,
                "external_id": item_id,
                "metadata": metadata,
                "status": "additional_folder_approval_required",
                "required_parent_id": str(inspection["required_parent_id"]),
                "message": "Additional containing-folder approval is required before ancestry can be verified.",
            }
        except (GoogleDriveError, DriveLibraryImportError) as exc:
            return {
                "item_key": key,
                "external_id": item_id,
                "metadata": {},
                "status": "rejected",
                "required_parent_id": "",
                "message": str(exc),
            }

    def create_review(
        self,
        *,
        root: Path,
        approved_root_id: str,
        account_permission_id: str,
        item_ids: list[str],
    ) -> dict[str, Any]:
        self._purge()
        selected = [str(item_id or "").strip() for item_id in item_ids if str(item_id or "").strip()]
        if not selected:
            raise DriveLibraryImportError("empty_selection", "Select at least one Google Drive file.")
        if len(selected) > MAX_DRIVE_SELECTION_FILES:
            raise DriveLibraryImportError(
                "too_many_files", f"Select no more than {MAX_DRIVE_SELECTION_FILES} Google Drive files per batch."
            )
        if len(set(selected)) != len(selected):
            raise DriveLibraryImportError("duplicate_selection", "The Google Drive selection contains duplicate files.")
        items = [
            self._inspect_item(
                root=Path(root),
                approved_root_id=approved_root_id,
                account_permission_id=account_permission_id,
                item_id=item_id,
            )
            for item_id in selected
        ]
        known_blob_bytes = sum(
            int(item["metadata"].get("size_bytes") or 0)
            for item in items
            if item["status"] != "rejected" and item["metadata"].get("download_kind") == "blob"
        )
        if known_blob_bytes > MAX_DRIVE_BATCH_BYTES:
            raise DriveLibraryImportError("batch_too_large", "The selected Drive files exceed the 500 MB batch limit.")
        review_id = secrets.token_urlsafe(24)
        review = {
            "review_id": review_id,
            "created_at": time.time(),
            "approved_root_id": approved_root_id,
            "account_permission_id": account_permission_id,
            "items": items,
            "imported": False,
        }
        self._reviews[review_id] = review
        return self._public_review(review)

    def get_review(self, review_id: str) -> dict[str, Any]:
        self._purge()
        review = self._reviews.get(str(review_id or ""))
        if not review:
            raise DriveLibraryImportError("review_missing", "The Drive import review expired or was not found.")
        return self._public_review(review)

    def start_file_selection(
        self,
        *,
        root: Path,
        redirect_uri: str,
        approved_root_id: str,
        account_permission_id: str,
    ) -> dict[str, str]:
        self._purge()
        oauth = begin_selection_authorization(
            redirect_uri, selection_kind="file", max_items=MAX_DRIVE_SELECTION_FILES
        )
        selection_id = secrets.token_urlsafe(24)
        context = {
            "selection_id": selection_id,
            "created_at": time.time(),
            "kind": "file",
            "root": Path(root),
            "approved_root_id": approved_root_id,
            "account_permission_id": account_permission_id,
            "status": "pending",
        }
        self._selections[oauth["state"]] = context
        self._selections[selection_id] = context
        return {"selection_id": selection_id, "authorization_url": oauth["authorization_url"]}

    def start_parent_selection(
        self,
        *,
        root: Path,
        redirect_uri: str,
        review_id: str,
        item_key: str,
    ) -> dict[str, str]:
        self._purge()
        review = self._reviews.get(str(review_id or ""))
        if not review:
            raise DriveLibraryImportError("review_missing", "The Drive import review expired or was not found.")
        item = next((entry for entry in review["items"] if entry["item_key"] == item_key), None)
        if not item or item["status"] != "additional_folder_approval_required":
            raise DriveLibraryImportError("folder_not_required", "This item does not require another folder approval.")
        oauth = begin_selection_authorization(redirect_uri, selection_kind="folder", max_items=1)
        selection_id = secrets.token_urlsafe(24)
        context = {
            "selection_id": selection_id,
            "created_at": time.time(),
            "kind": "folder",
            "root": Path(root),
            "approved_root_id": review["approved_root_id"],
            "account_permission_id": review["account_permission_id"],
            "review_id": review_id,
            "item_key": item_key,
            "required_parent_id": item["required_parent_id"],
            "status": "pending",
        }
        self._selections[oauth["state"]] = context
        self._selections[selection_id] = context
        return {"selection_id": selection_id, "authorization_url": oauth["authorization_url"]}

    def complete_authorization(
        self,
        *,
        state: str,
        code: str,
        redirect_uri: str,
        picked_file_ids: str,
        current_approved_root_id: str,
        current_account_permission_id: str,
    ) -> dict[str, Any]:
        self._purge()
        context = self._selections.pop(str(state or ""), None)
        if not context:
            raise DriveLibraryImportError("selection_missing", "The Drive selection expired or was not found.")
        try:
            if not secrets.compare_digest(context["approved_root_id"], str(current_approved_root_id)) or not secrets.compare_digest(
                context["account_permission_id"], str(current_account_permission_id)
            ):
                raise DriveLibraryImportError(
                    "binding_changed", "The approved Drive binding changed; start a new selection."
                )
            completed = complete_selection_authorization(
                context["root"],
                state=state,
                code=code,
                redirect_uri=redirect_uri,
                picked_file_ids=picked_file_ids,
                approved_root_id=context["approved_root_id"],
                account_permission_id=context["account_permission_id"],
            )
            selected_ids = list(completed["selected_ids"])
            if context["kind"] == "file":
                review = self.create_review(
                    root=context["root"],
                    approved_root_id=context["approved_root_id"],
                    account_permission_id=context["account_permission_id"],
                    item_ids=selected_ids,
                )
            else:
                if len(selected_ids) != 1 or not secrets.compare_digest(
                    selected_ids[0], context["required_parent_id"]
                ):
                    raise DriveLibraryImportError(
                        "wrong_parent_folder", "Select the exact containing folder requested by the authoritative parent chain."
                    )
                review_record = self._reviews.get(context["review_id"])
                if not review_record:
                    raise DriveLibraryImportError("review_missing", "The Drive import review expired or was not found.")
                inspection = inspect_approved_item_ancestry(
                    context["root"],
                    approved_root_id=context["approved_root_id"],
                    account_permission_id=context["account_permission_id"],
                    item_id=selected_ids[0],
                )
                if (inspection.get("item") or {}).get("kind") != "folder":
                    raise DriveLibraryImportError("parent_not_folder", "The selected containing item is not a folder.")
                item = next(
                    entry for entry in review_record["items"] if entry["item_key"] == context["item_key"]
                )
                replacement = self._inspect_item(
                    root=context["root"],
                    approved_root_id=context["approved_root_id"],
                    account_permission_id=context["account_permission_id"],
                    item_id=item["external_id"],
                    item_key=item["item_key"],
                )
                review_record["items"][review_record["items"].index(item)] = replacement
                review = self._public_review(review_record)
            context["status"] = "complete"
            context["review"] = review
        except Exception as exc:
            context["status"] = "error"
            context["error"] = str(exc)
            self._selections[context["selection_id"]] = context
            raise
        self._selections[context["selection_id"]] = context
        return {"selection_id": context["selection_id"], "review": review}

    def selection_status(self, selection_id: str) -> dict[str, Any]:
        self._purge()
        context = self._selections.get(str(selection_id or ""))
        if not context:
            raise DriveLibraryImportError("selection_missing", "The Drive selection expired or was not found.")
        result: dict[str, Any] = {"selection_id": context["selection_id"], "status": context["status"]}
        if context.get("review"):
            result["review"] = context["review"]
        if context.get("error"):
            result["error"] = context["error"]
        return result

    def import_review(
        self,
        conn: sqlite3.Connection,
        *,
        review_id: str,
        root: Path,
        inbox_root: Path,
        database_root: Path,
        approved_root_id: str,
        account_permission_id: str,
        received_at: str,
        confirmed: bool,
    ) -> dict[str, Any]:
        self._purge()
        if not confirmed:
            raise DriveLibraryImportError("confirmation_required", "Confirm the Drive snapshot import before continuing.")
        review = self._reviews.get(str(review_id or ""))
        if not review or review["imported"]:
            raise DriveLibraryImportError("review_missing", "The Drive import review expired or was already used.")
        if not secrets.compare_digest(review["approved_root_id"], str(approved_root_id)) or not secrets.compare_digest(
            review["account_permission_id"], str(account_permission_id)
        ):
            raise DriveLibraryImportError("binding_changed", "The approved Drive binding changed; start a new selection.")
        if self._review_status(review["items"]) != "ready":
            raise DriveLibraryImportError("review_not_ready", "Every selected file must pass ancestry verification first.")

        results: list[dict[str, Any]] = []
        batch_bytes = 0
        with tempfile.TemporaryDirectory(prefix="mdc-drive-import-") as temp_name:
            temp_root = Path(temp_name)
            for position, review_item in enumerate(review["items"]):
                item_id = review_item["external_id"]
                destination = temp_root / f"{position:02d}.snapshot"
                try:
                    inspection = inspect_approved_item_ancestry(
                        root,
                        approved_root_id=approved_root_id,
                        account_permission_id=account_permission_id,
                        item_id=item_id,
                    )
                    if inspection.get("status") != "verified":
                        raise DriveLibraryImportError(
                            "ancestry_changed", "Ancestry is no longer fully verified."
                        )
                    metadata = self._validated_item(inspection)
                    per_file_limit = (
                        MAX_NATIVE_EXPORT_BYTES if metadata["download_kind"] == "export" else MAX_DOWNLOAD_BYTES
                    )
                    downloaded = download_approved_item(
                        root,
                        approved_root_id=approved_root_id,
                        account_permission_id=account_permission_id,
                        item_id=item_id,
                        destination=destination,
                        max_bytes=per_file_limit,
                    )
                    downloaded_size = int(downloaded["size_bytes"])
                    if batch_bytes + downloaded_size > MAX_DRIVE_BATCH_BYTES:
                        raise DriveLibraryImportError(
                            "batch_too_large", "The 500 MB Drive import batch limit was reached."
                        )
                    batch_bytes += downloaded_size
                    with IncomingFileStager(
                        Path(inbox_root), filename=metadata["local_name"], max_bytes=per_file_limit
                    ) as stager:
                        with destination.open("rb") as source:
                            while True:
                                chunk = source.read(COPY_CHUNK_BYTES)
                                if not chunk:
                                    break
                                stager.write(chunk)
                        staged = stager.finish()
                    stored_mime = metadata.get("export_mime_type") or metadata["mime_type"]
                    registered = register_staged_incoming(
                        conn,
                        staged,
                        database_root=Path(database_root),
                        mime_type=stored_mime,
                        source_kind="google_drive",
                        created_by="Human",
                        received_at=received_at,
                        notes="Google Drive snapshot; quarantined pending human catalog approval.",
                        source_external_id=item_id,
                        source_external_root_id=approved_root_id,
                        source_external_modified_at=str(metadata.get("modified_time") or ""),
                        source_external_mime_type=str(metadata.get("mime_type") or ""),
                        source_export_mime_type=str(metadata.get("export_mime_type") or ""),
                    )
                    results.append(
                        {
                            **registered,
                            "item_key": review_item["item_key"],
                            "name": metadata["name"],
                            "google_drive_snapshot": True,
                            "quarantined": True,
                            "cataloged": False,
                        }
                    )
                except (GoogleDriveError, DriveLibraryImportError, LibraryIntakeError) as exc:
                    results.append(
                        {"item_key": review_item["item_key"], "status": "rejected", "message": str(exc)}
                    )
                finally:
                    destination.unlink(missing_ok=True)
        review["imported"] = True
        return {
            "status": "complete",
            "review_id": review_id,
            "results": results,
            "total_bytes": batch_bytes,
            "quarantined": True,
            "cataloged": False,
            "rose_searchable": False,
        }
