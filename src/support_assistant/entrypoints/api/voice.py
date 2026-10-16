"""Same-origin authenticated duplex channel; credentials never appear in URLs."""

import asyncio
import json
import math
import secrets
import struct
import time

from fastapi import WebSocket, WebSocketDisconnect

from support_assistant.domain.conversation import SupportError
from support_assistant.observability.logging import event
from support_assistant.voice.coordinator import VoiceCoordinator


class SocketTransport:
    def __init__(self, socket):
        self.socket = socket
        self.lock = asyncio.Lock()
        self.connected = True

    async def send(self, packet):
        if not self.connected:
            return
        async with self.lock:
            try:
                await asyncio.wait_for(self.socket.send_json(packet), 5)
            except Exception:
                self.connected = False
                raise


async def voice_socket(socket: WebSocket, session_id: str):
    runtime = socket.app.state.runtime
    # Browser requests must originate from this host; CLI clients may omit Origin.
    origin = socket.headers.get("origin")
    expected = (
        "https://" if socket.url.scheme == "wss" else "http://"
    ) + socket.headers.get("host", "")
    if origin and origin != expected:
        await socket.close(code=1008)
        return
    await socket.accept()
    transport = SocketTransport(socket)
    coordinator = None
    reserved = False
    try:
        packet = await asyncio.wait_for(socket.receive_text(), 5)
        if len(packet) > 4096:
            raise ValueError("Invalid authentication")
        auth = json.loads(packet)
        token = auth.get("token", "")
        identity = None
        if not isinstance(token, str):
            raise ValueError("Invalid authentication")
        for candidate, key in [
            ("customer-a", runtime.settings.demo_a_token),
            ("customer-b", runtime.settings.demo_b_token),
        ]:
            if key and secrets.compare_digest(key.encode(), token.encode()):
                identity = candidate
        if not identity:
            await socket.close(code=1008)
            return
        if len(session_id) != 32 or any(
            c not in "0123456789abcdef" for c in session_id
        ):
            await socket.close(code=1008)
            return
        session = await runtime.store.get(session_id, identity)
        if session.state == "terminated":
            await transport.send({"type": "closed", "reason": "session_terminated"})
            return
        resources = runtime.voice
        if resources.connections >= runtime.settings.voice.max_connections:
            await socket.close(code=1013)
            return
        resources.connections += 1
        reserved = True
        coordinator = VoiceCoordinator(
            runtime, identity, session_id, transport, resources
        )
        await coordinator.start()
        # Capture is real-time: reject floods instead of accumulating stale audio.
        budget = 32.0
        last = time.monotonic()
        while not coordinator.closed:
            try:
                message = await asyncio.wait_for(socket.receive(), 90)
            except TimeoutError:
                await transport.send(
                    {"type": "error", "message": "Connection idle. Please reconnect."}
                )
                break
            if message["type"] == "websocket.disconnect":
                break
            raw = message.get("bytes")
            if raw is not None:
                if len(raw) != 1032:
                    raise ValueError("Invalid PCM frame")
                now = time.monotonic()
                budget = min(32.0, budget + (now - last) * 40) - 1
                last = now
                if budget < 0:
                    raise ValueError("Audio sent faster than real time")
                timestamp = struct.unpack("<d", raw[:8])[0]
                if not math.isfinite(timestamp) or timestamp < 0:
                    raise ValueError("Invalid frame timestamp")
                await coordinator.frame(raw[8:], timestamp)
                continue
            text = message.get("text", "")
            if len(text) > 8192:
                raise ValueError("Message too large")
            data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError("Invalid control message")
            kind = data.get("type")
            if kind == "text":
                # Server generates IDs: callers cannot forge another audio utterance.
                await coordinator.text(data.get("text"))
            elif kind == "voice_start":
                try:
                    await coordinator.enable()
                except Exception:
                    event("voice_setup_failed", category="models_or_dependencies")
                    await transport.send(
                        {
                            "type": "error",
                            "message": "Voice could not start. Install voice dependencies and run scripts/setup_voice.py. Text input is available.",
                        }
                    )
            elif kind == "voice_stop":
                await coordinator.disable()
            elif kind == "audio_ack":
                if isinstance(data.get("sequence"), int):
                    await coordinator.playback.acknowledge(
                        data.get("playback_id"), data["sequence"]
                    )
            elif kind == "playback_stopped":
                coordinator.playback.acknowledge_stop(
                    str(data.get("playback_id", ""))[:64]
                )
                event(
                    "playback_cancel_ack",
                    session_id=session_id,
                    playback_id=str(data.get("playback_id", ""))[:64],
                )
            elif kind == "latency":
                value = data.get("value_ms")
                if (
                    isinstance(value, (float, int))
                    and math.isfinite(value)
                    and 0 <= value <= 120000
                ):
                    event(
                        "voice_latency",
                        session_id=session_id,
                        metric="capture_to_scheduled_audio_ms",
                        value=round(value, 2),
                        mode="client_reported",
                        playback_id=str(data.get("playback_id", ""))[:64],
                    )
            elif kind == "ping":
                await transport.send({"type": "pong"})
            elif kind == "close":
                break
    except (WebSocketDisconnect, SupportError):
        pass
    except (ValueError, TimeoutError, KeyError, TypeError):
        if transport.connected:
            try:
                await transport.send(
                    {
                        "type": "error",
                        "message": "Invalid or timed-out channel request.",
                    }
                )
            except Exception:
                pass
    except Exception as exc:
        event("voice_connection_failed", category=type(exc).__name__)
    finally:
        transport.connected = False
        if coordinator:
            await coordinator.aclose()
        if reserved:
            runtime.voice.connections -= 1
        try:
            await socket.close()
        except Exception:
            pass
