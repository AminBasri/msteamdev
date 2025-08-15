# src/msteamuat/config.py

import os
import yaml
import logging

logger = logging.getLogger(__name__)


class Config:
    """Handles loading and access to configuration files."""

    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.agents_path = os.path.join(base_dir, "config", "agents.yaml")
        self.tasks_path = os.path.join(base_dir, "config", "tasks.yaml")
        self._load_configs()

    def _load_configs(self):
        """Load all YAML configuration files."""
        try:
            with open(self.agents_path, "r") as f:
                self.agents_def = yaml.safe_load(f)
            with open(self.tasks_path, "r") as f:
                self.tasks_def = yaml.safe_load(f)
            logger.info("Successfully loaded agent and task configurations.")
        except FileNotFoundError as e:
            logger.error(f"Configuration file not found: {e}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML configuration: {e}")
            raise

    def get_agents_def(self) -> dict:
        """Return the agents definition."""
        return self.agents_def

    def get_tasks_def(self) -> dict:
        """Return the tasks definition."""
        return self.tasks_def


# Create a single instance of the Config class to be used throughout the application
config = Config()