from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai.provider import GenerationResult

ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "prompts" / "chief_review.txt"

VALID_RECOMMENDATIONS = {"approve_internal", "revise", "hold"}
VALID_CRITERION_STATUS = {"met", "partially_met", "not_met", "unclear"}

CHIEF_REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "review_title": {"type": "string"},
        "executive_summary": {"type": "string"},
        "approval_recommendation": {
            "type": "string",
            "enum": ["approve_internal", "revise", "hold"],
        },
        "success_criteria_review": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["met", "partially_met", "not_met", "unclear"],
                    },
                    "evidence": {"type": "string"},
                },
                "required": ["criterion", "status", "evidence"],
                "additionalProperties": False,
            },
        },
        "deliverable_review": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "deliverable_key": {"type": "string"},
                    "deliverable": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["ready", "needs_verification", "needs_revision", "not_ready"],
                    },
                    "note": {"type": "string"},
                },
                "required": ["deliverable_key", "deliverable", "status", "note"],
                "additionalProperties": False,
            },
        },
        "research_programs_alignment": {
            "type": "array",
            "items": {"type": "string"},
        },
        "gaps_or_conflicts": {
            "type": "array",
            "items": {"type": "string"},
        },
        "verification_before_public_use": {
            "type": "array",
            "items": {"type": "string"},
        },
        "recommended_revisions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "executive_decisions_needed": {
            "type": "array",
            "items": {"type": "string"},
        },
        "final_package_summary": {"type": "string"},
        "handoff_note": {"type": "string"},
    },
    "required": [
        "review_title",
        "executive_summary",
        "approval_recommendation",
        "success_criteria_review",
        "deliverable_review",
        "research_programs_alignment",
        "gaps_or_conflicts",
        "verification_before_public_use",
        "recommended_revisions",
        "executive_decisions_needed",
        "final_package_summary",
        "handoff_note",
    ],
    "additionalProperties": False,
}


class ChiefReviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChiefReviewResult:
    artifact: dict[str, Any]
    rendered_text: str
    generation: GenerationResult
    attempt_count: int = 1


