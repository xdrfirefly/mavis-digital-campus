from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


MAX_LIBRARY_UPLOAD_BYTES = 100 * 1024 * 1024


class LibraryIntakeError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def safe_library_filename(filename: str) -> tuple[str, str]:
    raw = str(filename or "").replace("\\", "/").split("/")[-1].strip()
    if not raw or raw in {".", ".."}:
        raise LibraryIntakeError("invalid_filename", "A valid filename is required.")
    original = raw[:240]
    safe = re.sub(r"[^A-Za-z0-9._ -]+", "_", original).strip(" .")
    safe = re.sub(r"\s+", " ", safe)[:180] or "library-file"
    return original, safe


@dataclass(frozen=True)
class StagedIncomingFile:
    original_filename: str
    safe_filename: str
    temp_path: Path
    size_bytes: int
    sha256: str


class IncomingFileStager:
    """Stream one untrusted file into bounded local staging storage."""

    def __init__(self, inbox_root: Path, *, filename: str, max_bytes: int = MAX_LIBRARY_UPLOAD_BYTES):
        self.inbox_root = Path(inbox_root)
        self.original_filename, self.safe_filename = safe_library_filename(filename)
        self.max_bytes = max(1, int(max_bytes))
        self.inbox_root.mkdir(parents=True, exist_ok=True)
        self.temp_path = self.inbox_root / f".incoming-{time.time_ns()}"
        self._handle = self.temp_path.open("wb")
        self._hasher = hashlib.sha256()
        self._size = 0
        self._released = False

    def __enter__(self) -> IncomingFileStager:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if not self._released:
            self.abort()

    def write(self, chunk: bytes) -> None:
        if self._released or self._handle.closed:
            raise LibraryIntakeError("closed", "The incoming file staging stream is closed.")
        if not chunk:
            return
        next_size = self._size + len(chunk)
        if next_size > self.max_bytes:
            raise LibraryIntakeError("too_large", "Library files are limited to 100 MB each.")
        self._handle.write(chunk)
        self._hasher.update(chunk)
        self._size = next_size

    def finish(self) -> StagedIncomingFile:
        if self._released or self._handle.closed:
            raise LibraryIntakeError("closed", "The incoming file staging stream is closed.")
        if self._size <= 0:
            raise LibraryIntakeError("empty", "The uploaded file is empty.")
        self._handle.flush()
        self._handle.close()
        self._released = True
        return StagedIncomingFile(
            original_filename=self.original_filename,
            safe_filename=self.safe_filename,
            temp_path=self.temp_path,
            size_bytes=self._size,
            sha256=self._hasher.hexdigest(),
        )

    def abort(self) -> None:
        if not self._handle.closed:
            self._handle.close()
        self.temp_path.unlink(missing_ok=True)


def register_staged_incoming(
    conn: sqlite3.Connection,
    staged: StagedIncomingFile,
    *,
    database_root: Path,
    mime_type: str,
    source_kind: str,
    created_by: str,
    received_at: str,
    notes: str = "",
) -> dict[str, object]:
    """Commit staged bytes to Library quarantine with the existing SHA-256 contract."""
    final_path: Path | None = None
    moved = False
    try:
        duplicate = conn.execute(
            "SELECT id,original_filename,status FROM library_inbox WHERE sha256=?", (staged.sha256,)
        ).fetchone()
        if duplicate:
            staged.temp_path.unlink(missing_ok=True)
            return {
                "status": "duplicate",
                "inbox_id": int(duplicate["id"]),
                "original_filename": duplicate["original_filename"],
                "inbox_status": duplicate["status"],
                "sha256": staged.sha256,
            }

        final_path = staged.temp_path.parent / f"{staged.sha256[:12]}-{staged.safe_filename}"
        if final_path.exists():
            final_path = staged.temp_path.parent / f"{staged.sha256[:20]}-{staged.safe_filename}"
        relative_path = final_path.relative_to(Path(database_root)).as_posix()
        staged.temp_path.replace(final_path)
        moved = True
        cur = conn.execute(
            """
            INSERT INTO library_inbox(original_filename,stored_filename,relative_path,mime_type,size_bytes,sha256,status,source_kind,notes,created_by,received_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                staged.original_filename,
                final_path.name,
                relative_path,
                str(mime_type or "application/octet-stream")[:200],
                staged.size_bytes,
                staged.sha256,
                "Incoming",
                str(source_kind or "upload")[:100],
                str(notes or "")[:2400],
                str(created_by or "Human")[:160],
                received_at,
                received_at,
            ),
        )
    except ValueError as exc:
        staged.temp_path.unlink(missing_ok=True)
        if moved and final_path is not None:
            final_path.unlink(missing_ok=True)
        raise LibraryIntakeError("storage_boundary", "Library inbox storage is outside the Campus data root.") from exc
    except Exception:
        staged.temp_path.unlink(missing_ok=True)
        if moved and final_path is not None:
            final_path.unlink(missing_ok=True)
        raise
    assert final_path is not None
    return {
        "status": "received",
        "inbox_id": int(cur.lastrowid),
        "original_filename": staged.original_filename,
        "stored_filename": final_path.name,
        "relative_path": relative_path,
        "size_bytes": staged.size_bytes,
        "sha256": staged.sha256,
    }
