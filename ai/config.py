from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_OPENAI_MODEL = "gpt-5.6-terra"

VALID_PROVIDERS = {"gemini", "openai"}
VALID_ROLES = {"chief", "research", "programs", "caretaker"}


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        values[key] = value

    return values


def combined_environment() -> dict[str, str]:
    merged = read_env_file(ENV_PATH)
    merged.update({k: v for k, v in os.environ.items() if isinstance(v, str)})
    return merged


def _provider(value: str | None, default: str) -> str:
    selected = (value or default).strip().lower()
    return selected if selected in VALID_PROVIDERS else default


@dataclass(frozen=True)
class AISettings:
    gemini_api_key: str
    gemini_model: str

    openai_api_key: str
    openai_model: str

    chief_provider: str
    research_provider: str
    programs_provider: str
    caretaker_provider: str

    def provider_configured(self, provider_id: str) -> bool:
        provider_id = provider_id.strip().lower()
        if provider_id == "gemini":
            return bool(self.gemini_api_key.strip())
        if provider_id == "openai":
            return bool(self.openai_api_key.strip())
        return False

    def provider_model(self, provider_id: str) -> str:
        provider_id = provider_id.strip().lower()
        if provider_id == "gemini":
            return self.gemini_model
        if provider_id == "openai":
            return self.openai_model
        raise ValueError(f"Unknown provider: {provider_id}")

    def role_provider(self, role: str) -> str:
        role = role.strip().lower()
        if role not in VALID_ROLES:
            raise ValueError(f"Unknown campus AI role: {role}")
        return getattr(self, f"{role}_provider")

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "AISettings":
        return cls(
            gemini_api_key=(values.get("GEMINI_API_KEY") or "").strip(),
            gemini_model=(values.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL).strip(),
            openai_api_key=(values.get("OPENAI_API_KEY") or "").strip(),
            openai_model=(values.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL).strip(),
            chief_provider=_provider(values.get("CHIEF_PROVIDER"), "gemini"),
            research_provider=_provider(values.get("RESEARCH_PROVIDER"), "gemini"),
            programs_provider=_provider(values.get("PROGRAMS_PROVIDER"), "openai"),
            caretaker_provider=_provider(values.get("CARETAKER_PROVIDER"), "gemini"),
        )


def get_ai_settings() -> AISettings:
    return AISettings.from_mapping(combined_environment())
