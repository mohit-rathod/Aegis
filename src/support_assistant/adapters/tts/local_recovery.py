import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "recovery"
RECOVERY_TEXT = {
    "stt": "I could not hear that clearly. Please try again, or type your message.",
    "tts": "Audio is temporarily unavailable. Please read the response on screen.",
    "long": "Please use a shorter message, or type your question.",
}


async def recording(kind):
    with wave.open(str(ROOT / (kind + ".wav")), "rb") as wav:
        rate = wav.getframerate()
        while pcm := wav.readframes(1024):
            yield rate, pcm
