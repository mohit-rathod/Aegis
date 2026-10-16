import asyncio

from support_assistant.adapters.audio.silero_vad import SileroVAD
from support_assistant.adapters.groq.speech_to_text import GroqSpeechToText
from support_assistant.adapters.tts.piper import PiperTTS
from support_assistant.application.ports.speech_to_text import SpeechToText
from support_assistant.application.ports.text_to_speech import TextToSpeech


class VoiceResources:
    """One provider pool per application; recurrent VAD state is per call."""

    def __init__(self, settings):
        self.settings = settings
        self.session = None
        self.lock = asyncio.Lock()
        self.connections = 0
        self.mode = "live_groq_whisper_chat_piper"
        self.faults = None
        self.capacity = asyncio.Semaphore(settings.voice.provider_concurrency)
        self.stt: SpeechToText = GroqSpeechToText(
            settings.groq_key,
            settings.groq_stt_model,
            settings.voice.language,
            settings.voice.stt_timeout,
        )
        self.tts: TextToSpeech = PiperTTS(
            settings.voice.tts_model, settings.voice.tts_timeout
        )

    async def detector(self):
        async with self.lock:
            if self.session is None:
                self.session = await asyncio.wait_for(
                    asyncio.to_thread(
                        SileroVAD.load_session, self.settings.voice.vad_model
                    ),
                    15,
                )
        return SileroVAD(self.session)

    async def aclose(self):
        await self.stt.aclose()
