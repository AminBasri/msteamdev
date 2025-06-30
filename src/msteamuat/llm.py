# llm.py
import os
from langchain_ollama import OllamaLLM

def get_llm():
    return Ollama(
        model=os.getenv("MODEL", "mistral:7b"),
        base_url=os.getenv("OLLAMA_API_BASE", "http://10.10.1.187:11434")
    )