from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai.provider import GenerationResult

ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "prompts" / "programs.txt"


class ProgramsError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProgramsResult:
    artifact: dict[str, Any]
    rendered_text: str
    generation: GenerationResult


PROGRAMS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "deliverable_title": {"type": "string"},
        "program_summary": {"type": "string"},
        "audience": {"type": "string"},
        "duration_minutes": {"type": "integer"},
        "objectives": {
            "type": "array",
            "items": {"type": "string"},
        },
        "run_of_show": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "minutes": {"type": "integer"},
                    "segment": {"type": "string"},
                    "purpose": {"type": "string"},
                    "facilitator_action": {"type": "string"},
                },
                "required": [
                    "minutes",
                    "segment",
                    "purpose",
                    "facilitator_action",
                ],
                "additionalProperties": False,
            },
        },
        "materials": {
            "type": "array",
            "items": {"type": "string"},
        },
        "participant_activities": {
            "type": "array",
            "items": {"type": "string"},
        },
        "facilitator_notes": {
            "type": "array",
            "items": {"type": "string"},
        },
        "handout_or_resource_ideas": {
            "type": "array",
            "items": {"type": "string"},
        },
        "research_integration": {
            "type": "array",
            "items": {"type": "string"},
        },
        "verification_flags": {
            "type": "array",
            "items": {"type": "string"},
        },
        "handoff_note": {"type": "string"},
    },
    "required": [
        "deliverable_title",
        "program_summary",
        "audience",
        "duration_minutes",
        "objectives",
        "run_of_show",
        "materials",
        "participant_activities",
        "facilitator_notes",
        "handout_or_resource_ideas",
        "research_integration",
        "verification_flags",
        "handoff_note",
    ],
    "additionalProperties": False,
}


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
            raise ProgramsError("Programs did not return a readable JSON deliverable.")
        try:
            data = json.loads(raw[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ProgramsError("Programs returned a deliverable that was not valid JSON.") from exc

    if not isinstance(data, dict):
        raise ProgramsError("Programs response was not a JSON object.")
    return data


def _clean_run_of_show(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    output: list[dict[str, Any]] = []
    for item in value[:10]:
        if not isinstance(item, dict):
            continue

        try:
            minutes = int(item.get("minutes") or 0)
        except (TypeError, ValueError):
            minutes = 0

        minutes = max(1, min(minutes, 240))
        segment = _clean_text(item.get("segment"), limit=220)
        purpose = _clean_text(item.get("purpose"), limit=500)
        action = _clean_text(item.get("facilitator_action"), limit=900)

        if not segment:
            continue

        output.append({
            "minutes": minutes,
            "segment": segment,
            "purpose": purpose,
            "facilitator_action": action,
        })

    return output


def normalize_artifact(data: dict[str, Any], task_title: str) -> dict[str, Any]:
    title = _clean_text(data.get("deliverable_title"), limit=180)
    if not title:
        title = _clean_text(task_title, limit=180) or "Programs Deliverable"

    summary = _clean_text(data.get("program_summary"), limit=1800)
    audience = _clean_text(data.get("audience"), limit=500)

    try:
        duration = int(data.get("duration_minutes") or 0)
    except (TypeError, ValueError):
        duration = 0
    duration = max(0, min(duration, 1440))

    run_of_show = _clean_run_of_show(data.get("run_of_show"))
    if not duration and run_of_show:
        duration = sum(int(item["minutes"]) for item in run_of_show)

    objectives = _clean_list(data.get("objectives"), max_items=8)
    if not summary:
        raise ProgramsError("Programs deliverable did not include a usable program summary.")
    if not objectives:
        raise ProgramsError("Programs deliverable did not include usable objectives.")
    if not run_of_show:
        raise ProgramsError("Programs deliverable did not include a usable run of show.")

    return {
        "deliverable_title": title,
        "program_summary": summary,
        "audience": audience,
        "duration_minutes": duration,
        "objectives": objectives,
        "run_of_show": run_of_show,
        "materials": _clean_list(data.get("materials"), max_items=12),
        "participant_activities": _clean_list(data.get("participant_activities"), max_items=8),
        "facilitator_notes": _clean_list(data.get("facilitator_notes"), max_items=10),
        "handout_or_resource_ideas": _clean_list(data.get("handout_or_resource_ideas"), max_items=8),
        "research_integration": _clean_list(data.get("research_integration"), max_items=8),
        "verification_flags": _clean_list(data.get("verification_flags"), max_items=8),
        "handoff_note": _clean_text(data.get("handoff_note"), limit=1000),
    }


def render_artifact(artifact: dict[str, Any]) -> str:
    sections: list[str] = [
        "AI-generated — Programs",
        "",
        artifact["deliverable_title"],
        "",
        "PROGRAM SUMMARY",
        artifact["program_summary"],
    ]

    if artifact["audience"]:
        sections.extend(["", "AUDIENCE", artifact["audience"]])

    if artifact["duration_minutes"]:
        sections.extend(["", "DURATION", f"{artifact['duration_minutes']} minutes"])

    def add_list(title: str, items: list[str]) -> None:
        if not items:
            return
        sections.extend(["", title])
        sections.extend(f"• {item}" for item in items)

    add_list("OBJECTIVES", artifact["objectives"])

    sections.extend(["", "RUN OF SHOW"])
    for item in artifact["run_of_show"]:
        sections.append(
            f"• {item['minutes']} min — {item['segment']}"
            + (f": {item['facilitator_action']}" if item["facilitator_action"] else "")
        )
        if item["purpose"]:
            sections.append(f"  Purpose: {item['purpose']}")

    add_list("MATERIALS", artifact["materials"])
    add_list("PARTICIPANT ACTIVITIES", artifact["participant_activities"])
    add_list("FACILITATOR NOTES", artifact["facilitator_notes"])
    add_list("HANDOUT / RESOURCE IDEAS", artifact["handout_or_resource_ideas"])
    add_list("HOW RESEARCH WAS USED", artifact["research_integration"])
    add_list("VERIFY BEFORE PUBLIC USE", artifact["verification_flags"])

    if artifact["handoff_note"]:
        sections.extend(["", "HANDOFF NOTE", artifact["handoff_note"]])

    sections.extend([
        "",
        "Programs boundary: this deliverable was generated from the approved Programs brief and supplied internal project context. "
        "No email, publishing, purchasing, submission, external contact, or autonomous web action occurred."
    ])

    return "\n".join(sections)


def run_programs(
    provider,
    *,
    project_title: str,
    project_summary: str,
    task_title: str,
    task_brief: str,
    research_artifacts: list[dict[str, Any]] | None = None,
    prior_results: list[dict[str, str]] | None = None,
    institutional_memory: list[dict[str, Any]] | None = None,
    library_context: dict[str, Any] | None = None,
) -> ProgramsResult:
    research_artifacts = research_artifacts or []
    prior_results = prior_results or []
    institutional_memory = institutional_memory or []
    library_context = library_context or {}

    parts: list[str] = [
        PROMPT_PATH.read_text(encoding="utf-8"),
        "",
        "PROJECT TITLE:",
        _clean_text(project_title, limit=300),
        "",
        "PROJECT SUMMARY:",
        _clean_text(project_summary, limit=1800),
        "",
        "APPROVED PROGRAMS TASK:",
        _clean_text(task_title, limit=300),
        "",
        "CHIEF OF STAFF BRIEF:",
        _clean_text(task_brief, limit=2400),
    ]

    if institutional_memory:
        parts.extend([
            "",
            "HUMAN-CURATED INSTITUTIONAL MEMORY:",
            json.dumps(institutional_memory, ensure_ascii=False, indent=2),
            "Use memory to preserve established institutional decisions, preferences, lessons, and context. Current approved task instructions take precedence if there is a conflict.",
        ])

    if library_context:
        parts.extend([
            "",
            "PROGRAMS LIBRARY FIRST — TRUSTED LOCAL LIBRARY CONTEXT:",
            json.dumps(library_context, ensure_ascii=False, indent=2),
            (
                "This context came from the local Librarian and human Library First decision. "
                "Catalog metadata is always trusted local context. Some human-approved files may also include locally extracted text under selected_material_contents/trusted_local_text. "
                "Only claim to have read file content when trusted_local_text is explicitly present; an index status without text is not file content. "
                "If decision=revise, treat the selected collection and any supplied trusted_local_text as the institutional baseline and preserve its established theme unless the approved brief explicitly changes it. "
                "If decision=create_new, the human deliberately chose new work after reviewing existing holdings; do not falsely claim unsupplied holdings were used as source content."
            ),
        ])

    if research_artifacts:
        parts.extend(["", "STRUCTURED INTERNAL RESEARCH ARTIFACTS:"])
        for index, artifact in enumerate(research_artifacts[:4], start=1):
            parts.append(f"Research artifact {index}:")
            parts.append(json.dumps(artifact, ensure_ascii=False, indent=2))
    else:
        parts.extend([
            "",
            "STRUCTURED INTERNAL RESEARCH ARTIFACTS:",
            "None were available before this Programs task. Do not pretend that Research supplied information it did not supply."
        ])

    if prior_results:
        parts.extend(["", "OTHER PRIOR COMPLETED INTERNAL RESULTS:"])
        for item in prior_results[:4]:
            owner = _clean_text(item.get("owner"), limit=100)
            result = _clean_text(item.get("result"), limit=1600)
            parts.append(f"- {owner}: {result}")

    parts.extend([
        "",
        "Build the Programs deliverable now. Return only the required JSON object."
    ])

    prompt = "\n".join(parts)

    # OpenAI's Responses API supports strict JSON Schema Structured Outputs.
    # Use it when the configured provider exposes that capability. This avoids
    # accepting prose, Markdown, or truncated pseudo-JSON as a Programs artifact.
    if hasattr(provider, "generate_structured"):
        generation = provider.generate_structured(
            prompt,
            schema_name="mavis_programs_deliverable",
            schema=PROGRAMS_SCHEMA,
            max_output_tokens=3600,
        )
    else:
        generation = provider.generate_text(prompt, max_output_tokens=3000)

    artifact = normalize_artifact(_extract_json(generation.text), task_title)

    return ProgramsResult(
        artifact=artifact,
        rendered_text=render_artifact(artifact),
        generation=generation,
    )
