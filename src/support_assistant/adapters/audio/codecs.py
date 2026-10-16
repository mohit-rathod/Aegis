import io
import wave

import numpy as np


def pcm_to_wav(pcm, rate=16000):
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return output.getvalue()


def wav_to_pcm(path):
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError("Use mono int16 WAV")
        rate = wav.getframerate()
        pcm = wav.readframes(wav.getnframes())
    if rate != 16000:
        data = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
        data = np.interp(
            np.arange(int(len(data) * 16000 / rate)) * rate / 16000,
            np.arange(len(data)),
            data,
        )
        pcm = np.clip(data, -32768, 32767).astype("<i2").tobytes()
    return pcm
