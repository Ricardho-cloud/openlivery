"""Chat completions over raw HTTP against an OpenAI-compatible endpoint.

Every model is reached through the same ``/chat/completions`` dialect, which
is what xAI (and other OpenAI-compatible hosts) speak. The usage block is
recorded when the provider reports it; otherwise Reports prices from the catalog.
"""

from dataclasses import dataclass, field

import httpx
from fastapi import HTTPException


# Optional attribution headers (harmless on xAI; used by some compatible hosts).
APP_HEADERS = {"HTTP-Referer": "https://github.com/Ricardho-cloud/openlivery", "X-Title": "OpenLivery"}


@dataclass
class Usage:
    """Token and cost accounting for one or more provider calls."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float | None = None

    def __add__(self, other: "Usage") -> "Usage":
        cost = None if self.cost_usd is None and other.cost_usd is None else (self.cost_usd or 0.0) + (other.cost_usd or 0.0)
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cached_tokens + other.cached_tokens,
            self.reasoning_tokens + other.reasoning_tokens,
            cost,
        )


@dataclass
class Completion:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: list[dict] | None = None
    cost_usd: float | None = None
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    served_by: str = ""
    duration_ms: int | None = None
    generation_id: str = ""
    attachments: list = field(default_factory=list)


_SAMPLING_PARAM_HINTS = ("temperature", "max_tokens", "max_output_tokens", "max_completion_tokens", "unsupported", "not supported")


async def chat_completion(
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Completion:
    try:
        return await _chat_completions(base_url, api_key, model, messages, temperature, max_tokens)
    except HTTPException:
        raise
    except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not get a valid response from the AI provider. Check the API key and the model.",
        ) from exc


def chat_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


def auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", **APP_HEADERS}


def sampling_params(temperature: float | None, max_tokens: int | None) -> dict:
    sampling: dict = {}
    if temperature is not None:
        sampling["temperature"] = temperature
    if max_tokens is not None:
        sampling["max_tokens"] = max_tokens
    return sampling


async def _chat_completions(base_url, api_key, model, messages, temperature, max_tokens) -> Completion:
    payload = {
        "model": model,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        "usage": {"include": True},
    }
    data = await _post_json(chat_url(base_url), auth_headers(api_key), payload, sampling_params(temperature, max_tokens))
    return completion_from(extract_chat_text(data), read_usage(data), data)


def completion_from(text: str, usage: Usage, data: dict, tool_calls: list[dict] | None = None) -> Completion:
    return Completion(
        text,
        usage.input_tokens,
        usage.output_tokens,
        tool_calls=tool_calls,
        cost_usd=usage.cost_usd,
        cached_tokens=usage.cached_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        served_by=str(data.get("provider") or ""),
        generation_id=str(data.get("id") or ""),
    )


def read_usage(data: dict) -> Usage:
    usage = data.get("usage") or {}
    prompt_details = usage.get("prompt_tokens_details") or {}
    completion_details = usage.get("completion_tokens_details") or {}
    cost_details = usage.get("cost_details") or {}
    cost = usage.get("cost")
    upstream = cost_details.get("upstream_inference_cost")
    cost_usd = None if cost is None and upstream is None else float(cost or 0) + float(upstream or 0)
    if not cost and upstream is None:
        cost_usd = None
    return Usage(
        input_tokens=int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
        cached_tokens=int(prompt_details.get("cached_tokens") or 0),
        reasoning_tokens=int(completion_details.get("reasoning_tokens") or 0),
        cost_usd=cost_usd,
    )


async def _post_json(url: str, headers: dict, base_payload: dict, sampling: dict) -> dict:
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(url, headers=headers, json={**base_payload, **sampling})
        if sampling and response.status_code >= 400 and _is_sampling_param_error(response):
            response = await client.post(url, headers=headers, json=base_payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"The AI provider responded with an error: {_safe_provider_error(response)}")
    return response.json()


def chat_message(data: dict) -> dict:
    return data["choices"][0].get("message") or {}


def extract_chat_text(data: dict) -> str:
    content = chat_message(data).get("content")
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text")
    text = (content or "").strip()
    if not text:
        raise ValueError("empty response")
    return text


def _is_sampling_param_error(response: httpx.Response) -> bool:
    message = _safe_provider_error(response).lower()
    if "credits" in message:
        return False
    return any(hint in message for hint in _SAMPLING_PARAM_HINTS)


def _safe_provider_error(response: httpx.Response) -> str:
    try:
        data = response.json()
        message = data.get("error", {}).get("message") or data.get("message")
        if isinstance(message, str):
            return message[:500]
    except ValueError:
        pass
    return f"HTTP {response.status_code}"


async def test_provider(provider: str, base_url: str, api_key: str) -> dict:
    headers = {"Authorization": f"Bearer {api_key}", **APP_HEADERS}
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.get(f"{base_url.rstrip('/')}/key", headers=headers)
            if response.status_code == 404:
                response = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
        if response.status_code < 400:
            try:
                payload = response.json()
                info = payload.get("data") or {}
            except (ValueError, AttributeError):
                info = {}
            remaining = info.get("limit_remaining") if isinstance(info, dict) else None
            message = "Key verified."
            if isinstance(remaining, (int, float)):
                message = f"Key verified. Remaining credit: ${remaining:,.2f}."
            return {"ok": True, "message": message, "models": []}
        raise HTTPException(status_code=502, detail=f"Could not verify the key: {_safe_provider_error(response)}")
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not connect to the provider") from exc
