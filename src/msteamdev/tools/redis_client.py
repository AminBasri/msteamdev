# src/msteamdev/tools/redis_client.py
import redis.asyncio as async_redis
import redis as sync_redis
import os
import json
import logging
import asyncio
from typing import Optional, Union

# Configure logger
logger = logging.getLogger('redis_client')
logger.setLevel(logging.INFO)
logger.propagate = False
logger.handlers.clear()

# Add FileHandler for redis_client.log - use relative path for cross-platform compatibility
log_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'log')
os.makedirs(log_dir, exist_ok=True)
file_handler = logging.FileHandler(os.path.join(log_dir, 'redis_client.log'))
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Add StreamHandler for console output
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(stream_handler)

# Global client instances
_async_redis_client: Optional[async_redis.Redis] = None
_sync_redis_client: Optional[sync_redis.Redis] = None

async def get_async_redis_client() -> Optional[async_redis.Redis]:
    """Initializes and returns an async Redis client."""
    global _async_redis_client
    
    if _async_redis_client is None:
        try:
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", 6379))
            _async_redis_client = async_redis.Redis(
                host=redis_host, 
                port=redis_port, 
                db=0, 
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            await _async_redis_client.ping()
            logger.info("Successfully connected to Redis (async).")
        except Exception as e:
            logger.error(f"Could not connect to Redis (async): {e}")
            _async_redis_client = None
            return None
    
    return _async_redis_client

def get_sync_redis_client() -> Optional[sync_redis.Redis]:
    """Initializes and returns a sync Redis client."""
    global _sync_redis_client
    
    if _sync_redis_client is None:
        try:
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", 6379))
            _sync_redis_client = sync_redis.Redis(
                host=redis_host, 
                port=redis_port, 
                db=0, 
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            _sync_redis_client.ping()
            logger.info("Successfully connected to Redis (sync).")
        except Exception as e:
            logger.error(f"Could not connect to Redis (sync): {e}")
            _sync_redis_client = None
            return None
    
    return _sync_redis_client

# For backwards compatibility
redis_client = None

async def init_redis():
    """Initialize Redis connections."""
    global redis_client
    redis_client = await get_async_redis_client()
    return redis_client

# Async versions
async def cache_set(key: str, value: Union[dict, str], ex: int = 300, ttl_seconds: int = None):
    """Saves a dictionary to the cache as JSON."""
    # Handle parameter variations
    if ttl_seconds is not None:
        ex = ttl_seconds
    
    client = await get_async_redis_client()
    if client:
        try:
            if isinstance(value, dict):
                value = json.dumps(value)
            await client.set(key, value, ex=ex)
            logger.debug(f"Cache SET: key='{key}', ttl={ex}s")
        except Exception as e:
            logger.error(f"Error setting cache key '{key}': {e}")

async def cache_get(key: str) -> Union[dict, str, None]:
    """Retrieves a value from the cache."""
    client = await get_async_redis_client()
    if client:
        try:
            cached_value = await client.get(key)
            if cached_value:
                logger.debug(f"Cache GET: key='{key}' (HIT)")
                try:
                    return json.loads(cached_value)
                except json.JSONDecodeError:
                    return cached_value
            else:
                logger.debug(f"Cache GET: key='{key}' (MISS)")
        except Exception as e:
            logger.error(f"Error getting cache key '{key}': {e}")
    return None

async def cache_delete(key: str):
    """Deletes a key from the cache."""
    client = await get_async_redis_client()
    if client:
        try:
            await client.delete(key)
            logger.debug(f"Cache DELETE: key='{key}'")
        except Exception as e:
            logger.error(f"Error deleting cache key '{key}': {e}")

async def cache_set_add(set_name: str, value: str):
    """Adds a member to a Redis set."""
    client = await get_async_redis_client()
    if client:
        try:
            await client.sadd(set_name, value)
            logger.debug(f"Redis SET ADD: set='{set_name}', member='{value}'")
        except Exception as e:
            logger.error(f"Error adding to Redis set '{set_name}': {e}")

async def cache_set_remove(set_name: str, value: str):
    """Removes a member from a Redis set."""
    client = await get_async_redis_client()
    if client:
        try:
            await client.srem(set_name, value)
            logger.debug(f"Redis SET REMOVE: set='{set_name}', member='{value}'")
        except Exception as e:
            logger.error(f"Error removing from Redis set '{set_name}': {e}")

async def cache_set_is_member(set_name: str, value: str) -> bool:
    """Checks if a member exists in a Redis set."""
    client = await get_async_redis_client()
    if client:
        try:
            is_member = await client.sismember(set_name, value)
            logger.debug(f"Redis SET IS_MEMBER: set='{set_name}', member='{value}', result={is_member}")
            return is_member
        except Exception as e:
            logger.error(f"Error checking Redis set membership for '{set_name}': {e}")
    return False

# Sync versions for use in sync contexts
def cache_set_sync(key: str, value: Union[dict, str], ex: int = 300, ttl_seconds: int = None):
    """Saves a value to the cache as JSON (sync version)."""
    # Handle parameter variations
    if ttl_seconds is not None:
        ex = ttl_seconds
    
    client = get_sync_redis_client()
    if client:
        try:
            if isinstance(value, dict):
                value = json.dumps(value)
            client.set(key, value, ex=ex)
            logger.debug(f"Cache SET (sync): key='{key}', ttl={ex}s")
        except Exception as e:
            logger.error(f"Error setting cache key '{key}' (sync): {e}")

def cache_get_sync(key: str) -> Union[dict, str, None]:
    """Retrieves a value from the cache (sync version)."""
    client = get_sync_redis_client()
    if client:
        try:
            cached_value = client.get(key)
            if cached_value:
                logger.debug(f"Cache GET (sync): key='{key}' (HIT)")
                try:
                    return json.loads(cached_value)
                except json.JSONDecodeError:
                    return cached_value
            else:
                logger.debug(f"Cache GET (sync): key='{key}' (MISS)")
        except Exception as e:
            logger.error(f"Error getting cache key '{key}' (sync): {e}")
    return None

def cache_delete_sync(key: str):
    """Deletes a key from the cache (sync version)."""
    client = get_sync_redis_client()
    if client:
        try:
            client.delete(key)
            logger.debug(f"Cache DELETE (sync): key='{key}'")
        except Exception as e:
            logger.error(f"Error deleting cache key '{key}' (sync): {e}")

# Smart wrapper functions that choose sync or async based on context
def cache_set_smart(key: str, value: Union[dict, str], ttl_seconds: int = 300):
    """Smart cache_set that works in both sync and async contexts."""
    try:
        # Try to get the current event loop
        loop = asyncio.get_running_loop()
        # If we're in an async context, create a task
        return asyncio.create_task(cache_set(key, value, ex=ttl_seconds))
    except RuntimeError:
        # No event loop running, use sync version
        return cache_set_sync(key, value, ex=ttl_seconds)

def cache_get_smart(key: str):
    """Smart cache_get that works in both sync and async contexts."""
    try:
        # Try to get the current event loop
        loop = asyncio.get_running_loop()
        # If we're in an async context, create a task
        return asyncio.create_task(cache_get(key))
    except RuntimeError:
        # No event loop running, use sync version
        return cache_get_sync(key)

def cache_delete_smart(key: str):
    """Smart cache_delete that works in both sync and async contexts."""
    try:
        # Try to get the current event loop
        loop = asyncio.get_running_loop()
        # If we're in an async context, create a task
        return asyncio.create_task(cache_delete(key))
    except RuntimeError:
        # No event loop running, use sync version
        return cache_delete_sync(key)
