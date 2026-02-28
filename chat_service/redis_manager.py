import redis.asyncio as redis
import asyncio
import os
import json

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

class RedisManager:
    def __init__(self):
        self.redis = None
        self.pubsub = None

    async def connect(self):
        self.redis = await redis.from_url(REDIS_URL, decode_responses=True)
        self.pubsub = self.redis.pubsub()

    async def publish(self, channel, message):
        await self.redis.publish(channel, json.dumps(message))

    async def subscribe(self, channel):
        await self.pubsub.subscribe(channel)
        async for message in self.pubsub.listen():
            if message["type"] == "message":
                yield json.loads(message["data"])

redis_manager = RedisManager()
