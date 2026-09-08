from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai.provider import GenerationResult

ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "prompts" / "research.txt"


class ResearchError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResearchResult:
    artifact: dict[str, Any]
    rendered_text: str
    generation: GenerationResult


def _clean_text(value: Any, *, limit: int) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _clean_list(value: Any, *, max_items: int, item_limit: int = 500) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value[:max_items]:
        text = _clean_text(item, limit=item_limit)
        if text:
            output.append(text)
    return output


def _extract_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise ResearchError("Research did not return a readable JSON brief.")
        try:
            data = json.loads(raw[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ResearchError("Research returned a brief that was not valid JSON.") from exc

    if not isinstance(data, dict):
        raise ResearchError("Research response was not a JSON object.")
    return data


def normalize_artifact(data: dict[str, Any]) -> dict[str, Any]:
    executive_summary = _clean_text(data.get("executive_summary"), limit=1600)
    findings = _clean_list(data.get("findings"), max_items=8)
    recommendations = _clean_list(data.get("practical_recommendations"), max_items=6)
    uncertainties = _clean_list(data.get("uncertainties"), max_items=5)
    verification = _clean_list(data.get("verification_needed"), max_items=6)
    handoff = _clean_text(data.get("handoff_note"), limit=900)

    if not executive_summary:
        raise ResearchError("Research brief did not include an executive summary.")
    if not findings:
        raise ResearchError("Research brief did not include usable findings.")

    return {
        "executive_summary": executive_summary,
        "findings": findings,
        "practical_recommendations": recommendations,
        "uncertainties": uncertainties,
        "verification_needed": verification,
        "handoff_note": handoff,
    }


def render_artifact(artifact: dict[str, Any]) -> str:
    sections = [
        "AI-generated — Research",
        "",
        "EXECUTIVE SUMMARY",
        artifact["executive_summary"],
    ]

    def add_list(title: str, items: list[str]) -> None:
        if items:
            sections.extend(["", title])
            sections.extend(f"• {item}" for item in items)

    add_list("FINDINGS", artifact["findings"])
    add_list("PRACTICAL RECOMMENDATIONS", artifact["practical_recommendations"])
    add_list("UNCERTAINTIES / LIMITATIONS", artifact["uncertainties"])
    add_list("VERIFY BEFORE PUBLIC USE", artifact["verification_needed"])

    if artifact["handoff_note"]:
        sections.extend(["", "HANDOFF NOTE", artifact["handoff_note"]])

    sections.extend([
        "",
        "Research boundary: Gemini produced this internal brief from the approved task context. "
        "This workflow did not autonomously browse the web or verify current external sources."
    ])
    return "\n".join(sections)


def run_research(
    provider,
    *,
    project_title: str,
    project_summary: str,
    task_title: str,
    task_brief: str,
    prior_results: list[dict[str, str]] | None = None,
    institutional_memory: list[dict[str, Any]] | None = None,
) -> ResearchResult:
    prior_results = prior_results or []
    institutional_memory = institutional_memory or []
    parts = [
        PROMPT_PATH.read_text(encoding="utf-8"),
        "",
        "PROJECT TITLE:",
        _clean_text(project_title, limit=300),
        "",
        "PROJECT SUMMARY:",
        _clean_text(project_summary, limit=1800),
        "",
        "APPROVED RESEARCH TASK:",
        _clean_text(task_title, limit=300),
        "",
        "CHIEF OF STAFF BRIEF:",
        _clean_text(task_brief, limit=2200),
    ]

    if institutional_memory:
        parts.extend([
            "",
            "HUMAN-CURATED INSTITUTIONAL MEMORY:",
            json.dumps(institutional_memory, ensure_ascii=False, indent=2),
            "Use memory as organizational context, not as proof of external facts. Current approved task instructions take precedence if there is a conflict.",
        ])

    if prior_results:
        parts.extend(["", "PRIOR COMPLETED INTERNAL RESULTS:"])
        for item in prior_results[:4]:
            parts.append(
                f"- {item.get('owner','Campus')}: "
                f"{_clean_text(item.get('result'), limit=1400)}"
            )

    parts.extend(["", "Produce the internal research brief now. Return only the required JSON object."])
    prompt = "\n".join(parts)

    generation = provider.generate_text(prompt, max_output_tokens=1400)
    artifact = normalize_artifact(_extract_json(generation.text))
    return ResearchResult(
        artifact=artifact,
        rendered_text=render_artifact(artifact),
        generation=generation,
    )
