"""Real Redis/session test with explicitly scripted provider and no embedding inference."""
import argparse
import asyncio
from collections import Counter
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from redis.asyncio import Redis
from tests.fakes.part_a import make_service
from support_assistant.domain.conversation import Turn

ROOT=Path(__file__).resolve().parents[1]

async def run(args):
    redis=Redis.from_url(args.redis_url,decode_responses=True,max_connections=128)
    prefix='aegis-load-'+uuid.uuid4().hex
    info=await redis.info('server')
    persistence=await redis.info('persistence')
    runtime=make_service(redis,prefix,ROOT)
    runtime.llm.route='product_question'
    sem=asyncio.Semaphore(args.concurrency)
    sessions=[]
    started=time.monotonic()
    async def create():
        async with sem:return await runtime.store.create('customer-a')
    try:
        # Bounded task batches, not one unbounded task per session.
        for offset in range(0,args.sessions,500):
            sessions.extend(await asyncio.gather(*(create() for _ in range(min(500,args.sessions-offset)))))
        create_seconds=time.monotonic()-started
        turn_results=[];latencies=[]
        async def ask(index):
            async with sem:
                session=sessions[index%len(sessions)]
                start=time.monotonic()
                answer=await runtime.service.handle('customer-a',session.session_id,
                    Turn(turn_id=f'load-{index}',text='What filters are supported?'))
                latencies.append((time.monotonic()-start)*1000)
                return answer.status
        started=time.monotonic()
        for offset in range(0,args.turns,500):
            turn_results.extend(await asyncio.gather(*(ask(i) for i in range(offset,min(args.turns,offset+500)))))
        seconds=time.monotonic()-started
        read=await runtime.store.get(sessions[-1].session_id,'customer-a')
        result={'mode':'real_redis_scripted_llm_no_embeddings','redis_version':info.get('redis_version'),'aof_enabled':bool(persistence.get('aof_enabled')),
            'python':platform.python_version(),'session_records':len(sessions),'creation_seconds':create_seconds,
            'active_turns':args.turns,'client_concurrency':args.concurrency,'seconds':seconds,
            'turns_per_second':args.turns/seconds,'statuses':dict(Counter(turn_results)),
            'latency_ms':{'p50':statistics.median(latencies),'p95':sorted(latencies)[max(0,int(.95*len(latencies))-1)],'max':max(latencies)},
            'last_session_readable':read.session_id==sessions[-1].session_id,
            'classifier':await runtime.cache.metrics(),
            'limitations':'Single process. Session records are not 10k open network connections. Scripted provider and no embeddings: not Groq/RAG/voice throughput.'}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
    finally:
        keys=[k async for k in redis.scan_iter(match=prefix+':*')]
        for offset in range(0,len(keys),500):await redis.delete(*keys[offset:offset+500])
        await redis.aclose()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--redis-url',default=os.getenv('AEGIS_REDIS_URL','redis://127.0.0.1:6379/0'))
    p.add_argument('--sessions',type=int,default=10000)
    p.add_argument('--turns',type=int,default=200)
    p.add_argument('--concurrency',type=int,default=16)
    p.add_argument('--output',type=Path,default=Path('var/evaluation/part-a-capacity.json'))
    a=p.parse_args()
    if min(a.sessions,a.turns,a.concurrency)<=0:p.error('Counts must be positive')
    asyncio.run(run(a))

if __name__=='__main__':main()
