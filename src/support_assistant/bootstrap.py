import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from zoneinfo import ZoneInfo

from support_assistant.adapters.cache.redis_cache import RedisClassifierCache
from support_assistant.adapters.embeddings.sentence_transformer import (
    SentenceTransformerEmbedder,
)
from support_assistant.adapters.groq.client import GroqClient
from support_assistant.adapters.persistence.fixture_orders import FixtureOrders
from support_assistant.adapters.persistence.redis_sessions import RedisSessionStore
from support_assistant.adapters.retrieval.numpy_index import NumpyIndex
from support_assistant.agents.human_escalation import HumanEscalationAgent
from support_assistant.agents.order_status import OrderStatusAgent
from support_assistant.agents.product_question import ProductQuestionAgent
from support_assistant.application.guarded_dispatcher import GuardedDispatcher
from support_assistant.application.response_service import ResponseService
from support_assistant.application.support_service import SupportService
from support_assistant.config import Settings
from support_assistant.domain.safety import ApprovalAuthority
from support_assistant.observability.logging import event
from support_assistant.rag.documents import load_documents
from support_assistant.rag.retriever import Retriever
from support_assistant.routing.classifier import Classifier
from support_assistant.safety.regex_guard import RegexGuard
from support_assistant.tools.executor import ToolExecutor


class Runtime:
    def __init__(self, settings, redis, llm, pool, service, store, cache, retriever):
        self.settings, self.redis, self.llm, self.pool = settings, redis, llm, pool
        self.service, self.store, self.cache = service, store, cache
        self.retriever = retriever
        from support_assistant.voice.resources import VoiceResources

        self.voice = VoiceResources(settings)

    async def aclose(self):
        await self.voice.aclose()
        await self.llm.aclose()
        await self.redis.aclose()
        self.pool.shutdown(wait=False, cancel_futures=True)


def build_retriever(settings):
    embedder = SentenceTransformerEmbedder(
        settings.embedding_model, settings.embedding_revision
    )
    return Retriever(
        NumpyIndex.load(settings.index_dir),
        load_documents(settings.kb_dir),
        embedder,
        settings,
    )


async def create_runtime(settings=None):
    from redis.asyncio import Redis

    settings = (
        settings or Settings.from_env()
    )  # Load .env before HF/model initialization.
    redis = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=3,
        socket_connect_timeout=3,
        max_connections=128,
    )
    pool = ThreadPoolExecutor(
        max_workers=settings.embedding_workers, thread_name_prefix="aegis-embedding"
    )
    llm = None
    try:
        await redis.ping()
        llm = GroqClient(
            settings.groq_key,
            settings.groq_model,
            settings.provider_timeout,
            max_concurrency=settings.provider_concurrency,
        )
        retriever = await asyncio.to_thread(build_retriever, settings)
        authority = ApprovalAuthority(settings.turn_timeout + 10)
        store = RedisSessionStore(
            redis,
            settings.prefix,
            settings.session_ttl,
            int(settings.turn_timeout) + 15,
        )
        cache = RedisClassifierCache(
            redis,
            settings.prefix,
            settings.classifier_ttl,
            settings.classifier_max_entries,
        )
        fixed = settings.demo_as_of
        current = date.fromisoformat(fixed) if fixed else None
        today = (
            (lambda: current)
            if current
            else (lambda: datetime.now(ZoneInfo("Asia/Kolkata")).date())
        )
        executor = ToolExecutor(FixtureOrders(settings.fixture_path), authority, today)
        handlers = {
            "product_question": ProductQuestionAgent(
                retriever, llm, authority, pool, settings.max_embedding_pending
            ),
            "order_status": OrderStatusAgent(llm, executor, authority),
            "escalate_to_human": HumanEscalationAgent(authority),
        }
        service = SupportService(
            store,
            RegexGuard(),
            llm,
            Classifier(llm, cache, settings.provider_timeout),
            GuardedDispatcher(authority, handlers),
            ResponseService(llm, executor),
            authority,
            executor,
            settings.turn_timeout,
            settings.max_active,
        )
        event(
            "runtime_ready",
            model=settings.groq_model,
            demo_clock=fixed or "system_Asia_Kolkata",
            session_backend="redis",
            max_active_per_worker=settings.max_active,
        )
        return Runtime(settings, redis, llm, pool, service, store, cache, retriever)
    except BaseException:
        if llm:
            await llm.aclose()
        await redis.aclose()
        pool.shutdown(wait=False, cancel_futures=True)
        raise
