import json
import httpx
from support_assistant.domain.errors import ProviderError

class GroqJsonLLM:
    def __init__(self, api_key: str, model: str, timeout: float = 20):
        if not api_key or not model:
            raise ValueError("Set GROQ_API_KEY and GROQ_MODEL in .env")
        self.model = model
        self.client = httpx.Client(base_url="https://api.groq.com/openai/v1/",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(timeout), follow_redirects=False)

    def complete_json(self, system: str, payload: dict) -> dict:
        try:
            response = self.client.post("chat/completions", json={
                "model": self.model,
                "messages": [{"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(payload)}],
                "temperature": 0,
                "max_completion_tokens": 4096,
                "response_format": {"type": "json_object"},
            })
            response.raise_for_status()
            body = response.json()
            if body["choices"][0].get("finish_reason") == "length":
                raise ProviderError(
                    "Groq output hit its token limit before completion"
                )
            content = body["choices"][0]["message"]["content"]
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ValueError("Expected JSON object")
            return result
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code

            hints = {
                400: "Check model support for JSON mode and request parameters",
                401: "Check GROQ_API_KEY",
                403: "Check account permissions and model access",
                404: "Check GROQ_MODEL availability",
                429: "Groq rate limit or quota reached",
            }

            hint = hints.get(status, "Groq service returned an HTTP error")
            raise ProviderError(f"Groq HTTP {status}: {hint}") from None

        except httpx.TimeoutException:
            raise ProviderError("Groq request timed out") from None

        except httpx.RequestError:
            raise ProviderError("Groq network connection failed") from None

        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError(
                "Groq returned invalid JSON or an unexpected response structure"
            ) from None

    def close(self):
        self.client.close()
