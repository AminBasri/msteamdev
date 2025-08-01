# src/msteamuat/llm.py

import os
import yaml
import logging
import threading
from openai import OpenAI
from crewai import LLM

# ------------------------------------------
# Logger Setup
# ------------------------------------------
logger = logging.getLogger('llm')
logger.setLevel(logging.INFO)
logger.propagate = False
logger.handlers.clear()

file_handler = logging.FileHandler('/home/crewai/msteamuat/log/llm.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(stream_handler)

# ------------------------------------------
# Optional: YAML config loader (not used now)
# ------------------------------------------
def load_yaml(path):
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning(f"LLM config file {path} not found, using defaults")
        return {}
    except Exception as e:
        logger.error(f"Failed to load LLM config {path}: {str(e)}")
        return {}

# ------------------------------------------
# Timeout-based LLM tester using OpenAI Client
# ------------------------------------------
class LLMWithTimeout:
    def __init__(self, base_url, api_key, model, timeout=5, test_message="Say hi!"):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.test_message = test_message

    def is_responsive(self):
        result = [None]

        def try_call():
            try:
                client = OpenAI(
                    base_url=self.base_url,
                    api_key=self.api_key
                )
                _ = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": self.test_message}]
                )
                result[0] = True
            except Exception as e:
                logger.warning(f"LLM API call failed: {str(e)}")
                result[0] = False

        thread = threading.Thread(target=try_call)
        thread.start()
        thread.join(timeout=self.timeout)

        return result[0] is True

# ------------------------------------------
# Main LLM loader with fallback logic
# ------------------------------------------
def get_llm():
    temperature = float(os.getenv("TEMPERATURE", 0.7))

    # === Try Ollama First ===
    try:
        ollama_model = os.getenv("MODEL", "ollama/mistral-small3.2:latest")
        ollama_base_url = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
        logger.info(f"Trying Ollama model: {ollama_model}")

        tester = LLMWithTimeout(
            base_url=ollama_base_url,
            api_key=os.getenv("OPENAI_API_KEY", "ollama"),  # dummy for local
            model=ollama_model,
            timeout=5
        )

        if tester.is_responsive():
            logger.info("Using Ollama LLM")
            return LLM(
                model=ollama_model,
                base_url=ollama_base_url,
                temperature=temperature
            )
        else:
            logger.warning("Ollama model is slow/unresponsive. Falling back.")
    except Exception as e:
        logger.warning(f"Ollama LLM check failed: {str(e)}")

    # === Fallback to OpenRouter ===
    try:
        openrouter_model = os.getenv("OPENROUTER_MODEL", "mistralai/mistral-small-3.2-24b-instruct")
        openrouter_base_url = os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
        openrouter_key = os.getenv("OPENROUTER_API_KEY")

        if openrouter_key:
            os.environ["OPENAI_API_KEY"] = openrouter_key  # Required by CrewAI

        logger.info(f"Falling back to OpenRouter model: {openrouter_model}")

        return LLM(
            model=openrouter_model,
            base_url=openrouter_base_url,
            temperature=temperature
        )
    except Exception as e:
        logger.error(f"Failed to initialize any LLM: {str(e)}")
        raise

# ------------------------------------------
# Test LLM response in __main__
# ------------------------------------------
if __name__ == "__main__":
    try:
        llm = get_llm()
        logger.info(f"LLM initialized successfully: {llm.model}")

        client = OpenAI(
            base_url=llm.base_url,
            api_key=os.getenv("OPENAI_API_KEY")
        )

        response = client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": "Say hi!"}]
        )

        logger.info("LLM response: %s", response.choices[0].message.content)
        print(f"\n🧠 LLM Provider: {llm.model}")
        print(f"💬 Response: {response.choices[0].message.content}\n")

    except Exception as e:
        logger.error(f"LLM test failed: {str(e)}")
        print(f"\n❌ LLM test failed: {str(e)}\n")