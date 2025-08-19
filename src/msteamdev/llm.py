# src/msteamdev/llm.py

import os
import yaml
import logging
from crewai import LLM

from msteamdev.logging_setup import get_module_logger

# Configure logger via centralized setup
logger = get_module_logger('llm', log_filename='llm.log', level=logging.INFO)

def load_yaml(path):
    """Load YAML configuration file."""
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning(f"LLM config file {path} not found, using defaults")
        return {}
    except Exception as e:
        logger.error(f"Failed to load LLM config {path}: {str(e)}")
        return {}

def get_llm():
    """Initialize and return an LLM instance with validated configuration."""
    # Default configuration
    default_config = {
        "model": "grok-3",
        "base_url": "https://api.x.ai/v1",
        "temperature": 0.7
    }

    # Load from environment variables
    env_config = {
        "model": os.getenv("MODEL", default_config["model"]),
        "base_url": os.getenv("OLLAMA_API_BASE", default_config["base_url"]),
        "temperature": float(os.getenv("TEMPERATURE", default_config["temperature"])),
        "timeout": 30,
        "max_retries": 3
    }
    '''
    # Load from config file (if exists)
    config_file = "src/msteamdev/config/llm.yaml"
    file_config = load_yaml(config_file)
    '''
    # Merge configurations: environment variables override file, file overrides defaults
    #config = {**default_config, **file_config, **env_config}
    config = {**env_config}

    # Validate configuration
    required_fields = ["model", "base_url", "temperature"]
    missing_fields = [field for field in required_fields if not config.get(field)]
    if missing_fields:
        logger.error(f"Missing required LLM configuration fields: {missing_fields}")
        raise ValueError(f"Missing required LLM configuration fields: {missing_fields}")

    logger.info(f"Initializing LLM with config: model={config['model']}, base_url={config['base_url']}, temperature={config['temperature']}")

    try:
        llm = LLM(
            model=config["model"],
            base_url=config["base_url"],
            temperature=config["temperature"],
        )
        return llm
    except Exception as e:
        logger.error(f"Failed to initialize LLM: {str(e)}")
        raise

if __name__ == "__main__":
    llm = get_llm()
    logger.info(f"LLM initialized: {llm}")