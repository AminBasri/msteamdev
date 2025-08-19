import logging
import os
import sys
from typing import Optional


def get_log_dir() -> str:
    """Return absolute directory path for logs under the repo's log directory."""
    # Use the main log directory at /home/crewai/msteamdev/log
    log_dir = '/home/crewai/msteamdev/log'
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def setup_root_logger(log_filename: str = 'crew.log', level: int = logging.INFO) -> logging.Logger:
    """Configure the root logger to write to the central log directory and stdout.

    This uses force=True to override any prior basicConfig so all modules route
    to the same place consistently.
    """
    log_dir = get_log_dir()
    log_file_path = os.path.join(log_dir, log_filename)

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file_path),
            logging.StreamHandler(sys.stdout)
        ],
        force=True,
    )
    return logging.getLogger()


def get_module_logger(name: str, log_filename: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    """Return a named logger configured to write to the central log directory.

    - When log_filename is provided, a FileHandler is attached for that file.
    - Console output is always attached.
    - Propagation is disabled to avoid duplicate logs when root is also configured.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    logger.handlers.clear()

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    if log_filename:
        log_dir = get_log_dir()
        file_handler = logging.FileHandler(os.path.join(log_dir, log_filename))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def configure_llm_library_loggers(logger_names: Optional[list] = None) -> None:
    """Route LLM-related libraries' logs to llm.log and stop propagation to root.

    Targets: httpx, httpcore, litellm, openlit
    """
    if logger_names is None:
        # Include both lowercase and CamelCase variants used by libraries
        logger_names = ["httpx", "httpcore", "opentelemetry.instrumentation.instrumentor", "LiteLLM", "openlit", "opentelemetry.trace"]

    log_dir = get_log_dir()
    llm_log_path = os.path.join(log_dir, "llm.log")

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler = logging.FileHandler(llm_log_path)
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    for logger_name in logger_names:
        lib_logger = logging.getLogger(logger_name)
        # Prevent forwarding to root (which writes to crew.log)
        lib_logger.propagate = False

        # Avoid duplicating handlers if already configured for llm.log
        has_llm_file = False
        for h in lib_logger.handlers:
            try:
                if isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', '') == llm_log_path:
                    has_llm_file = True
                    break
            except Exception:
                pass
        if not has_llm_file:
            lib_logger.addHandler(file_handler)

        # Ensure console visibility for these libraries
        has_stream = any(isinstance(h, logging.StreamHandler) for h in lib_logger.handlers)
        if not has_stream:
            lib_logger.addHandler(stream_handler)


