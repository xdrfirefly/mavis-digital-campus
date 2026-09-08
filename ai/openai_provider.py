from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request

from .provider import GenerationResult


class OpenAIProvider:
    provider_name = "openai"
    endpoint = "https://api.openai.com/v1/responses"

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

    def _request_from_payload(self, payload: dict) -> urllib.request.Request:
        return urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mavis-Digital-Campus/0.7.5.1",
            },
        )

    def _build_request(self, prompt: str, max_output_tokens: int) -> urllib.request.Request:
        payload = {
            "model": self.model,
            "input": prompt,
            "max_output_tokens": max(1, min(int(max_output_tokens), 4096)),
            "reasoning": {"effort": "none"},
            "store": False,
        }
        return self._request_from_payload(payload)

    def _build_structured_request(
        self,
        prompt: str,
        *,
        schema_name: str,
        schema: dict,
        max_output_tokens: int,
    ) -> urllib.request.Request:
        payload = {
            "model": self.model,
            "input": prompt,
            "max_output_tokens": max(1, min(int(max_output_tokens), 4096)),
            "reasoning": {"effort": "none"},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
                "verbosity": "low",
            },
            "store": False,
        }
        return self._request_from_payload(payload)

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

    @staticmethod
    def _extract_text(data: dict) -> str:
        # Some API/SDK representations expose a convenience output_text field.
        direct = data.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()

        text_parts: list[str] = []
        output = data.get("output") or []

        for item in output:
            if not isinstance(item, dict):
                continue

            content = item.get("content") or []
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") in {"output_text", "text"} and part.get("text"):
                    text_parts.append(str(part["text"]))

        return "".join(text_parts).strip()

    def _perform_request(self, request: urllib.request.Request) -> dict:
        raw = ""

        for attempt in range(1, self.max_attempts + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read().decode("utf-8")
                break

            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    error_data = json.loads(exc.read().decode("utf-8"))
                    detail = (
                        error_data.get("error", {}).get("message")
                        or error_data.get("message")
                        or ""
                    )
                except Exception:
                    pass

                suffix = f": {detail}" if detail else ""
                raise RuntimeError(f"OpenAI API returned HTTP {exc.code}{suffix}") from exc

            except Exception as exc:
                if not self._is_timeout_error(exc):
                    if isinstance(exc, urllib.error.URLError):
                        reason = getattr(exc, "reason", exc)
                        raise RuntimeError(f"Could not reach OpenAI API: {reason}") from exc
                    raise

                if attempt >= self.max_attempts:
                    raise RuntimeError(
                        f"OpenAI did not finish responding within {int(self.timeout_seconds)} seconds "
                        f"after {self.max_attempts} attempts. This is usually a temporary network/model delay."
                    ) from exc

                if self.retry_delay_seconds:
                    time.sleep(self.retry_delay_seconds)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenAI returned a response the campus could not read.") from exc

        if not isinstance(data, dict):
            raise RuntimeError("OpenAI returned an unexpected response shape.")

        status = data.get("status")
        if status == "incomplete":
            details = data.get("incomplete_details") or {}
            reason = details.get("reason") if isinstance(details, dict) else None
            suffix = f" Reason: {reason}." if reason else ""
            raise RuntimeError(
                "OpenAI stopped before completing the response."
                + suffix
                + " Programs will not accept a partial deliverable."
            )
        if status == "failed":
            error = data.get("error") or {}
            detail = error.get("message") if isinstance(error, dict) else None
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"OpenAI response failed{suffix}")

        return data

    def _generation_from_data(self, data: dict, prompt: str) -> GenerationResult:
        text = self._extract_text(data)
        if not text:
            status = data.get("status") if isinstance(data, dict) else None
            suffix = f" Response status: {status}." if status else ""
            raise RuntimeError(f"OpenAI returned no readable text.{suffix}")

        return GenerationResult(
            provider=self.provider_name,
            model=self.model,
            text=text,
            input_chars=len(prompt),
            output_chars=len(text),
        )

    def generate_structured(
        self,
        prompt: str,
        *,
        schema_name: str,
        schema: dict,
        max_output_tokens: int = 2400,
    ) -> GenerationResult:
        """Generate strict JSON using the Responses API Structured Outputs feature."""
        if not self.api_key:
            raise RuntimeError("OpenAI API key is not configured.")
        if not prompt.strip():
            raise ValueError("Prompt cannot be empty.")
        if not schema_name.strip():
            raise ValueError("Structured output schema name cannot be empty.")
        if not isinstance(schema, dict):
            raise ValueError("Structured output schema must be a JSON-schema object.")

        request = self._build_structured_request(
            prompt,
            schema_name=schema_name,
            schema=schema,
            max_output_tokens=max_output_tokens,
        )
        data = self._perform_request(request)
        return self._generation_from_data(data, prompt)

    def generate_text(self, prompt: str, *, max_output_tokens: int = 120) -> GenerationResult:
        if not self.api_key:
            raise RuntimeError("OpenAI API key is not configured.")
        if not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        request = self._build_request(prompt, max_output_tokens)
        data = self._perform_request(request)
        return self._generation_from_data(data, prompt)
