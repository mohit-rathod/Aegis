"""Optional Chromium smoke: fake microphone device, real VAD/Piper/Redis.

Run from project root after installing Playwright/Chromium and voice assets.
STT and the Groq LLM are explicit scripted substitutes. No physical mic is tested.
"""

import asyncio
import json
import os
import sys
import uuid
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


async def main():
    import uvicorn
    from playwright.async_api import async_playwright
    from redis.asyncio import Redis

    from support_assistant.config import Settings
    from support_assistant.entrypoints.api.app import app
    from support_assistant.observability.logging import configure_logging
    from support_assistant.voice.resources import VoiceResources
    from tests.fakes.support import make_service

    configure_logging()
    settings = Settings.from_env()
    settings = replace(
        settings,
        demo_a_token="browser-demo-only",
        demo_b_token="browser-other",
        redis_url=os.getenv("AEGIS_TEST_REDIS_URL", settings.redis_url),
    )
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    prefix = "aegis-browser-" + uuid.uuid4().hex
    runtime = make_service(redis, prefix, ROOT)
    runtime.settings = settings
    runtime.redis = redis
    resources = VoiceResources(settings)

    class STT:
        async def transcribe(self, pcm):
            return "Where is AEG-1001?"

    actual_stt = resources.stt
    resources.stt = STT()
    runtime.voice = resources

    @asynccontextmanager
    async def lifespan(application):
        application.state.runtime = runtime
        yield

    original = app.router.lifespan_context
    app.router.lifespan_context = lifespan
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=18080, log_level="warning", ws_max_size=16384
        )
    )
    serving = asyncio.create_task(server.serve())
    output = Path(os.getenv("AEGIS_BROWSER_OUTPUT", "var/evaluation/browser"))
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    try:
        async with asyncio.timeout(10):
            while not server.started:
                await asyncio.sleep(0.02)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                args=[
                    "--use-fake-ui-for-media-stream",
                    "--use-fake-device-for-media-stream",
                    "--use-file-for-fake-audio-capture="
                    + str(ROOT / "tests/fixtures/audio/question.wav")
                    + "%noloop",
                    "--autoplay-policy=no-user-gesture-required",
                ]
            )
            page = await browser.new_page(
                viewport={"width": 1100, "height": 1000}, permissions=["microphone"]
            )
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.goto("http://127.0.0.1:18080/")
            await page.locator("#token").fill("browser-demo-only")
            await page.locator("#connect").click()
            await page.wait_for_function("!document.getElementById('send').disabled")
            await page.locator("#text").fill("Where is AEG-1001?")
            await page.locator("#send").click()
            await page.wait_for_function(
                "document.getElementById('messages').textContent.includes('in_transit')"
            )
            await page.locator("#voice").click()
            await page.wait_for_function(
                "document.getElementById('events').textContent.includes('audio_start')",
                timeout=60000,
            )
            await page.wait_for_function(
                "document.getElementById('latency').textContent.includes('Response:')",
                timeout=60000,
            )
            await page.locator("#voice").click()
            await page.screenshot(path=str(output / "frontend-qa.png"), full_page=True)
            await page.set_viewport_size({"width": 390, "height": 844})
            overflow = await page.evaluate(
                "document.documentElement.scrollWidth > innerWidth"
            )
            assert not overflow, "Mobile viewport has horizontal overflow"
            await page.locator("#end").click()
            result = {
                "mode": "chromium_fake_microphone_scripted_stt_llm_real_vad_piper_redis",
                "physical_microphone": False,
                "page_errors": errors,
                "mobile_overflow": overflow,
                "text_and_voice_passed": True,
                "events": await page.locator("#events").inner_text(),
                "latency_label": await page.locator("#latency").inner_text(),
            }
            assert not errors, errors
            (output / "browser.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps({k: v for k, v in result.items() if k != "events"}))
            await browser.close()
    finally:
        server.should_exit = True
        await serving
        app.router.lifespan_context = original
        await actual_stt.aclose()
        keys = [key async for key in redis.scan_iter(match=prefix + ":*")]
        if keys:
            await redis.delete(*keys)
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
