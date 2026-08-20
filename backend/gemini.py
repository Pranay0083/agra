"""Gemini access layer: structured chat completions + embeddings, both wrapped
in Tenacity exponential-backoff retries (max 3 attempts)."""
import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

import config
from schemas import ReviewDraft

logger = logging.getLogger(__name__)

GEN_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
EMBED_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"

RETRYABLE = (httpx.HTTPError, httpx.TimeoutException, ConnectionError, TimeoutError, RuntimeError)


class TransientLLMError(RuntimeError):
    pass


def _json_schema() -> Dict[str, Any]:
    """Gemini-compatible JSON schema mirroring the Pydantic ReviewDraft model."""
    sev = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
    cat = ["SECURITY", "LOGIC", "MEMORY", "QUALITY"]
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "risk_score": {"type": "integer"},
            "comments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "line": {"type": "integer"},
                        "severity": {"type": "string", "enum": sev},
                        "category": {"type": "string", "enum": cat},
                        "title": {"type": "string"},
                        "rationale": {"type": "string"},
                        "cwe": {"type": "string"},
                        "owasp": {"type": "string"},
                        "rule_id": {"type": "string"},
                        "suggested_code": {"type": "string"},
                        "policy_citation": {"type": "string"},
                    },
                    "required": ["file_path", "line", "severity", "category", "title", "rationale"],
                },
            },
        },
        "required": ["summary", "risk_score", "comments"],
    }


class GeminiClient:
    def __init__(self):
        self.model = config.GEMINI_MODEL
        self.embed_model = config.GEMINI_EMBED_MODEL
        self.key = config.GOOGLE_API_KEY
        self.retries = 0

    @property
    def configured(self) -> bool:
        return bool(self.key)

    async def _post(self, url: str, payload: Dict[str, Any], timeout: float = 120.0) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, params={"key": self.key}, json=payload)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise TransientLLMError(f"Gemini transient {resp.status_code}: {resp.text[:200]}")
            if resp.status_code >= 400:
                raise ValueError(f"Gemini error {resp.status_code}: {resp.text[:400]}")
            return resp.json()

    async def _with_retry(self, coro_factory, attempts: int = 3):
        local_retry = -1
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type((TransientLLMError,) + RETRYABLE),
                wait=wait_exponential(multiplier=1, min=1, max=8),
                stop=stop_after_attempt(attempts),
                reraise=True,
            ):
                with attempt:
                    local_retry += 1
                    result = await coro_factory()
            self.retries += max(local_retry, 0)
            return result
        except RetryError as exc:  # pragma: no cover
            self.retries += attempts - 1
            raise exc

    async def generate_review(self, prompt: str) -> Tuple[Optional[ReviewDraft], Dict[str, Any]]:
        """Returns (parsed_draft_or_None, meta{usage, raw_text, parse_error})."""
        if not self.configured:
            raise ValueError("GOOGLE_API_KEY is not configured")

        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.15,
                "responseMimeType": "application/json",
                "responseSchema": _json_schema(),
                "maxOutputTokens": 8192,
            },
        }
        url = GEN_URL.format(model=self.model)
        data = await self._with_retry(lambda: self._post(url, payload))

        usage = data.get("usageMetadata", {}) or {}
        meta = {
            "prompt_tokens": usage.get("promptTokenCount", 0),
            "completion_tokens": usage.get("candidatesTokenCount", 0),
            "total_tokens": usage.get("totalTokenCount", 0),
            "parse_error": None,
            "raw_text": "",
        }

        text = ""
        for cand in data.get("candidates", []):
            for part in (cand.get("content") or {}).get("parts", []):
                if "text" in part:
                    text += part["text"]
        meta["raw_text"] = text[:8000]

        if not text.strip():
            meta["parse_error"] = "Model returned an empty response body."
            return None, meta

        import json

        try:
            draft = ReviewDraft.model_validate(json.loads(text))
            return draft, meta
        except Exception as exc:  # noqa: BLE001 - fed back into the self-correction loop
            meta["parse_error"] = str(exc)[:1200]
            return None, meta

    async def embed(self, text: str) -> List[float]:
        if not self.configured:
            raise ValueError("GOOGLE_API_KEY is not configured")
        url = EMBED_URL.format(model=self.embed_model)
        payload = {
            "model": f"models/{self.embed_model}",
            "content": {"parts": [{"text": text[:8000]}]},
            "outputDimensionality": config.EMBED_DIM,
        }
        data = await self._with_retry(lambda: self._post(url, payload, timeout=60.0))
        return data.get("embedding", {}).get("values", [])

    async def embed_many(self, texts: List[str]) -> List[List[float]]:
        return await asyncio.gather(*[self.embed(t) for t in texts])

    async def ping(self) -> Dict[str, Any]:
        if not self.configured:
            return {"ok": False, "detail": "GOOGLE_API_KEY missing"}
        try:
            url = GEN_URL.format(model=self.model)
            await self._post(url, {"contents": [{"parts": [{"text": "ping"}]}],
                                   "generationConfig": {"maxOutputTokens": 8}}, timeout=25.0)
            return {"ok": True, "detail": self.model}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": str(exc)[:200]}


def estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    return round(
        (prompt_tokens / 1_000_000) * config.PRICE_IN
        + (completion_tokens / 1_000_000) * config.PRICE_OUT,
        6,
    )


gemini = GeminiClient()
