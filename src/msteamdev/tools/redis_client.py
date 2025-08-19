# src/msteamdev/tools/redis_client.py
import redis
import os
import json
import logging
from msteamdev.logging_setup import get_module_logger
from typing import Optional, Union

# Configure centralized logger
logger = get_module_logger('redis_client', log_filename='redis_client.log', level=logging.INFO)

# Global client instance - pure sync approach following CrewAI patterns
_redis_client: Optional[redis.Redis] = None

def get_redis_client() -> Optional[redis.Redis]:
    """Initializes and returns a Redis client (pure sync approach for CrewAI)."""
    global _redis_client
    
    if _redis_client is None:
        try:
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", 6379))
            _redis_client = redis.Redis(
                host=redis_host, 
                port=redis_port, 
                db=0, 
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            _redis_client.ping()
            logger.info("Successfully connected to Redis.")
        except Exception as e:
            logger.error(f"Could not connect to Redis: {e}")
            _redis_client = None
            return None
    
    return _redis_client

# For backwards compatibility
redis_client = None

def init_redis():
    """Initialize Redis connection (sync version for CrewAI)."""
    global redis_client
    redis_client = get_redis_client()
    return redis_client

# Pure sync cache functions following CrewAI patterns
def cache_set(key: str, value: Union[dict, str], ex: int = 300, ttl_seconds: int = None):
    """Saves a value to the cache as JSON."""
    # Handle parameter variations
    if ttl_seconds is not None:
        ex = ttl_seconds
    
    client = get_redis_client()
    if client:
        try:
            if isinstance(value, dict):
                value = json.dumps(value)
            client.set(key, value, ex=ex)
            logger.debug(f"Cache SET: key='{key}', ttl={ex}s")
        except Exception as e:
            logger.error(f"Error setting cache key '{key}': {e}")

def cache_get(key: str) -> Union[dict, str, None]:
    """Retrieves a value from the cache."""
    client = get_redis_client()
    if client:
        try:
            cached_value = client.get(key)
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

def cache_delete(key: str):
    """Deletes a key from the cache."""
    client = get_redis_client()
    if client:
        try:
            client.delete(key)
            logger.debug(f"Cache DELETE: key='{key}'")
        except Exception as e:
            logger.error(f"Error deleting cache key '{key}': {e}")

def cache_set_add(set_name: str, value: str):
    """Adds a member to a Redis set."""
    client = get_redis_client()
    if client:
        try:
            client.sadd(set_name, value)
            logger.debug(f"Redis SET ADD: set='{set_name}', member='{value}'")
        except Exception as e:
            logger.error(f"Error adding to Redis set '{set_name}': {e}")

def cache_set_remove(set_name: str, value: str):
    """Removes a member from a Redis set."""
    client = get_redis_client()
    if client:
        try:
            client.srem(set_name, value)
            logger.debug(f"Redis SET REMOVE: set='{set_name}', member='{value}'")
        except Exception as e:
            logger.error(f"Error removing from Redis set '{set_name}': {e}")

def cache_set_is_member(set_name: str, value: str) -> bool:
    """Checks if a member exists in a Redis set."""
    client = get_redis_client()
    if client:
        try:
            is_member = client.sismember(set_name, value)
            logger.debug(f"Redis SET IS_MEMBER: set='{set_name}', member='{value}', result={is_member}")
            return is_member
        except Exception as e:
            logger.error(f"Error checking Redis set membership for '{set_name}': {e}")
    return False

# Backwards compatibility aliases
cache_set_sync = cache_set
cache_get_sync = cache_get
cache_delete_sync = cache_delete
