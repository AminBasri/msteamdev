## Project Overview

This project is a multi-agent AI system built using the `crewAI` framework. Its primary purpose is to automate the processing and management of IT alerts. The system is designed to receive alerts, analyze them, decide whether to escalate them, and send notifications to the appropriate teams. It leverages a variety of tools and technologies, including:

*   **`crewAI`:** A framework for building multi-agent AI systems.
*   **Python:** The core programming language.
*   **YAML:** For configuring agents and tasks.
*   **PagerDuty:** For incident management.
*   **Redis:** For caching and tracking scheduled escalations.
*   **OpenLit:** For telemetry and performance monitoring.

The system is composed of several agents, each with a specific role:

*   **`action_recommender`:** Provides technical recommendations for resolving alerts.
*   **`escalation_checker`:** Decides whether an alert needs to be escalated.
*   **`communicator`:** Crafts and sends notifications.
*   **`reporter`:** Generates shift reports.
*   **`pagerduty_manager`:** Manages incidents in PagerDuty.

## Building and Running

### Installation

This project uses `uv` for dependency management. To install the necessary packages, run the following commands:

```bash
pip install uv
crewai install
```

### Running the Project

To run the project, use the following command:

```bash
crewai run
```

This will start a test pipeline that simulates an alert and processes it through the system.

### Running Tests

The project includes tests that can be run using `pytest`.

```bash
pytest
```

## Development Conventions

*   **Configuration:** Agents and tasks are defined in YAML files located in `src/msteamdev/config`.
*   **Core Logic:** The main application logic is in `src/msteamdev/crew.py`. This file defines the agents, tasks, and the main pipeline for processing alerts.
*   **Entry Point:** The entry point for the application is `src/msteamdev/main.py`, which handles command-line arguments and starts the alert processing pipeline.
*   **Tools:** Custom tools are located in the `src/msteamdev/tools` directory.
*   **Logging:** The system uses a custom logging setup that writes logs to `log/crew.log` and to the console.
*   **Performance Monitoring:** The project includes a `CrewPerformanceMonitor` class that tracks various metrics, such as the number of processed alerts, success rates, and processing times.
*   **Error Handling:** The system includes robust error handling, with retry logic for API calls and fallback mechanisms for critical operations.
*   **Environment Variables:** The project uses a `.env` file for managing environment variables, such as API keys.
