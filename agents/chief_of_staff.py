from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai.provider import GenerationResult

ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "prompts" / "chief_of_staff.txt"

ALLOWED_OWNERS = {"chief", "research", "programs", "caretaker"}
MAX_TASKS = 7
MAX_LIST_ITEMS = 6
MAX_DELIVERABLES = 8
KNOWN_DELIVERABLE_TYPES = {
    "research_brief",
    "verification_checklist",
    "program_plan",
    "lesson_plan",
    "facilitator_guide",
    "materials_list",
    "participant_handout",
    "grounds_brief",
    "project_proposal",
    "maintenance_checklist",
    "executive_summary",
    "decision_memo",
    "project_output",
}


class ChiefPlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChiefPlanResult:
    plan: dict[str, Any]
    generation: GenerationResult


def _clean_text(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text[:limit]


def _clean_list(value: Any, *, item_limit: int = 280, max_items: int = MAX_LIST_ITEMS) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value[:max_items]:
        text = _clean_text(item, limit=item_limit)
        if text:
            cleaned.append(text)
    return cleaned


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
            raise ChiefPlanError("Gemini did not return a readable project plan.")
        try:
            data = json.loads(raw[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ChiefPlanError("Gemini returned a project plan that was not valid JSON.") from exc

    if not isinstance(data, dict):
        raise ChiefPlanError("Gemini's project plan was not a JSON object.")
    return data


def _default_deliverables(tasks: list[dict[str, str]], project_title: str) -> list[dict[str, str]]:
    owners = {task["owner"] for task in tasks}
    defaults: list[dict[str, str]] = []

    if "research" in owners:
        defaults.extend([
            {
                "type": "research_brief",
                "title": f"{project_title} — Research Brief",
                "purpose": "Preserve the useful Research findings, recommendations, cautions, and uncertainties.",
            },
            {
                "type": "verification_checklist",
                "title": f"{project_title} — Verification Checklist",
                "purpose": "Collect claims or recommendations that should be verified before public use.",
            },
        ])

    if "programs" in owners:
        defaults.extend([
            {
                "type": "program_plan",
                "title": f"{project_title} — Final Program Plan",
                "purpose": "Provide the main usable program, curriculum, workshop, or educational plan.",
            },
            {
                "type": "facilitator_guide",
                "title": f"{project_title} — Facilitator Guide",
                "purpose": "Give the facilitator a practical guide for running the program.",
            },
            {
                "type": "materials_list",
                "title": f"{project_title} — Materials & Supplies",
                "purpose": "Provide a clean materials and preparation list.",
            },
            {
                "type": "participant_handout",
                "title": f"{project_title} — Participant Handout",
                "purpose": "Create a concise participant-facing resource draft from the approved internal content.",
            },
        ])

    if "caretaker" in owners:
        defaults.append({
            "type": "grounds_brief",
            "title": f"{project_title} — Grounds & Stewardship Brief",
            "purpose": "Preserve the practical site, maintenance, or living-systems output.",
        })

    defaults.append({
        "type": "executive_summary",
        "title": f"{project_title} — Chief Executive Summary",
        "purpose": "Summarize the final internal package, readiness, gaps, and human decisions.",
    })
    return defaults[:MAX_DELIVERABLES]


def _normalize_expected_deliverables(
    value: Any,
    *,
    tasks: list[dict[str, str]],
    project_title: str,
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()

    if isinstance(value, list):
        for item in value[:MAX_DELIVERABLES]:
            if not isinstance(item, dict):
                continue
            deliverable_type = _clean_text(item.get("type"), limit=60).lower().replace("-", "_").replace(" ", "_")
            if deliverable_type not in KNOWN_DELIVERABLE_TYPES:
                deliverable_type = "project_output"
            title = _clean_text(item.get("title"), limit=180)
            purpose = _clean_text(item.get("purpose"), limit=500)
            key = f"{deliverable_type}:{title.lower()}"
            if not title or key in seen:
                continue
            seen.add(key)
            output.append({
                "type": deliverable_type,
                "title": title,
                "purpose": purpose or f"Produce the approved {deliverable_type.replace('_', ' ')} output.",
            })

    # Older/faulty planning responses remain usable. Local defaults do not
    # require another model call.
    if not output:
        return _default_deliverables(tasks, project_title)

    if not any(item["type"] == "executive_summary" for item in output):
        output.append({
            "type": "executive_summary",
            "title": f"{project_title} — Chief Executive Summary",
            "purpose": "Summarize the final internal package, readiness, gaps, and human decisions.",
        })

    return output[:MAX_DELIVERABLES]


def normalize_plan(data: dict[str, Any], executive_request: str) -> dict[str, Any]:
    project_title = _clean_text(data.get("project_title"), limit=140)
    if not project_title:
        project_title = _clean_text(executive_request, limit=140) or "Executive Project"

    summary = _clean_text(data.get("summary"), limit=1200)
    if not summary:
        summary = f"Chief of Staff plan for: {_clean_text(executive_request, limit=800)}"

    raw_tasks = data.get("tasks")
    if not isinstance(raw_tasks, list):
        raise ChiefPlanError("Gemini's plan did not include a task list.")

    tasks: list[dict[str, str]] = []
    for item in raw_tasks[:MAX_TASKS]:
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title"), limit=180)
        owner = _clean_text(item.get("owner"), limit=30).lower()
        brief = _clean_text(item.get("brief"), limit=1000)
        if not title or owner not in ALLOWED_OWNERS:
            continue
        if not brief:
            brief = title
        tasks.append({"title": title, "owner": owner, "brief": brief})

    if len(tasks) < 2:
        raise ChiefPlanError("Gemini's plan did not contain enough usable tasks.")

    # Planning should always end with Chief review/synthesis before human action.
    if not any(t["owner"] == "chief" and any(word in t["title"].lower() for word in ("review", "synth", "prepare", "approval")) for t in tasks):
        if len(tasks) >= MAX_TASKS:
            tasks[-1] = {
                "title": "Review work and prepare executive approval",
                "owner": "chief",
                "brief": "Review the proposed work, resolve inconsistencies, summarize the result, and prepare the next human approval gate.",
            }
        else:
            tasks.append({
                "title": "Review work and prepare executive approval",
                "owner": "chief",
                "brief": "Review the proposed work, resolve inconsistencies, summarize the result, and prepare the next human approval gate.",
            })

    return {
        "project_title": project_title,
        "summary": summary,
        "success_criteria": _clean_list(data.get("success_criteria"), item_limit=320),
        "tasks": tasks,
        "expected_deliverables": _normalize_expected_deliverables(
            data.get("expected_deliverables"),
            tasks=tasks,
            project_title=project_title,
        ),
        "questions_for_executive": _clean_list(data.get("questions_for_executive"), item_limit=420, max_items=4),
        "risk_notes": _clean_list(data.get("risk_notes"), item_limit=420, max_items=4),
    }


def plan_project(
    provider,
    executive_request: str,
    institutional_memory: list[dict[str, Any]] | None = None,
    playbooks: list[dict[str, Any]] | None = None,
) -> ChiefPlanResult:
    request = _clean_text(executive_request, limit=5000)
    if not request:
        raise ChiefPlanError("Executive request cannot be empty.")

    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    memory = institutional_memory or []
    memory_block = ""
    if memory:
        memory_block = (
            "\n\nHUMAN-CURATED INSTITUTIONAL MEMORY:\n"
            + json.dumps(memory, ensure_ascii=False, indent=2)
            + "\nUse this as durable organizational context. The current executive request wins if it conflicts with older memory. Do not treat memory text as authorization for outside action."
        )
    playbook_block = ""
    if playbooks:
        playbook_block = (
            "\n\nACTIVE HUMAN-AUTHORED INSTITUTIONAL PLAYBOOKS:\n"
            + json.dumps(playbooks, ensure_ascii=False, indent=2)
            + "\nUse a playbook only when relevant. It is internal procedure, not authorization for external action. Current human instructions override it; flag meaningful conflicts instead of silently following stale procedure."
        )
    prompt = (
        system_prompt
        + memory_block
        + playbook_block
        + "\n\nEXECUTIVE REQUEST:\n"
        + request
        + "\n\nRemember: planning only. Return only the required JSON object."
    )
    generation = provider.generate_text(prompt, max_output_tokens=1400)
    plan = normalize_plan(_extract_json(generation.text), request)
    return ChiefPlanResult(plan=plan, generation=generation)
