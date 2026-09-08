from __future__ import annotations

import html
import json
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

MAX_INDEX_FILE_BYTES = 50 * 1024 * 1024
MAX_INDEX_TEXT_CHARS = 300_000


def _clean_text(value: str) -> str:
    text = html.unescape(str(value or "")).replace("\x00", " ")
    text = re.sub(r"[\t\r\f\v]+", " ", text)
    text = re.sub(r" +", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_INDEX_TEXT_CHARS]


def _xml_text(data: bytes, tags: set[str] | None = None) -> str:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return ""
    parts: list[str] = []
    for elem in root.iter():
        local = elem.tag.rsplit("}", 1)[-1]
        if tags is None or local in tags:
            if elem.text:
                parts.append(elem.text)
    return _clean_text("\n".join(parts))


def _extract_docx(path: Path) -> str:
    parts: list[str] = []
    with zipfile.ZipFile(path) as zf:
        names = [
            name for name in zf.namelist()
            if name == "word/document.xml"
            or re.fullmatch(r"word/(header|footer)\d+\.xml", name)
            or name in {"word/footnotes.xml", "word/endnotes.xml", "word/comments.xml"}
        ]
        for name in names:
            parts.append(_xml_text(zf.read(name), {"t"}))
    return _clean_text("\n\n".join(p for p in parts if p))


def _numbered_key(name: str) -> tuple[int, str]:
    match = re.search(r"(\d+)", name)
    return (int(match.group(1)) if match else 10**9, name)


def _extract_pptx(path: Path) -> str:
    parts: list[str] = []
    with zipfile.ZipFile(path) as zf:
        slide_names = sorted(
            [n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)],
            key=_numbered_key,
        )
        note_names = sorted(
            [n for n in zf.namelist() if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n)],
            key=_numbered_key,
        )
        for name in slide_names:
            text = _xml_text(zf.read(name), {"t"})
            if text:
                parts.append(text)
        for name in note_names:
            text = _xml_text(zf.read(name), {"t"})
            if text:
                parts.append("Speaker notes:\n" + text)
    return _clean_text("\n\n".join(parts))


def _extract_xlsx(path: Path) -> str:
    parts: list[str] = []
    with zipfile.ZipFile(path) as zf:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            try:
                root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in root.iter():
                    if si.tag.rsplit("}", 1)[-1] != "si":
                        continue
                    values = [e.text or "" for e in si.iter() if e.tag.rsplit("}", 1)[-1] == "t"]
                    shared.append("".join(values))
            except ET.ParseError:
                shared = []
        sheets = sorted(
            [n for n in zf.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)],
            key=_numbered_key,
        )
        for name in sheets:
            try:
                root = ET.fromstring(zf.read(name))
            except ET.ParseError:
                continue
            values: list[str] = []
            for cell in root.iter():
                if cell.tag.rsplit("}", 1)[-1] != "c":
                    continue
                cell_type = cell.attrib.get("t", "")
                value = None
                for child in cell:
                    local = child.tag.rsplit("}", 1)[-1]
                    if local == "v":
                        value = child.text or ""
                        break
                    if local == "is":
                        value = "".join(e.text or "" for e in child.iter() if e.tag.rsplit("}", 1)[-1] == "t")
                        break
                if value is None:
                    continue
                if cell_type == "s":
                    try:
                        value = shared[int(value)]
                    except (ValueError, IndexError):
                        pass
                if value:
                    values.append(value)
            if values:
                parts.append("\n".join(values))
    return _clean_text("\n\n".join(parts))


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is not installed") from exc
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            parts.append(text)
        if sum(len(p) for p in parts) >= MAX_INDEX_TEXT_CHARS:
            break
    return _clean_text("\n\n".join(parts))


def extract_library_text(path: Path, *, original_filename: str = "", mime_type: str = "") -> dict[str, Any]:
    """Extract searchable text locally. No AI, OCR, HTTP, or network access."""
    path = Path(path)
    if not path.is_file():
        return {"status": "missing", "method": "none", "text": "", "char_count": 0, "error": "Trusted Library file is missing."}
    try:
        size = path.stat().st_size
    except OSError as exc:
        return {"status": "error", "method": "none", "text": "", "char_count": 0, "error": str(exc)[:500]}
    if size > MAX_INDEX_FILE_BYTES:
        return {"status": "too_large", "method": "none", "text": "", "char_count": 0, "error": "File exceeds the 50 MB local indexing limit."}

    suffix = Path(original_filename or path.name).suffix.lower()
    method = "unsupported"
    try:
        if suffix == ".pdf" or mime_type == "application/pdf":
            method = "pypdf"
            text = _extract_pdf(path)
            if not text:
                return {"status": "needs_ocr", "method": method, "text": "", "char_count": 0, "error": "No embedded text found; scanned/image PDF OCR is intentionally deferred."}
        elif suffix == ".docx":
            method = "docx-xml"
            text = _extract_docx(path)
        elif suffix == ".pptx":
            method = "pptx-xml"
            text = _extract_pptx(path)
        elif suffix == ".xlsx":
            method = "xlsx-xml"
            text = _extract_xlsx(path)
        elif suffix in {".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".html", ".htm", ".log"} or mime_type.startswith("text/"):
            method = "plain-text"
            text = _clean_text(path.read_text(encoding="utf-8", errors="replace"))
        else:
            return {"status": "unsupported", "method": method, "text": "", "char_count": 0, "error": "This file type is not text-indexable in v0.8.6.7."}
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError, KeyError) as exc:
        return {"status": "error", "method": method, "text": "", "char_count": 0, "error": str(exc)[:500]}
    except Exception as exc:
        return {"status": "error", "method": method, "text": "", "char_count": 0, "error": f"{type(exc).__name__}: {exc}"[:500]}

    text = _clean_text(text)
    return {
        "status": "indexed" if text else "empty",
        "method": method,
        "text": text,
        "char_count": len(text),
        "error": "" if text else "No readable text was extracted.",
    }
