from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

GRANTS_GOV_SEARCH_URL = "https://api.grants.gov/v1/api/search2"
GRANTS_GOV_DETAIL_BASE = "https://www.grants.gov/search-results-detail"
DEFAULT_TIMEOUT_SECONDS = 15


class GrantDiscoveryError(RuntimeError):
    pass


def _clean_text(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _iso_date(value: Any) -> str | None:
    text = _clean_text(value, 80)
    if not text:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def search_grants_gov(keyword: str, rows: int = 20, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Search the public Grants.gov Search2 API and return a small normalized result set.

    Search2 is intentionally used because Grants.gov documents it as public and not
    requiring authentication. This function does not submit applications, create
    Grants.gov accounts, or use an AI provider.
    """
    query = _clean_text(keyword, 180)
    if not query:
        raise GrantDiscoveryError("Add a search phrase before asking Vernadette to discover grants.")
    rows = max(1, min(int(rows or 20), 40))
    payload = json.dumps({
        "rows": rows,
        "keyword": query,
        "oppStatuses": "posted|forecasted",
    }).encode("utf-8")
    request = Request(
        GRANTS_GOV_SEARCH_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mavis-Digital-Campus/0.8.7.3.2",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # nosec B310 - fixed HTTPS endpoint
            raw = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise GrantDiscoveryError(f"Grants.gov returned HTTP {exc.code}. Try again later.") from exc
    except URLError as exc:
        raise GrantDiscoveryError("I couldn't reach Grants.gov. Check the Campus internet connection and try again.") from exc
    except TimeoutError as exc:
        raise GrantDiscoveryError("Grants.gov took too long to respond. Try again in a moment.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GrantDiscoveryError("Grants.gov returned a response I couldn't read safely.") from exc

    if int(raw.get("errorcode") or 0) != 0:
        message = _clean_text(raw.get("msg") or "Grants.gov search failed.", 300)
        raise GrantDiscoveryError(message or "Grants.gov search failed.")

    data = raw.get("data") or {}
    hits = data.get("oppHits") or []
    results: list[dict[str, Any]] = []
    for hit in hits[:rows]:
        source_key = _clean_text(hit.get("id"), 80)
        if not source_key:
            continue
        opportunity_number = _clean_text(hit.get("number"), 180)
        title = _clean_text(hit.get("title"), 320) or "Untitled opportunity"
        agency_name = _clean_text(hit.get("agencyName"), 260)
        agency_code = _clean_text(hit.get("agencyCode"), 80)
        funder = agency_name or agency_code or "U.S. Federal Agency"
        source_status = _clean_text(hit.get("oppStatus"), 80).lower()
        results.append({
            "source_name": "Grants.gov",
            "source_key": source_key,
            "opportunity_number": opportunity_number,
            "title": title,
            "funder": funder,
            "agency_code": agency_code,
            "open_date": _iso_date(hit.get("openDate")),
            "deadline": _iso_date(hit.get("closeDate")),
            "source_status": source_status,
            "document_type": _clean_text(hit.get("docType"), 80),
            "alns": [str(x)[:40] for x in (hit.get("alnist") or []) if str(x).strip()][:8],
            "source_url": f"{GRANTS_GOV_DETAIL_BASE}/{source_key}",
        })

    return {
        "provider": "Grants.gov",
        "query": query,
        "hit_count": int(data.get("hitCount") or len(results)),
        "returned": len(results),
        "results": results,
    }
