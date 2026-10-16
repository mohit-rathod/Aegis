import asyncio
import uuid
from support_assistant.domain.routing import Route
from support_assistant.observability.logging import event

class RedisClassifierCache:
    def __init__(self, redis, prefix="aegis", ttl=300, max_entries=1000):
        self.redis, self.prefix, self.ttl, self.max_entries = redis, prefix, ttl, max_entries

    def key(self, digest): return f"{self.prefix}:classifier:{digest}"

    async def get(self, digest):
        raw = await self.redis.get(self.key(digest))
        if raw is None: return None
        try:
            route = Route.model_validate_json(raw)
            import time
            await self.redis.zadd(f"{self.prefix}:classifier-keys", {self.key(digest): time.time()})
            return route
        except ValueError:
            await self.redis.delete(self.key(digest))
            return None

    async def put(self, digest, route):
        # Atomic capped insertion; the sorted set only tracks keys, not message text.
        script = """
        redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
        redis.call('ZADD', KEYS[2], ARGV[3], KEYS[1])
        local n = redis.call('ZCARD', KEYS[2]) - tonumber(ARGV[4])
        if n > 0 then
          local old = redis.call('ZRANGE', KEYS[2], 0, n-1)
          for _, k in ipairs(old) do redis.call('DEL', k); redis.call('ZREM', KEYS[2], k) end
        end
        return 1
        """
        import time
        await self.redis.eval(script,2,self.key(digest),f"{self.prefix}:classifier-keys",
            route.model_dump_json(),self.ttl,time.time(),self.max_entries)

    async def count(self, name):
        await self.redis.hincrby(f"{self.prefix}:classifier-metrics",name,1)

    async def metrics(self):
        values=await self.redis.hgetall(f"{self.prefix}:classifier-metrics")
        values={str(k):int(v) for k,v in values.items()}
        hits,misses=values.get("hits",0),values.get("misses",0)
        return {**values,"hit_rate":hits/(hits+misses) if hits+misses else 0.0}

    async def acquire_fill(self, digest, timeout):
        token=uuid.uuid4().hex
        ok=await self.redis.set(f"{self.key(digest)}:fill",token,nx=True,ex=timeout)
        return token if ok else None

    async def release_fill(self,digest,token):
        await self.redis.eval("if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('DEL',KEYS[1]) end return 0",
            1,f"{self.key(digest)}:fill",token)
