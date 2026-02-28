import redis.asyncio as redis
import asyncio
import os
import json

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
if REDIS_URL and not REDIS_URL.startswith(("redis://", "rediss://", "unix://")):
    REDIS_URL = f"rediss://{REDIS_URL}"

class RedisManager:
    def __init__(self):
        self.redis = None
        self.pubsub = None

    async def connect(self):
        try:
            # Log the connection attempt (safely masking password if present)
            safe_url = REDIS_URL.split("@")[-1] if "@" in REDIS_URL else REDIS_URL
            print(f"Connecting to Redis at: {safe_url}")
            
            self.redis = await redis.from_url(REDIS_URL, decode_responses=True)
            self.pubsub = self.redis.pubsub()
            print("Successfully connected to Redis")
        except Exception as e:
            print(f"Redis Connection Error: {e}")
            raise e

    async def publish(self, channel, message):
        await self.redis.publish(channel, json.dumps(message))

    async def subscribe(self, channel):
        await self.pubsub.subscribe(channel)
        async for message in self.pubsub.listen():
            if message["type"] == "message":
                yield json.loads(message["data"])

redis_manager = RedisManager()
