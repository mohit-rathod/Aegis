import asyncio
import time

import httpx

from support_assistant.adapters.audio.codecs import pcm_to_wav
from support_assistant.observability.logging import event
from support_assistant.voice.events import SpeechFailure


class GroqSpeechToText:
    def __init__(self, key, model, language="en", timeout=12, client=None):
        self.key, self.model, self.language, self.timeout = (
            key,
            model,
            language,
            timeout,
        )
        self.client = client or httpx.AsyncClient(timeout=timeout)
        self.owned = client is None

    async def transcribe(self, pcm, *, fault=None):
        if not self.key:
            raise SpeechFailure("stt_credentials_missing")
        if not pcm or len(pcm) > 16000 * 2 * 61:
            raise SpeechFailure("stt_audio_invalid")
        data = {
            "model": self.model,
            "response_format": "json",
            "temperature": "0",
            "prompt": "Aegis support. Product names: Pure Mini, Pure Plus. Order references use the letters AEG followed by digits.",
        }
        if self.language:
            data["language"] = self.language
        wav = pcm_to_wav(pcm)
        started = time.monotonic()
        try:
            async with asyncio.timeout(self.timeout):
                for attempt in range(2):
                    retry_delay = 0.25
                    try:
                        if fault == "stt_transient" and attempt == 0:
                            raise httpx.ReadTimeout("injected demo timeout")
                        response = await self.client.post(
                            "https://api.groq.com/openai/v1/audio/transcriptions",
                            headers={
                                "Authorization": "Bearer "
                                + (
                                    "invalid-demo-key"
                                    if fault == "stt_auth"
                                    else self.key
                                )
                            },
                            data=data,
                            files={"file": ("utterance.wav", wav, "audio/wav")},
                        )
                        if response.status_code in (401, 403):
                            raise SpeechFailure("stt_authentication_failed")
                        if response.status_code == 429 or response.status_code >= 500:
                            if response.status_code == 429:
                                try:
                                    retry_delay = max(
                                        0.25,
                                        float(
                                            response.headers.get("retry-after", ".25")
                                        ),
                                    )
                                except ValueError:
                                    retry_delay = 0.5
                            if attempt or retry_delay > 1:
                                raise SpeechFailure("stt_unavailable")
                        elif response.is_error:
                            raise SpeechFailure("stt_request_rejected")
                        else:
                            text = response.json().get("text", "")
                            if not isinstance(text, str):
                                raise SpeechFailure("stt_invalid_response")
                            event(
                                "stt_completed",
                                attempt=attempt + 1,
                                duration_ms=round(
                                    (time.monotonic() - started) * 1000, 2
                                ),
                            )
                            return text.strip()
                    except (httpx.TransportError, ValueError):
                        if attempt:
                            raise SpeechFailure("stt_transport_failed") from None
                    event("stt_retry", attempt=attempt + 1)
                    await asyncio.sleep(retry_delay)
        except TimeoutError:
            raise SpeechFailure("stt_deadline") from None
        raise SpeechFailure("stt_unavailable")

    async def aclose(self):
        if self.owned:
            await self.client.aclose()
