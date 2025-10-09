# src/msteamdev/llm.py

import os
import yaml
import logging
from crewai.llm import LLM

# Optional LangChain imports for fallback
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_openai import ChatOpenAI
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

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
    # print(f"DEBUG: OLLAMA_API_BASE = {os.getenv('OLLAMA_API_BASE')}")
    # print(f"DEBUG: MODEL = {os.getenv('MODEL')}")
    # print(f"DEBUG: GEMINI_API_KEY = {os.getenv('GEMINI_API_KEY')}")
    # print(f"DEBUG: GEMINI_MODEL = {os.getenv('GEMINI_MODEL')}")
    # print(f"DEBUG: OPENAI_API_BASE_URL = {os.getenv('OPENAI_API_BASE_URL')}")
    
    ollama_base_url = os.getenv("OLLAMA_API_BASE")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    openai_base_url = os.getenv("OPENAI_API_BASE_URL")
    model = os.getenv("MODEL")
    temperature = float(os.getenv("TEMPERATURE", 0.7))

    # 1. Primary: Ollama
    if ollama_base_url and model:
        logger.info(f"Found OLLAMA_API_BASE and MODEL. Initializing CrewAI LLM for Ollama.")
        try:
            # Use CrewAI LLM wrapper for Ollama
            llm = LLM(
                model=f"ollama/{model}",
                base_url=ollama_base_url,
                temperature=temperature,
                api_key="dummy"  # Add dummy API key for Ollama
            )
            logger.info(f"Successfully initialized Ollama LLM: model=ollama/{model}, base_url={ollama_base_url}")
            return llm
        except Exception as e:
            logger.error(f"Failed to initialize Ollama LLM: {str(e)}")
            raise

    # 2. Secondary: Gemini
    elif gemini_api_key:
        logger.info("Found GEMINI_API_KEY. Initializing CrewAI LLM for Gemini.")
        try:
            # Use CrewAI LLM wrapper with correct model format for LiteLLM
            llm = LLM(
                model=f"gemini/{gemini_model}",
                api_key=gemini_api_key,
                temperature=0.3
            )
            logger.info(f"Successfully initialized Gemini LLM: model=gemini/{gemini_model}")
            return llm
        except Exception as e:
            logger.error(f"Failed to initialize Gemini LLM: {str(e)}")
            raise

    # 3. Tertiary: OpenAI
    elif openai_base_url and model:
        logger.info(f"Found OPENAI_API_BASE_URL and MODEL. Initializing CrewAI LLM for OpenAI.")
        try:
            # Use CrewAI LLM wrapper for OpenAI
            llm = LLM(
                model=f"openai/{model}",
                base_url=openai_base_url,
                temperature=temperature,
                api_key="dummy"  # Add dummy API key for OpenAI fallback
            )
            logger.info(f"Successfully initialized OpenAI LLM: model=openai/{model}, base_url={openai_base_url}")
            return llm
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI LLM: {str(e)}")
            raise
            
    # If no configuration is found
    else:
        error_msg = (
            "No LLM configuration found. Please set the environment variables for "
            "either Ollama (OLLAMA_API_BASE, MODEL), "
            "Gemini (GEMINI_API_KEY), or "
            "OpenAI (OPENAI_API_BASE_URL, MODEL)."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

if __name__ == "__main__":
    from dotenv import load_dotenv
    # To test, you would need to set GEMINI_API_KEY or other model env vars
    # For example: export GEMINI_API_KEY='your_key_here'
    load_dotenv()
    llm = get_llm()
    logger.info(f"LLM initialized: {llm}")
