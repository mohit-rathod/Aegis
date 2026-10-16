import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date,datetime
from zoneinfo import ZoneInfo
import os

from support_assistant.config import Settings
from support_assistant.config_part_a import PartASettings
from support_assistant.bootstrap import build_retriever
from support_assistant.adapters.groq.async_client import AsyncGroqClient
from support_assistant.adapters.persistence.redis_sessions import RedisSessionStore
from support_assistant.adapters.persistence.fixture_orders import FixtureOrders
from support_assistant.adapters.cache.redis_cache import RedisClassifierCache
from support_assistant.domain.safety import ApprovalAuthority
from support_assistant.routing.classifier import Classifier
from support_assistant.safety.regex_guard import RegexGuard
from support_assistant.tools.executor import ToolExecutor
from support_assistant.agents.order_status import OrderStatusAgent
from support_assistant.agents.human_escalation import HumanEscalationAgent
from support_assistant.agents.async_product_question import AsyncProductQuestionAgent
from support_assistant.application.guarded_dispatcher import GuardedDispatcher
from support_assistant.application.response_service import ResponseService
from support_assistant.application.part_a_service import PartASupportService
from support_assistant.observability.logging import event

class Runtime:
    def __init__(self,settings,part,redis,llm,pool,service,store,cache):
        self.settings,self.part,self.redis,self.llm,self.pool=settings,part,redis,llm,pool
        self.service,self.store,self.cache=service,store,cache

    async def aclose(self):
        await self.llm.aclose()
        await self.redis.aclose()
        self.pool.shutdown(wait=False,cancel_futures=True)

async def create_runtime():
    from redis.asyncio import Redis
    settings=Settings.from_env()  # Loads .env before HF imports/model initialization.
    part=PartASettings.from_env()
    redis=Redis.from_url(part.redis_url,decode_responses=True,socket_timeout=3,
        socket_connect_timeout=3,max_connections=128)
    pool=ThreadPoolExecutor(max_workers=part.embedding_workers,thread_name_prefix="aegis-embedding")
    llm=None
    try:
        await redis.ping()
        llm=AsyncGroqClient(settings.groq_key,settings.groq_model,settings.provider_timeout,
            max_concurrency=part.provider_concurrency)
        retriever=await asyncio.to_thread(build_retriever,settings)
        authority=ApprovalAuthority(part.turn_timeout+10)
        store=RedisSessionStore(redis,part.prefix,part.session_ttl,int(part.turn_timeout)+15)
        cache=RedisClassifierCache(redis,part.prefix,part.classifier_ttl,part.classifier_max_entries)
        fixed=os.getenv("AEGIS_DEMO_AS_OF","").strip()
        current=date.fromisoformat(fixed) if fixed else None
        today=(lambda:current) if current else (lambda:datetime.now(ZoneInfo("Asia/Kolkata")).date())
        executor=ToolExecutor(FixtureOrders(part.fixture_path),authority,today)
        handlers={"product_question":AsyncProductQuestionAgent(retriever,llm,authority,pool,part.max_embedding_pending),
            "order_status":OrderStatusAgent(llm,executor,authority),
            "escalate_to_human":HumanEscalationAgent(authority)}
        service=PartASupportService(store,RegexGuard(),llm,
            Classifier(llm,cache,settings.provider_timeout),GuardedDispatcher(authority,handlers),
            ResponseService(llm,executor),authority,executor,part.turn_timeout,part.max_active)
        event("runtime_ready",model=settings.groq_model,demo_clock=fixed or "system_Asia_Kolkata",
            session_backend="redis",max_active_per_worker=part.max_active)
        return Runtime(settings,part,redis,llm,pool,service,store,cache)
    except BaseException:
        if llm: await llm.aclose()
        await redis.aclose()
        pool.shutdown(wait=False,cancel_futures=True)
        raise