def _clean_text(value: Any, *, limit: int) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _clean_list(value: Any, *, max_items: int, item_limit: int = 700) -> list[str]:
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
            raise ChiefReviewError("Chief final review did not return a readable JSON object.")
        try:
            data = json.loads(raw[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ChiefReviewError("Chief final review returned invalid JSON.") from exc

    if not isinstance(data, dict):
        raise ChiefReviewError("Chief final review response was not a JSON object.")
    return data


def normalize_artifact(
    data: dict[str, Any],
    *,
    project_title: str,
    success_criteria: list[str],
) -> dict[str, Any]:
    review_title = _clean_text(data.get("review_title"), limit=180)
    if not review_title:
        review_title = f"Executive Review — {_clean_text(project_title, limit=140)}"

    summary = _clean_text(data.get("executive_summary"), limit=2200)
    if not summary:
        raise ChiefReviewError("Chief final review did not include an executive summary.")

    recommendation = _clean_text(data.get("approval_recommendation"), limit=40).lower()
    if recommendation not in VALID_RECOMMENDATIONS:
        raise ChiefReviewError("Chief final review did not include a valid approval recommendation.")

    raw_criteria = data.get("success_criteria_review")
    criteria_review: list[dict[str, str]] = []

    if isinstance(raw_criteria, list):
        for item in raw_criteria[:12]:
            if not isinstance(item, dict):
                continue
            criterion = _clean_text(item.get("criterion"), limit=600)
            status = _clean_text(item.get("status"), limit=40).lower()
            evidence = _clean_text(item.get("evidence"), limit=1100)
            if criterion and status in VALID_CRITERION_STATUS:
                criteria_review.append({
                    "criterion": criterion,
                    "status": status,
                    "evidence": evidence,
                })

    if success_criteria and not criteria_review:
        raise ChiefReviewError("Chief final review did not assess the approved success criteria.")

    deliverable_review: list[dict[str, str]] = []
    raw_deliverables = data.get("deliverable_review")
    if isinstance(raw_deliverables, list):
        for item in raw_deliverables[:16]:
            if not isinstance(item, dict):
                continue
            deliverable_key = _clean_text(item.get("deliverable_key"), limit=220)
            deliverable = _clean_text(item.get("deliverable"), limit=220)
            status = _clean_text(item.get("status"), limit=40).lower()
            note = _clean_text(item.get("note"), limit=900)
            if status not in {"ready", "needs_verification", "needs_revision", "not_ready"}:
                continue
            if deliverable_key or deliverable:
                deliverable_review.append({
                    "deliverable_key": deliverable_key,
                    "deliverable": deliverable,
                    "status": status,
                    "note": note,
                })

    return {
        "review_title": review_title,
        "executive_summary": summary,
        "approval_recommendation": recommendation,
        "success_criteria_review": criteria_review,
        "deliverable_review": deliverable_review,
        "research_programs_alignment": _clean_list(data.get("research_programs_alignment"), max_items=10),
        "gaps_or_conflicts": _clean_list(data.get("gaps_or_conflicts"), max_items=10),
        "verification_before_public_use": _clean_list(data.get("verification_before_public_use"), max_items=12),
        "recommended_revisions": _clean_list(data.get("recommended_revisions"), max_items=10),
        "executive_decisions_needed": _clean_list(data.get("executive_decisions_needed"), max_items=10),
        "final_package_summary": _clean_text(data.get("final_package_summary"), limit=1800),
        "handoff_note": _clean_text(data.get("handoff_note"), limit=1000),
    }


def render_artifact(artifact: dict[str, Any]) -> str:
    recommendation_labels = {
        "approve_internal": "APPROVE INTERNAL PACKAGE",
        "revise": "REVISION RECOMMENDED",
        "hold": "HOLD — MORE INFORMATION NEEDED",
    }

    sections: list[str] = [
        "AI-generated — Chief Final Review",
        "",
        artifact["review_title"],
        "",
        "EXECUTIVE SUMMARY",
        artifact["executive_summary"],
        "",
        "CHIEF RECOMMENDATION",
        recommendation_labels[artifact["approval_recommendation"]],
    ]

    if artifact["success_criteria_review"]:
        sections.extend(["", "SUCCESS CRITERIA"])
        for item in artifact["success_criteria_review"]:
            sections.append(
                f"• {item['status'].replace('_', ' ').upper()} — {item['criterion']}"
            )
            if item["evidence"]:
                sections.append(f"  Evidence: {item['evidence']}")

    if artifact.get("deliverable_review"):
        sections.extend(["", "DELIVERABLE REVIEW"])
        for item in artifact["deliverable_review"]:
            label = item.get("deliverable") or item.get("deliverable_key") or "Deliverable"
            sections.append(
                f"• {str(item.get('status','')).replace('_',' ').upper()} — {label}"
            )
            if item.get("note"):
                sections.append(f"  {item['note']}")

    def add_list(title: str, items: list[str]) -> None:
        if not items:
            return
        sections.extend(["", title])
        sections.extend(f"• {item}" for item in items)

    add_list("RESEARCH / PROGRAMS ALIGNMENT", artifact["research_programs_alignment"])
    add_list("GAPS OR CONFLICTS", artifact["gaps_or_conflicts"])
    add_list("VERIFY BEFORE PUBLIC USE", artifact["verification_before_public_use"])
    add_list("RECOMMENDED REVISIONS", artifact["recommended_revisions"])
    add_list("EXECUTIVE DECISIONS NEEDED", artifact["executive_decisions_needed"])

    if artifact["final_package_summary"]:
        sections.extend(["", "FINAL PACKAGE", artifact["final_package_summary"]])

    if artifact["handoff_note"]:
        sections.extend(["", "HANDOFF NOTE", artifact["handoff_note"]])

    sections.extend([
        "",
        "Chief review boundary: this is an internal executive review only. "
        "Approval does not authorize email, publishing, purchasing, spending, submission, external contact, "
        "or any other consequential outside action."
    ])

    return "\n".join(sections)


def _build_prompt(
    *,
    project_title: str,
    project_summary: str,
    task_title: str,
    task_brief: str,
    success_criteria: list[str],
    risk_notes: list[str],
    questions_for_executive: list[str],
    research_artifacts: list[dict[str, Any]],
    programs_artifacts: list[dict[str, Any]],
    deliverables: list[dict[str, Any]],
    other_completed_results: list[dict[str, str]],
    institutional_memory: list[dict[str, Any]],
    playbooks: list[dict[str, Any]],
) -> str:
    parts: list[str] = [
        PROMPT_PATH.read_text(encoding="utf-8"),
        "",
        "PROJECT TITLE:",
        _clean_text(project_title, limit=300),
        "",
        "APPROVED PROJECT SUMMARY:",
        _clean_text(project_summary, limit=2200),
        "",
        "FINAL CHIEF TASK:",
        _clean_text(task_title, limit=300),
        "",
        "CHIEF TASK BRIEF:",
        _clean_text(task_brief, limit=2400),
        "",
        "APPROVED SUCCESS CRITERIA:",
        json.dumps(success_criteria, ensure_ascii=False, indent=2),
        "",
        "ORIGINAL RISK NOTES:",
        json.dumps(risk_notes, ensure_ascii=False, indent=2),
        "",
        "ORIGINAL QUESTIONS FOR EXECUTIVE:",
        json.dumps(questions_for_executive, ensure_ascii=False, indent=2),
        "",
        "COMPLETED STRUCTURED RESEARCH ARTIFACTS:",
        json.dumps(research_artifacts, ensure_ascii=False, indent=2),
        "",
        "COMPLETED STRUCTURED PROGRAMS ARTIFACTS:",
        json.dumps(programs_artifacts, ensure_ascii=False, indent=2),
        "",
        "CURRENT PROJECT DELIVERABLES:",
        json.dumps(deliverables, ensure_ascii=False, indent=2),
        "",
        "OTHER COMPLETED INTERNAL TASK RESULTS:",
        json.dumps(other_completed_results, ensure_ascii=False, indent=2),
        "",
        "HUMAN-CURATED INSTITUTIONAL MEMORY:",
        json.dumps(institutional_memory, ensure_ascii=False, indent=2),
        "",
        "Use memory as durable organizational context. Current project instructions and explicit human decisions take precedence over older memory if they conflict.",
        "",
        "ACTIVE HUMAN-AUTHORED INSTITUTIONAL PLAYBOOKS:",
        json.dumps(playbooks, ensure_ascii=False, indent=2),
        "",
        "Use relevant playbooks to assess procedural completeness. A playbook is internal procedure, not external-action authority, and current human instructions take precedence.",
        "",
        "Prepare the final internal executive review now. Return only the required JSON object.",
    ]
    return "\n".join(parts)


def run_chief_review(
    provider,
    *,
    project_title: str,
    project_summary: str,
    task_title: str,
    task_brief: str,
    success_criteria: list[str],
    risk_notes: list[str] | None = None,
    questions_for_executive: list[str] | None = None,
    research_artifacts: list[dict[str, Any]] | None = None,
    programs_artifacts: list[dict[str, Any]] | None = None,
    deliverables: list[dict[str, Any]] | None = None,
    other_completed_results: list[dict[str, str]] | None = None,
    institutional_memory: list[dict[str, Any]] | None = None,
    playbooks: list[dict[str, Any]] | None = None,
) -> ChiefReviewResult:
    risk_notes = risk_notes or []
    questions_for_executive = questions_for_executive or []
    research_artifacts = research_artifacts or []
    programs_artifacts = programs_artifacts or []
    deliverables = deliverables or []
    other_completed_results = other_completed_results or []
    institutional_memory = institutional_memory or []
    playbooks = playbooks or []

    prompt = _build_prompt(
        project_title=project_title,
        project_summary=project_summary,
        task_title=task_title,
        task_brief=task_brief,
        success_criteria=success_criteria,
        risk_notes=risk_notes,
        questions_for_executive=questions_for_executive,
        research_artifacts=research_artifacts,
        programs_artifacts=programs_artifacts,
        deliverables=deliverables,
        other_completed_results=other_completed_results,
        institutional_memory=institutional_memory,
        playbooks=playbooks,
    )

    # OpenAI routes can use strict Structured Outputs. The default Gemini Chief
    # route uses JSON-only prompting plus one same-provider repair attempt if needed.
    if hasattr(provider, "generate_structured"):
        generation = provider.generate_structured(
            prompt,
            schema_name="mavis_chief_final_review",
            schema=CHIEF_REVIEW_SCHEMA,
            max_output_tokens=2600,
        )
        artifact = normalize_artifact(
            _extract_json(generation.text),
            project_title=project_title,
            success_criteria=success_criteria,
        )
        return ChiefReviewResult(
            artifact=artifact,
            rendered_text=render_artifact(artifact),
            generation=generation,
            attempt_count=1,
        )

    first = provider.generate_text(prompt, max_output_tokens=1800)
    try:
        artifact = normalize_artifact(
            _extract_json(first.text),
            project_title=project_title,
            success_criteria=success_criteria,
        )
        return ChiefReviewResult(
            artifact=artifact,
            rendered_text=render_artifact(artifact),
            generation=first,
            attempt_count=1,
        )
    except ChiefReviewError as first_error:
        repair_prompt = "\n".join([
            "You are repairing your own previous Chief final-review response.",
            "The previous response was not valid usable JSON.",
            "Return ONLY one corrected JSON object matching the requested Chief final-review shape.",
            "Do not add Markdown or commentary.",
            "",
            "ORIGINAL PROJECT TITLE:",
            _clean_text(project_title, limit=300),
            "",
            "APPROVED SUCCESS CRITERIA:",
            json.dumps(success_criteria, ensure_ascii=False),
            "",
            "PREVIOUS RESPONSE TO REPAIR:",
            first.text[:12000],
        ])
        second = provider.generate_text(repair_prompt, max_output_tokens=1800)

        try:
            artifact = normalize_artifact(
                _extract_json(second.text),
                project_title=project_title,
                success_criteria=success_criteria,
            )
        except ChiefReviewError as second_error:
            raise ChiefReviewError(
                "Chief final review returned invalid structured JSON after one same-provider repair attempt."
            ) from second_error

        combined = GenerationResult(
            provider=second.provider,
            model=second.model,
            text=second.text,
            input_chars=first.input_chars + second.input_chars,
            output_chars=first.output_chars + second.output_chars,
        )
        return ChiefReviewResult(
            artifact=artifact,
            rendered_text=render_artifact(artifact),
            generation=combined,
            attempt_count=2,
        )
