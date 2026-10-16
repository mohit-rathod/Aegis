import asyncio
import json

import httpx

from support_assistant.domain.errors import ProviderError


class GroqClient:
    def __init__(
        self,
        key,
        model,
        timeout=20,
        max_tokens=4096,
        max_concurrency=16,
        transport=None,
    ):
        if not key or not model:
            raise ValueError("Set GROQ_API_KEY and GROQ_MODEL")
        if "whisper" in model.lower():
            raise ValueError(
                "GROQ_MODEL must be a chat model; use GROQ_STT_MODEL for Whisper"
            )
        self.model, self.max_tokens = model, max_tokens
        self.limit = asyncio.Semaphore(max_concurrency)
        self.client = httpx.AsyncClient(
            base_url="https://api.groq.com/openai/v1/",
            headers={"Authorization": f"Bearer {key}"},
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(
                max_connections=max_concurrency,
                max_keepalive_connections=max_concurrency,
            ),
            follow_redirects=False,
            transport=transport,
        )

    async def chat(self, messages, tools=None, force_tool=False):
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_completion_tokens": self.max_tokens,
        }
        if "gpt-oss" in self.model:
            payload["reasoning_effort"] = "low"
        if tools is not None:
            payload.update(
                tools=tools,
                tool_choice="required" if force_tool else "auto",
                parallel_tool_calls=False,
            )
        else:
            payload["response_format"] = {"type": "json_object"}
        try:
            async with self.limit:
                response = await self.client.post("chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            choice = data["choices"][0]
            if choice.get("finish_reason") == "length":
                raise ProviderError("provider_token_limit")
            if not isinstance(choice["message"], dict):
                raise ValueError()
            return choice["message"]
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"groq_http_{exc.response.status_code}") from None
        except httpx.TimeoutException:
            raise ProviderError("groq_timeout") from None
        except httpx.RequestError:
            raise ProviderError("groq_network_error") from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError("groq_invalid_response") from None

    async def complete_json(self, system, payload):
        result = await self.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload)},
            ]
        )
        try:
            body = json.loads(result["content"])
            if not isinstance(body, dict):
                raise ValueError()
            return body
        except (ValueError, KeyError, TypeError):
            raise ProviderError("groq_invalid_json") from None

    async def aclose(self):
        await self.client.aclose()
