import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient

from support_assistant.config import Settings
from support_assistant.domain.conversation import Session, SupportError
from support_assistant.entrypoints.api.app import app
from tests.fakes.audio import components


class Store:
    async def create(self, identity):
        return Session(session_id="a" * 32, customer_id=identity)

    async def get(self, sid, identity):
        if identity != "customer-a":
            raise SupportError("session_not_available")
        return await self.create(identity)


class ChannelTests(unittest.TestCase):
    def setUp(self):
        runtime, resources, _ = components()
        runtime.settings = Settings(demo_a_token="demo-a", demo_b_token="demo-b")
        runtime.store = Store()
        runtime.voice = resources
        resources.connections = 0
        self.runtime = runtime

        @asynccontextmanager
        async def lifespan(application):
            application.state.runtime = runtime
            yield

        self.patch = patch.object(app.router, "lifespan_context", lifespan)
        self.patch.start()
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.patch.stop()

    def test_frontend_and_worklet_served(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Send text", response.text)
        self.assertIn("Start voice", response.text)
        self.assertEqual(self.client.get("/assets/capture-worklet.js").status_code, 200)

    def test_text_uses_shared_service_over_authenticated_socket(self):
        with self.client.websocket_connect(
            "/sessions/" + "a" * 32 + "/channel"
        ) as socket:
            socket.send_json({"token": "demo-a"})
            self.assertEqual(socket.receive_json()["type"], "ready")
            socket.send_json({"type": "text", "text": "Where is my order?"})
            while True:
                packet = socket.receive_json()
                if packet["type"] == "response":
                    break
            self.assertEqual(packet["answer"], "Validated answer.")
            self.assertEqual(self.runtime.service.turns[0].channel, "text")
        self.assertEqual(self.runtime.voice.connections, 0)

    def test_wrong_token_rejected(self):
        from starlette.websockets import WebSocketDisconnect

        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect(
                "/sessions/" + "a" * 32 + "/channel"
            ) as socket:
                socket.send_json({"token": "wrong"})
                socket.receive_json()
        self.assertEqual(self.runtime.service.turns, [])

    def test_other_customer_cannot_attach_to_session(self):
        from starlette.websockets import WebSocketDisconnect

        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect(
                "/sessions/" + "a" * 32 + "/channel"
            ) as socket:
                socket.send_json({"token": "demo-b"})
                socket.receive_json()
        self.assertEqual(self.runtime.service.turns, [])

    def test_cross_origin_socket_rejected(self):
        from starlette.websockets import WebSocketDisconnect

        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect(
                "/sessions/" + "a" * 32 + "/channel",
                headers={"origin": "https://untrusted.example"},
            ):
                pass

    def test_invalid_audio_frame_does_not_dispatch(self):
        with self.client.websocket_connect(
            "/sessions/" + "a" * 32 + "/channel"
        ) as socket:
            socket.send_json({"token": "demo-a"})
            while socket.receive_json()["type"] != "history":
                pass
            socket.send_bytes(b"bad")
            while True:
                packet = socket.receive_json()
                if packet["type"] == "error":
                    break
        self.assertEqual(self.runtime.service.turns, [])
