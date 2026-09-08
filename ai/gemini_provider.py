from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from .provider import GenerationResult


class GeminiProvider:
    provider_name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
        max_attempts: int = 2,
        retry_delay_seconds: float = 1.25,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout_seconds = max(5.0, float(timeout_seconds))
        self.max_attempts = max(1, min(int(max_attempts), 3))
        self.retry_delay_seconds = max(0.0, float(retry_delay_seconds))

    @property
    def endpoint(self) -> str:
        model = urllib.parse.quote(self.model, safe="-_.")
        return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def _build_request(self, prompt: str, max_output_tokens: int) -> urllib.request.Request:
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max(1, min(int(max_output_tokens), 2048))},
        }
        return urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
                "User-Agent": "Mavis-Digital-Campus/0.7.3.1",
            },
        )

    @staticmethod
    def _is_timeout_error(exc: BaseException) -> bool:
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return True
        if isinstance(exc, urllib.error.URLError):
            reason = getattr(exc, "reason", None)
            if isinstance(reason, (TimeoutError, socket.timeout)):
                return True
            if "timed out" in str(reason).lower():
                return True
        return "timed out" in str(exc).lower()

    def generate_text(self, prompt: str, *, max_output_tokens: int = 120) -> GenerationResult:
        if not self.api_key:
            raise RuntimeError("Gemini API key is not configured.")
        if not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        raw = None
        last_timeout = None
        for attempt in range(1, self.max_attempts + 1):
            request = self._build_request(prompt, max_output_tokens)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read().decode("utf-8")
                break
            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    error_data = json.loads(exc.read().decode("utf-8"))
                    detail = error_data.get("error", {}).get("message") or error_data.get("message") or ""
                except Exception:
                    pass
                suffix = f": {detail}" if detail else ""
                raise RuntimeError(f"Gemini API returned HTTP {exc.code}{suffix}") from exc
            except Exception as exc:
                if not self._is_timeout_error(exc):
                    if isinstance(exc, urllib.error.URLError):
                        reason = getattr(exc, "reason", exc)
                        raise RuntimeError(f"Could not reach Gemini API: {reason}") from exc
                    raise
                last_timeout = exc
                if attempt >= self.max_attempts:
                    raise RuntimeError(
                        f"Gemini did not finish responding within {int(self.timeout_seconds)} seconds "
                        f"after {self.max_attempts} attempts. This is usually a temporary network/model delay."
                    ) from exc
                if self.retry_delay_seconds:
                    time.sleep(self.retry_delay_seconds)

        if raw is None:
            raise RuntimeError(f"Gemini request failed after {self.max_attempts} attempts.") from last_timeout

        try:
            data = json.loads(raw)
            candidates = data.get("candidates") or []
            parts = candidates[0]["content"]["parts"] if candidates else []
            text = "".join(
                str(part.get("text", ""))
                for part in parts
                if isinstance(part, dict) and part.get("text")
            ).strip()
        except Exception as exc:
            raise RuntimeError("Gemini returned a response the campus could not read.") from exc

        if not text:
            block_reason = data.get("promptFeedback", {}).get("blockReason") if isinstance(data, dict) else None
            suffix = f" ({block_reason})" if block_reason else ""
            raise RuntimeError(f"Gemini returned no text{suffix}.")

        return GenerationResult(
            provider=self.provider_name,
            model=self.model,
            text=text,
            input_chars=len(prompt),
            output_chars=len(text),
        )
