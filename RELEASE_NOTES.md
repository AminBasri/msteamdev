# Release Notes - msteamdev CrewAI Project

This document summarizes the key changes, features, and fixes that have been implemented in the `msteamdev` repository.

---

## Key Enhancements & Features

### 1. Advanced Agent Tooling (`enhanced_tools.py`)
- A new suite of "enhanced" tools has been introduced to provide advanced analytics, caching, and system monitoring capabilities.
- **Caching with Redis:** The enhanced tools use a Redis cache to store the results of expensive operations, dramatically improving performance for repeated queries.
- **In-depth Analysis:** Tools like `GetAlertTrends` and `GetMatchingAlertsEnhanced` now provide rich, pre-computed analysis, including trend data, pattern recognition, and time distribution, allowing the AI agents to make faster and more intelligent decisions.
- **Performance Metrics:** A `ToolMetrics` system has been integrated to track the usage, performance, and success rate of each tool, visible through the `GetSystemHealth` tool.

### 2. Centralized Logging and Health Checks
- **Unified Logging:** The logging configuration has been centralized in `src/msteamdev/logging_setup.py`, ensuring consistent and structured logging across the entire application.
- **Health Check Endpoint:** A new health check endpoint has been added to the webhook receiver, providing a simple way to monitor the status of the system.
- **Enhanced Telemetry:** More detailed logging has been added to the core `crew.py` logic, providing better visibility into agent and task execution, especially for PagerDuty interactions.

### 3. Improved Agent and Task Definitions
- The agent and task configurations (`agents_enhanced.yaml`, `tasks_enhanced.yaml`) have been updated to leverage the new enhanced tools.
- **Prompt Engineering:** The backstories and descriptions for agents have been refined to explicitly guide them to prioritize the use of the more powerful enhanced tools, while keeping the original tools as a reliable fallback.

### 4. Performance and Reliability Fixes
- **Asynchronous Operations:** Corrected several `TypeError` and event loop issues related to `async` and `sync` function calls, particularly with the Redis client and alert processing pipeline.
- **API Fallbacks:** The system now includes a fallback mechanism for PagerDuty API calls, improving the reliability of incident acknowledgments.
- **Dependency Updates:** Key dependencies such as `pdpyras`, `pydantic`, and `redis` have been updated to their latest versions.

---

## Detailed Changes by Component

- **`crew.py`**:
  - Integrated `LoggedAgent` and `LoggedTask` classes for enhanced telemetry.
  - Added more detailed logging for incident acknowledgment and escalation workflows.
- **`tools/alert_store.py`**:
  - Added synchronous versions of core functions (e.g., `load_log_sync`) for safer integration with CrewAI's synchronous tool model.
- **`tools/enhanced_tools.py`**:
  - Created as a new, advanced layer on top of `alert_store.py`.
  - Implemented Redis caching, performance metrics, and in-depth analytical helper functions.
- **`tools/mcp_stdio_server.py`**:
  - This module was removed in a refactor to simplify the architecture and rely on direct tool calls instead.
- **`config/*.yaml`**:
  - Updated agent and task definitions to include and prioritize the new enhanced tools.
- **`pyproject.toml`**:
  - Added new dependencies like `plotly` for future dashboarding capabilities.
  - Updated several existing packages to their latest versions.
