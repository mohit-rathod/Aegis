import asyncio
import json
import struct
import sys

from support_assistant.observability.logging import event
from support_assistant.voice.events import SpeechFailure


class PiperTTS:
    def __init__(self, model, timeout=30):
        self.model, self.timeout = model, timeout

    async def stream(self, text):
        for attempt in range(2):
            produced = False
            stream = self._once(text)
            try:
                async for item in stream:
                    produced = True
                    yield item
                return
            except SpeechFailure as exc:
                if produced or attempt or str(exc) == "tts_model_missing":
                    raise
                event("tts_retry", attempt=attempt + 1)
            finally:
                await stream.aclose()

    async def _once(self, text):
        if (
            not self.model.is_file()
            or not self.model.with_suffix(".onnx.json").is_file()
        ):
            raise SpeechFailure("tts_model_missing")
        process = None
        try:
            async with asyncio.timeout(self.timeout):
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "support_assistant.adapters.tts.piper_worker",
                    str(self.model),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                process.stdin.write((json.dumps({"text": text}) + "\n").encode())
                await process.stdin.drain()
                process.stdin.close()
                while True:
                    try:
                        header = await process.stdout.readexactly(8)
                    except asyncio.IncompleteReadError as exc:
                        if exc.partial:
                            raise SpeechFailure("tts_truncated_audio") from None
                        break
                    rate, size = struct.unpack("!II", header)
                    if not 8000 <= rate <= 48000 or not 0 < size <= 65536 or size % 2:
                        raise SpeechFailure("tts_invalid_audio")
                    yield rate, await process.stdout.readexactly(size)
                if await process.wait():
                    raise SpeechFailure("tts_worker_failed")
        except TimeoutError:
            raise SpeechFailure("tts_deadline") from None
        except asyncio.IncompleteReadError:
            raise SpeechFailure("tts_truncated_audio") from None
        finally:
            if process and process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), 1)
                except TimeoutError:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    await process.wait()
