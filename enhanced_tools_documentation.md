# Documentation for enhanced_tools.py

This document provides an explanation of the `enhanced_tools.py` script, which defines a suite of advanced tools for a CrewAI agent designed to manage and analyze IT alerts.

## Key Features

The "enhanced" nature of these tools comes from several key features that make them powerful and reliable for an automated alert management system:

### 1. Metrics and Performance Tracking

-   **`ToolMetrics` Class**: A dedicated class to track important performance indicators for each tool.
-   **`@with_tool_metrics` Decorator**: This decorator is applied to each tool to automatically record:
    -   **Call Counts**: How many times each tool is used.
    -   **Error Counts**: How many times a tool fails.
    -   **Execution Times**: The average time it takes for a tool to run.
    -   **Success Rate**: The percentage of successful tool executions.
-   This metrics system is crucial for monitoring the agent's performance and identifying potential bottlenecks or issues.

### 2. Caching with Redis

-   The tools leverage a **Redis cache** (via `redis_client.py`) to store the results of computationally expensive operations, such as reading and filtering the alert log.
-   When a tool is called with the same parameters as a previous call, it can instantly retrieve the result from the cache instead of re-running the entire operation. This dramatically improves the speed and efficiency of the system.

### 3. In-depth Analysis

The tools are designed to provide more than just raw data; they perform on-the-fly analysis to deliver actionable insights:

-   `get_matching_alerts_enhanced`: Not only finds alerts but also analyzes their patterns, time distribution, and the criteria used for the search.
-   `check_escalation_eligibility_enhanced`: Provides detailed, context-aware reasoning for its decisions, considering factors like business hours, historical data, and alert severity.
-   `get_alert_trends`: Calculates distributions, rates, and alert velocity to offer a high-level, strategic overview of the alert landscape.

### 4. System Health Monitoring

-   The `get_system_health` tool acts as a real-time dashboard for the system's operational status.
-   It provides a snapshot of critical components, including the health of the Redis cache and the performance metrics of all other tools, allowing for quick diagnostics.

## Core Functions

-   **`read_alert_log_enhanced`**: Reads the alert log with powerful filtering capabilities for severity and time windows.
-   **`get_matching_alerts_enhanced`**: Finds specific alerts based on a set of criteria and provides a detailed analysis of the matching results.
-   **`check_escalation_eligibility_enhanced`**: Determines whether an alert requires human intervention and provides a comprehensive justification for its recommendation.
-   **`get_alert_trends`**: Analyzes alert patterns over a specified time period to identify emerging trends and systemic issues.
-   **`get_system_health`**: Delivers a health check of the entire monitoring system, including its dependencies and internal performance metrics.

---

## How to See the Tools in Action

These tools are intended to be used by an AI agent within the CrewAI framework, so the `enhanced_tools.py` script is not meant to be run directly. The primary way to observe their functionality is by running the main application and monitoring the logs.

However, to provide a direct demonstration, the `test_tools_output.py` script was created. This script imports and runs the `get_system_health` function to showcase the metrics system.

To run the test script, execute the following command in your terminal:

```bash
python test_tools_output.py
```

When you run this script, you will see:
1.  The initial output of the `get_system_health` tool, with no metrics recorded yet.
2.  A call to another tool (`read_alert_log_enhanced`) to generate some metrics.
3.  The updated output of `get_system_health`, which will now include the performance data for the `read_alert_log_enhanced` tool, demonstrating the live metrics tracking.
