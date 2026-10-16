import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

from support_assistant.config import Settings
from support_assistant.domain.conversation import Turn
from support_assistant.domain.evidence import Hit
from support_assistant.rag.documents import load_documents
from tests.fakes.support import FakeLLM

ROOT = Path(__file__).resolve().parents[2]


class UnifiedConfigTests(unittest.TestCase):
    def test_existing_environment_names_are_preserved(self):
        env = {
            "GROQ_API_KEY": "dummy-config-key",
            "GROQ_MODEL": "chat-model",
            "AEGIS_REDIS_URL": "redis://127.0.0.1:6379/2",
            "AEGIS_REDIS_PREFIX": "configured",
            "AEGIS_DEMO_AS_OF": "2026-10-16",
            "AEGIS_TOP_K_DOCUMENTS": "2",
        }
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.dict(os.environ, env, clear=True),
        ):
            original = Path.cwd()
            try:
                os.chdir(temp)
                settings = Settings.from_env()
            finally:
                os.chdir(original)
        self.assertEqual(settings.groq_model, "chat-model")
        self.assertEqual(settings.prefix, "configured")
        self.assertEqual(settings.top_k_documents, 2)
        self.assertEqual(settings.demo_as_of, "2026-10-16")
        self.assertNotIn("dummy-config-key", repr(settings))

    def test_both_console_names_point_to_same_cli(self):
        import tomllib

        project = tomllib.loads((ROOT / "pyproject.toml").read_text())
        self.assertEqual(project["project"]["name"], "aegis-support")
        scripts = project["project"]["scripts"]
        self.assertEqual(scripts["aegis-support"], scripts["aegis-rag"])


@unittest.skipUnless(os.getenv("AEGIS_TEST_REDIS_URL"), "Set AEGIS_TEST_REDIS_URL")
class UnifiedRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_runtime_handles_product_and_order(self):
        from support_assistant.bootstrap import create_runtime

        class LLM(FakeLLM):
            async def complete_json(self, system, payload):
                if "You answer questions" in system:
                    self.calls.append("generation")
                    return {
                        "status": "answer",
                        "claims": [
                            {
                                "text": "Pure Plus uses AF-P1.",
                                "citations": ["AEGIS-KB-002"],
                            }
                        ],
                    }
                return await super().complete_json(system, payload)

        llm = LLM()
        llm.route = "product_question"
        documents = load_documents(ROOT / "data/knowledge_base")
        doc = next(d for d in documents if d.document_id == "AEGIS-KB-002")
        retriever = Mock()
        retriever.retrieve.return_value = [Hit(doc, 0.8, ("AEGIS-KB-002:001",))]
        prefix = "aegis-unified-test-" + uuid.uuid4().hex
        settings = Settings(
            kb_dir=ROOT / "data/knowledge_base",
            fixture_path=ROOT / "data/fixtures/orders.json",
            redis_url=os.environ["AEGIS_TEST_REDIS_URL"],
            prefix=prefix,
            groq_key="dummy",
            groq_model="test",
            demo_as_of="2026-10-16",
        )
        with (
            patch(
                "support_assistant.bootstrap.build_retriever", return_value=retriever
            ),
            patch("support_assistant.bootstrap.GroqClient", return_value=llm),
        ):
            runtime = await create_runtime(settings)
        try:
            self.assertIs(runtime.settings, settings)
            session = await runtime.store.create("customer-a")
            product = await runtime.service.handle(
                "customer-a",
                session.session_id,
                Turn(turn_id="product", text="Which filter fits Pure Plus?"),
            )
            self.assertEqual(product.status, "answer")
            self.assertIn("AF-P1", product.answer)
            self.assertEqual(llm.calls, ["input", "router", "generation", "output"])
            llm.route = "order_status"
            order = await runtime.service.handle(
                "customer-a",
                session.session_id,
                Turn(turn_id="order", text="Where is AEG-1001?"),
            )
            self.assertEqual(order.status, "answer")
            self.assertIn("in_transit", order.answer)
        finally:
            keys = [k async for k in runtime.redis.scan_iter(match=prefix + ":*")]
            if keys:
                await runtime.redis.delete(*keys)
            await runtime.aclose()
