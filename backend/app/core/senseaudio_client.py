import json
from typing import Any

import httpx

from app.core.config import get_settings


class SenseAudioError(RuntimeError):
    pass


class SenseAudioClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.settings = get_settings()

    async def chat_json(self, messages: list[dict], temperature: float = 0.2) -> dict:
        url = f"{self.settings.senseaudio_base_url}{self.settings.senseaudio_chat_endpoint}"
        payload = {
            "model": self.settings.senseaudio_model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(240.0, connect=20.0)) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = self._extract_error_detail(exc.response)
            raise SenseAudioError(f"SenseAudio API returned {exc.response.status_code}: {detail}") from exc
        except httpx.TimeoutException as exc:
            raise SenseAudioError("SenseAudio API request timed out") from exc
        except httpx.HTTPError as exc:
            raise SenseAudioError(f"SenseAudio API request failed: {exc}") from exc
        except ValueError as exc:
            raise SenseAudioError("SenseAudio API returned non-JSON response") from exc

        content = self._extract_message_content(data)
        return self._parse_json_content(content)

    async def test_connection(self) -> bool:
        result = await self.chat_json([
            {"role": "system", "content": "You are a JSON-only health check."},
            {"role": "user", "content": "Return {\"ok\": true}."},
        ])
        return bool(result.get("ok"))

    def _extract_message_content(self, data: dict[str, Any]) -> Any:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise SenseAudioError("SenseAudio response does not contain choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise SenseAudioError("SenseAudio response does not contain message")
        if "content" not in message:
            raise SenseAudioError("SenseAudio response does not contain message content")
        return message["content"]

    def _parse_json_content(self, content: Any) -> dict:
        if isinstance(content, dict):
            return content
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") in {"text", "output_text"} and isinstance(item.get("text"), str):
                    return self._parse_json_text(item["text"])
            raise SenseAudioError("SenseAudio message content list does not contain JSON text")
        if not isinstance(content, str):
            raise SenseAudioError("SenseAudio message content is not text")
        return self._parse_json_text(content)

    def _parse_json_text(self, text: str) -> dict:
        raw = text.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").strip()
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SenseAudioError(f"SenseAudio response is not valid JSON: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise SenseAudioError("SenseAudio response JSON must be an object")
        return parsed

    def _extract_error_detail(self, response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return response.text[:500]
        detail = data.get("error") or data.get("detail") or data
        if isinstance(detail, dict):
            return str(detail.get("message") or detail)
        return str(detail)
