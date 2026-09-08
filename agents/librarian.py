from __future__ import annotations

import re
from typing import Any


def _text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _tokens(query: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) >= 2]


def _field_score(query: str, tokens: list[str], value: Any, *, phrase: int, token: int) -> int:
    text = _text(value)
    if not text:
        return 0
    score = phrase if query and query in text else 0
    score += sum(token for item in tokens if item in text)
    return score




def _excerpt(text: Any, query: str, tokens: list[str], limit: int = 360) -> str:
    source = " ".join(str(text or "").split())
    if not source:
        return ""
    lower = source.lower()
    positions = [p for p in [lower.find(query)] + [lower.find(t) for t in tokens] if p >= 0]
    start = max(0, (min(positions) if positions else 0) - 110)
    end = min(len(source), start + limit)
    excerpt = source[start:end].strip()
    if start > 0:
        excerpt = "…" + excerpt
    if end < len(source):
        excerpt += "…"
    return excerpt

def search_trusted_library(
    query: str,
    collections: list[dict[str, Any]],
    materials: list[dict[str, Any]],
    *,
    collection_limit: int = 8,
    material_limit: int = 16,
) -> dict[str, Any]:
    """Rank trusted Library metadata plus locally extracted trusted document text.

    This module intentionally has no AI-service or network imports. Incoming Materials
    are never supplied to this function, so quarantined files cannot influence results.
    """
    clean_query = " ".join(str(query or "").split()).strip()[:300]
    if not clean_query:
        raise ValueError("A Librarian question or search phrase is required.")

    q = clean_query.lower()
    tokens = _tokens(clean_query)

    collection_scores: dict[int, int] = {}
    ranked_collections: list[dict[str, Any]] = []
    for row in collections:
        if str(row.get("status") or "") != "Active":
            continue
        score = 0
        score += _field_score(q, tokens, row.get("title"), phrase=120, token=20)
        score += _field_score(q, tokens, row.get("subject"), phrase=70, token=12)
        score += _field_score(q, tokens, row.get("description"), phrase=45, token=7)
        score += _field_score(q, tokens, row.get("collection_type"), phrase=25, token=4)
        if score <= 0:
            continue
        item = dict(row)
        item["librarian_score"] = score
        collection_scores[int(row["id"])] = score
        ranked_collections.append(item)

    ranked_collections.sort(
        key=lambda item: (-int(item["librarian_score"]), _text(item.get("title")), int(item.get("id") or 0))
    )

    ranked_materials: list[dict[str, Any]] = []
    for row in materials:
        if str(row.get("status") or "") != "Cataloged":
            continue
        collection_id = int(row.get("collection_id") or 0)
        parent_score = collection_scores.get(collection_id, 0)
        score = 0
        score += _field_score(q, tokens, row.get("title"), phrase=110, token=20)
        score += _field_score(q, tokens, row.get("material_type"), phrase=35, token=6)
        score += _field_score(q, tokens, row.get("edition_label"), phrase=25, token=5)
        score += _field_score(q, tokens, row.get("notes"), phrase=35, token=6)
        score += _field_score(q, tokens, row.get("collection_title"), phrase=80, token=14)
        score += _field_score(q, tokens, row.get("subject"), phrase=45, token=8)
        content_score = _field_score(q, tokens, row.get("indexed_text"), phrase=95, token=11)
        score += content_score
        if parent_score:
            # Return the trusted contents of a matching collection even when an
            # individual filename/title does not repeat the collection topic.
            score += min(55, max(15, parent_score // 3))
        if score <= 0:
            continue
        item = dict(row)
        indexed_text = item.pop("indexed_text", "")
        item["librarian_score"] = score
        item["content_indexed"] = bool(indexed_text)
        item["content_match_excerpt"] = _excerpt(indexed_text, q, tokens) if content_score > 0 else ""
        ranked_materials.append(item)

    ranked_materials.sort(
        key=lambda item: (-int(item["librarian_score"]), _text(item.get("title")), int(item.get("id") or 0))
    )

    found_collections = ranked_collections[: max(1, min(int(collection_limit), 25))]
    found_materials = ranked_materials[: max(1, min(int(material_limit), 50))]
    best = max(
        [int(item["librarian_score"]) for item in found_collections + found_materials] or [0]
    )
    confidence = "high" if best >= 100 else "medium" if best >= 45 else "low" if best else "none"
    found = bool(found_collections or found_materials)

    return {
        "status": "found" if found else "not_found",
        "query": clean_query,
        "confidence": confidence,
        "collections": found_collections,
        "materials": found_materials,
        "collection_count": len(found_collections),
        "material_count": len(found_materials),
        "external_research_recommended": not found or confidence == "low",
        "message": (
            "Trusted Library material found. Review these Mavis Institute holdings before requesting outside research."
            if found
            else "The trusted Library does not contain a useful match. External Research is recommended if you want to continue."
        ),
        "local_only": True,
        "trusted_library_only": True,
        "incoming_materials_excluded": True,
        "web_access": False,
        "additional_ai_calls": 0,
    }
