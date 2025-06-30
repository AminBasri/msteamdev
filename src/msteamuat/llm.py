# llm.py
import os
from langchain_ollama import OllamaLLM

def get_alert_llm():
    """Return LLM for alert management (Magistral)."""
    return OllamaLLM(
        model=os.getenv("ALERT_MODEL", "magistral:latest"),  # Updated to remove 'ollama/' prefix
        base_url=os.getenv("OLLAMA_API_BASE", "http://10.10.6.8:11434"),
        temperature=0.3,  # Precise reasoning for alerts
    )

def get_report_llm():
    """Return LLM for daily report generation (Mixtral)."""
    return OllamaLLM(
        model=os.getenv("REPORT_MODEL", "mixtral:latest"),  # Updated to remove 'ollama/' prefix
        base_url=os.getenv("OLLAMA_API_BASE", "http://10.10.6.8:11434"),
        temperature=0.7,  # Creative text for reports
    )

# Optional: Dictionary for accessing LLMs by role
llm_configs = {
    "alert_management": get_alert_llm(),
    "daily_report": get_report_llm()
}