import json
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple, Optional

# Get the directory that contains the 'tools' subdirectory and the log files
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
LOG_FILE = os.path.join(BASE_DIR, "alert_log.json")

logger = logging.getLogger(__name__)

class AlertCache:
    """Manages caching of alerts with a Time-To-Live (TTL)."""

    def __init__(self, ttl_seconds: int = 60):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl = ttl_seconds
        self.last_update: Optional[datetime] = None
        self.cache_source: str = "empty"

    def _load_fresh_alerts(self) -> Dict[str, Dict[str, Any]]:
        """Loads alerts directly from the log file, deduplicating by incident_number."""
        logger.info("Loading fresh alerts from file: %s", LOG_FILE)
        if not os.path.exists(LOG_FILE):
            logger.warning(f"Alert log not found at {LOG_FILE}")
            self.cache_source = "file_not_found"
            return {}
        try:
            alert_dict = {}
            with open(LOG_FILE, "r") as f:
                for line in f:
                    alert = json.loads(line)
                    incident_number = alert.get("incident_number")
                    if incident_number:
                        alert_time = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
                        # Store the latest version of each alert
                        if incident_number not in alert_dict or \
                           alert_time > datetime.fromisoformat(alert_dict[incident_number]["timestamp"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc):
                            alert_dict[incident_number] = alert
            self.cache_source = "file_loaded"
            return alert_dict
        except Exception as e:
            logger.error(f"Failed to load fresh alerts from {LOG_FILE}: {e}")
            self.cache_source = "file_load_error"
            return {}

    def get_alerts(self, force_refresh: bool = False) -> Tuple[List[Dict[str, Any]], datetime, str]:
        """Retrieves alerts from cache or loads fresh data if cache is stale or refresh is forced.

        Returns:
            Tuple[List[Dict[str, Any]], datetime, str]: A tuple containing:
                - A list of alert dictionaries.
                - The timestamp of the last cache update (UTC).
                - The source of the data ('cached', 'fresh_load', 'file_not_found', 'file_load_error').
        """
        now = datetime.now(timezone.utc)
        if force_refresh or not self.last_update or \
           (now - self.last_update).total_seconds() > self.ttl:
            logger.info("Cache is stale or refresh forced. Loading fresh alerts.")
            self.cache = self._load_fresh_alerts()
            self.last_update = now
            return list(self.cache.values()), self.last_update, "fresh_load"
        
        logger.info("Returning alerts from cache.")
        return list(self.cache.values()), self.last_update, "cached"

# Global instance of the cache
ALERT_CACHE = AlertCache(ttl_seconds=int(os.getenv("ALERT_CACHE_TTL_SECONDS", "60")))