from __future__ import annotations

from .config import AISettings, get_ai_settings
from .gemini_provider import GeminiProvider
from .openai_provider import OpenAIProvider


PROVIDER_LABELS = {
    "gemini": "Gemini",
    "openai": "OpenAI",
}


def provider_public_status(provider_id: str, settings: AISettings | None = None) -> dict[str, object]:
    settings = settings or get_ai_settings()
    provider_id = provider_id.strip().lower()

    return {
        "provider": PROVIDER_LABELS.get(provider_id, provider_id.title()),
        "provider_id": provider_id,
        "model": settings.provider_model(provider_id),
        "configured": settings.provider_configured(provider_id),
        "supported": provider_id in PROVIDER_LABELS,
        "key_location": ".env",
        "key_exposed": False,
    }


def public_ai_status(settings: AISettings | None = None) -> dict[str, object]:
    settings = settings or get_ai_settings()

    providers = {
        provider_id: provider_public_status(provider_id, settings)
        for provider_id in ("gemini", "openai")
    }

    return {
        "providers": providers,
        "roles": {
            "chief": settings.chief_provider,
            "research": settings.research_provider,
            "programs": settings.programs_provider,
            "caretaker": settings.caretaker_provider,
        },
        "authority": "Multi-provider routing · no automatic fallback",
        "key_location": ".env",
        "keys_exposed": False,
    }


def get_provider(provider_id: str, settings: AISettings | None = None):
    settings = settings or get_ai_settings()
    provider_id = provider_id.strip().lower()

    if provider_id == "gemini":
        if not settings.gemini_api_key:
            raise RuntimeError(
                "Gemini API key not found. Add GEMINI_API_KEY to the .env file in the campus folder."
            )
        return GeminiProvider(settings.gemini_api_key, settings.gemini_model)

    if provider_id == "openai":
        if not settings.openai_api_key:
            raise RuntimeError(
                "OpenAI API key not found. Add OPENAI_API_KEY to the .env file in the campus folder."
            )
        return OpenAIProvider(settings.openai_api_key, settings.openai_model)

    raise RuntimeError(f"AI provider '{provider_id}' is not supported.")


def get_role_provider(role: str, settings: AISettings | None = None):
    settings = settings or get_ai_settings()
    provider_id = settings.role_provider(role)
    return get_provider(provider_id, settings)


def role_provider_id(role: str, settings: AISettings | None = None) -> str:
    settings = settings or get_ai_settings()
    return settings.role_provider(role)
