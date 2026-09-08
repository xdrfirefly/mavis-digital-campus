from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai.provider import GenerationResult

ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "prompts" / "chief_revision.txt"

MAX_TASK_REVISIONS = 6
MAX_DELIVERABLE_REVISIONS = 12


class ChiefRevisionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChiefRevisionResult:
    plan: dict[str, Any]
    generation: GenerationResult
    attempt_count: int = 1


def _clean_text(value: Any, *, limit: int) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


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
        value = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise ChiefRevisionError("Chief revision planning did not return readable JSON.")
        try:
            value = json.loads(raw[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ChiefRevisionError("Chief revision planning returned invalid JSON.") from exc

    if not isinstance(value, dict):
        raise ChiefRevisionError("Chief revision planning response was not a JSON object.")
    return value


def normalize_revision_plan(
    data: dict[str, Any],
    *,
    allowed_task_ids: set[int],
    allowed_deliverable_keys: set[str],
) -> dict[str, Any]:
    summary = _clean_text(data.get("revision_summary"), limit=1600)
    if not summary:
        raise ChiefRevisionError("Chief revision plan did not include a usable summary.")

    task_revisions: list[dict[str, Any]] = []
    seen_tasks: set[int] = set()
    raw_tasks = data.get("task_revisions")
    if isinstance(raw_tasks, list):
        for item in raw_tasks[:MAX_TASK_REVISIONS]:
            if not isinstance(item, dict):
                continue
            try:
                task_id = int(item.get("task_id"))
            except (TypeError, ValueError):
                continue
            if task_id not in allowed_task_ids or task_id in seen_tasks:
                continue
            reason = _clean_text(item.get("reason"), limit=700)
            revision_brief = _clean_text(item.get("revision_brief"), limit=1800)
            if not revision_brief:
                continue
            seen_tasks.add(task_id)
            task_revisions.append({
                "task_id": task_id,
                "reason": reason or "Selected by the Chief for revision.",
                "revision_brief": revision_brief,
            })

    deliverable_revisions: list[dict[str, str]] = []
    seen_outputs: set[str] = set()
    raw_outputs = data.get("deliverable_revisions")
    if isinstance(raw_outputs, list):
        for item in raw_outputs[:MAX_DELIVERABLE_REVISIONS]:
            if not isinstance(item, dict):
                continue
            key = _clean_text(item.get("deliverable_key"), limit=240)
            if key not in allowed_deliverable_keys or key in seen_outputs:
                continue
            seen_outputs.add(key)
            deliverable_revisions.append({
                "deliverable_key": key,
                "reason": _clean_text(item.get("reason"), limit=700)
                or "Selected by the Chief for a new output version.",
            })

    preserve: list[str] = []
    raw_preserve = data.get("preserve_deliverable_keys")
    if isinstance(raw_preserve, list):
        for value in raw_preserve[:MAX_DELIVERABLE_REVISIONS]:
            key = _clean_text(value, limit=240)
            if (
                key in allowed_deliverable_keys
                and key not in seen_outputs
                and key not in preserve
            ):
                preserve.append(key)

    # Any supplied output not selected for revision is preserved locally.
    for key in sorted(allowed_deliverable_keys):
        if key not in seen_outputs and key not in preserve:
            preserve.append(key)

    questions: list[str] = []
    raw_questions = data.get("questions_for_executive")
    if isinstance(raw_questions, list):
        for value in raw_questions[:4]:
            text = _clean_text(value, limit=600)
            if text:
                questions.append(text)

    if not task_revisions and not deliverable_revisions:
        raise ChiefRevisionError(
            "Chief revision plan did not select any existing work to revise."
        )

    return {
        "revision_summary": summary,
        "task_revisions": task_revisions,
        "deliverable_revisions": deliverable_revisions,
        "preserve_deliverable_keys": preserve,
        "questions_for_executive": questions,
    }


def _build_prompt(
    *,
    project_title: str,
    project_summary: str,
    success_criteria: list[str],
    human_revision_request: str,
    tasks: list[dict[str, Any]],
    deliverables: list[dict[str, Any]],
    previous_chief_review: dict[str, Any],
    institutional_memory: list[dict[str, Any]],
    playbooks: list[dict[str, Any]],
) -> str:
    return "\n".join([
        PROMPT_PATH.read_text(encoding="utf-8"),
        "",
        "PROJECT TITLE:",
        _clean_text(project_title, limit=300),
        "",
        "ORIGINAL PROJECT SUMMARY:",
        _clean_text(project_summary, limit=2200),
        "",
        "SUCCESS CRITERIA:",
        json.dumps(success_criteria, ensure_ascii=False, indent=2),
        "",
        "HUMAN REVISION INSTRUCTION:",
        _clean_text(human_revision_request, limit=4000),
        "",
        "EXISTING TASKS:",
        json.dumps(tasks, ensure_ascii=False, indent=2),
        "",
        "CURRENT PROJECT DELIVERABLES:",
        json.dumps(deliverables, ensure_ascii=False, indent=2),
        "",
        "PREVIOUS CHIEF FINAL REVIEW:",
        json.dumps(previous_chief_review, ensure_ascii=False, indent=2),
        "",
        "HUMAN-CURATED INSTITUTIONAL MEMORY:",
        json.dumps(institutional_memory, ensure_ascii=False, indent=2),
        "",
        "Use memory as durable organizational context. The current human revision instruction takes precedence over older memory if there is a conflict.",
        "",
        "ACTIVE HUMAN-AUTHORED INSTITUTIONAL PLAYBOOKS:",
        json.dumps(playbooks, ensure_ascii=False, indent=2),
        "",
        "Use only relevant playbooks. They are internal procedures, not external-action authority, and the current human revision instruction wins if there is a conflict.",
        "",
        "Create the smallest useful revision plan now. Return only the required JSON object.",
    ])


def run_chief_revision_plan(
    provider,
    *,
    project_title: str,
    project_summary: str,
    success_criteria: list[str],
    human_revision_request: str,
    tasks: list[dict[str, Any]],
    deliverables: list[dict[str, Any]],
    previous_chief_review: dict[str, Any] | None = None,
    institutional_memory: list[dict[str, Any]] | None = None,
    playbooks: list[dict[str, Any]] | None = None,
) -> ChiefRevisionResult:
    previous_chief_review = previous_chief_review or {}
    institutional_memory = institutional_memory or []
    playbooks = playbooks or []
    allowed_task_ids = {
        int(item["task_id"])
        for item in tasks
        if str(item.get("owner") or "") != "chief"
    }
    allowed_deliverable_keys = {
        str(item["deliverable_key"])
        for item in deliverables
        if str(item.get("deliverable_key") or "")
    }

    prompt = _build_prompt(
        project_title=project_title,
        project_summary=project_summary,
        success_criteria=success_criteria,
        human_revision_request=human_revision_request,
        tasks=tasks,
        deliverables=deliverables,
        previous_chief_review=previous_chief_review,
        institutional_memory=institutional_memory,
        playbooks=playbooks,
    )

    first = provider.generate_text(prompt, max_output_tokens=1600)
    try:
        plan = normalize_revision_plan(
            _extract_json(first.text),
            allowed_task_ids=allowed_task_ids,
            allowed_deliverable_keys=allowed_deliverable_keys,
        )
        return ChiefRevisionResult(plan=plan, generation=first, attempt_count=1)
    except ChiefRevisionError:
        repair_prompt = "\n".join([
            "Repair your previous revision-planning response.",
            "Return ONLY valid JSON in the exact requested revision-plan shape.",
            "Use only task IDs and deliverable keys that were supplied in the original prompt.",
            "",
            "PREVIOUS RESPONSE:",
            first.text[:10000],
            "",
            "ORIGINAL CONTEXT:",
            prompt[:16000],
        ])
        second = provider.generate_text(repair_prompt, max_output_tokens=1600)
        try:
            plan = normalize_revision_plan(
                _extract_json(second.text),
                allowed_task_ids=allowed_task_ids,
                allowed_deliverable_keys=allowed_deliverable_keys,
            )
        except ChiefRevisionError as exc:
            raise ChiefRevisionError(
                "Chief revision planning returned invalid structured JSON after one same-provider repair attempt."
            ) from exc

        combined = GenerationResult(
            provider=second.provider,
            model=second.model,
            text=second.text,
            input_chars=first.input_chars + second.input_chars,
            output_chars=first.output_chars + second.output_chars,
        )
        return ChiefRevisionResult(
            plan=plan,
            generation=combined,
            attempt_count=2,
        )
