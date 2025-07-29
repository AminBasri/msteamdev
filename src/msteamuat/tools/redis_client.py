# src/msteamuat/tools/redis_client.py
import redis
import os
import json
import logging

# Configure logger
logger = logging.getLogger('redis_client')
logger.setLevel(logging.INFO)
logger.propagate = False
logger.handlers.clear()

# Add FileHandler for redis_client.log
log_dir = '/home/crewai/msteamuat/log/'
os.makedirs(log_dir, exist_ok=True)
file_handler = logging.FileHandler(os.path.join(log_dir, 'redis_client.log'))
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Add StreamHandler for console output
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(stream_handler)

def get_redis_client():
    """Initializes and returns a Redis client."""
    try:
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", 6379))
        client = redis.Redis(host=redis_host, port=redis_port, db=0, decode_responses=True)
        client.ping()
        logger.info("Successfully connected to Redis.")
        return client
    except redis.exceptions.ConnectionError as e:
        logger.error(f"Could not connect to Redis: {e}")
        return None

redis_client = get_redis_client()

# Cache utility functions for storing and retrieving data in Redis. 15 minutes TTL by default.
def cache_set(key: str, value: dict, ttl_seconds: int = 900):
    """Saves a dictionary to the cache as JSON."""
    if redis_client:
        redis_client.set(key, json.dumps(value), ex=ttl_seconds)

def cache_get(key: str) -> dict | None:
    """Retrieves a dictionary from the cache."""
    if redis_client:
        cached_value = redis_client.get(key)
        if cached_value:
            return json.loads(cached_value)
    return None

def cache_delete(key: str):
    """Deletes a key from the cache."""
    if redis_client:
        redis_client.delete(key)
