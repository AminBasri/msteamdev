# src/msteamdev/tools/redis_client.py
import redis.asyncio as redis
import os
import json
import logging
import asyncio

# Configure logger
logger = logging.getLogger('redis_client')
logger.setLevel(logging.INFO)
logger.propagate = False
logger.handlers.clear()

# Add FileHandler for redis_client.log
log_dir = '/home/crewai/msteamdev/log/'
os.makedirs(log_dir, exist_ok=True)
file_handler = logging.FileHandler(os.path.join(log_dir, 'redis_client.log'))
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Add StreamHandler for console output
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(stream_handler)

async def get_redis_client():
    """Initializes and returns a Redis client."""
    try:
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", 6379))
        client = redis.Redis(host=redis_host, port=redis_port, db=0, decode_responses=True)
        await client.ping()
        logger.info("Successfully connected to Redis.")
        return client
    except redis.exceptions.ConnectionError as e:
        logger.error(f"Could not connect to Redis: {e}")
        return None

redis_client = asyncio.run(get_redis_client())

async def cache_set(key: str, value: dict, ex: int = 300):
    """Saves a dictionary to the cache as JSON."""
    if redis_client:
        try:
            await redis_client.set(key, json.dumps(value), ex=ex)
            logger.debug(f"Cache SET: key='{key}', ttl={ex}s")
        except Exception as e:
            logger.error(f"Error setting cache key '{key}': {e}")

async def cache_get(key: str) -> dict | None:
    """Retrieves a dictionary from the cache."""
    if redis_client:
        try:
            cached_value = await redis_client.get(key)
            if cached_value:
                logger.debug(f"Cache GET: key='{key}' (HIT)")
                return json.loads(cached_value)
            else:
                logger.debug(f"Cache GET: key='{key}' (MISS)")
        except Exception as e:
            logger.error(f"Error getting cache key '{key}': {e}")
    return None

async def cache_delete(key: str):
    """Deletes a key from the cache."""
    if redis_client:
        try:
            await redis_client.delete(key)
            logger.debug(f"Cache DELETE: key='{key}'")
        except Exception as e:
            logger.error(f"Error deleting cache key '{key}': {e}")

async def cache_set_add(set_name: str, value: str):
    """Adds a member to a Redis set."""
    if redis_client:
        try:
            await redis_client.sadd(set_name, value)
            logger.debug(f"Redis SET ADD: set='{set_name}', member='{value}'")
        except Exception as e:
            logger.error(f"Error adding to Redis set '{set_name}': {e}")

async def cache_set_remove(set_name: str, value: str):
    """Removes a member from a Redis set."""
    if redis_client:
        try:
            await redis_client.srem(set_name, value)
            logger.debug(f"Redis SET REMOVE: set='{set_name}', member='{value}'")
        except Exception as e:
            logger.error(f"Error removing from Redis set '{set_name}': {e}")

async def cache_set_is_member(set_name: str, value: str) -> bool:
    """Checks if a member exists in a Redis set."""
    if redis_client:
        try:
            is_member = await redis_client.sismember(set_name, value)
            logger.debug(f"Redis SET IS_MEMBER: set='{set_name}', member='{value}', result={is_member}")
            return is_member
        except Exception as e:
            logger.error(f"Error checking Redis set membership for '{set_name}': {e}")
    return False