# **CrewAI Pipeline Flow Analysis (Enhanced & Optimized)**

This document outlines the current, enhanced pipeline, which has been significantly refactored for performance, intelligence, and safety.

## **1. System Optimizations & Performance**

The new pipeline is built on several core optimizations that improve speed, reduce resource consumption, and provide better monitoring.

*   **Optimized Tooling:** The original ~20 separate tools have been consolidated into a few powerful, unified tools (`UnifiedAlertReader`, `KnowledgeQuery`). This reduces complexity and memory overhead.
*   **Dynamic Tool Loading:** Agents are no longer loaded with all tools. Instead, they receive a minimal, context-specific set of tools based on their role and the alert's severity.
*   **Asynchronous Pipeline:** The entire workflow now runs asynchronously using `asyncio`, allowing for non-blocking I/O and better scalability.
*   **Performance Monitoring:** A built-in `PerformanceMonitor` and `ToolUsageTracker` provide real-time insights into system health, task duration, error rates, and tool efficiency.
*   **Agent Caching:** Agents are cached to prevent unnecessary re-initialization, speeding up crew execution.

## **2. Alert Processing Pipeline**

The flow begins when an alert is received and is processed through a series of asynchronous, scheduled tasks.

### **Alert Reception (`webhook_receiver.py`)**

```
PagerDuty Webhook → FastAPI → Extract alert data → Save to alert_log.json
↓
start_alert_pipeline(alert) → Background thread (non-blocking)
```

### **Pipeline Orchestration (`crew.py`)**

The core pipeline schedules two main tasks asynchronously.

```
_run_alert_pipeline_async(alert):
  ├── Check for duplicate processing (Redis cache)
  ├── Schedule Acknowledgment Task (1-minute delay)
  └── Schedule Escalation Task (3-minute delay)
```

### **Parallel Processing**

```
┌─ Acknowledgment Path (Async Task) ───────────────┐
│ check_and_acknowledge_alert_task():              │
│   ├── Wait 1 minute                             │
│   ├── Load `pagerduty_manager` agent with minimal tools │
│   ├── Tools: GetIncidentStatus, AcknowledgeIncident │
│   ├── Auto-acknowledge if triggered             │
│   └── Fallback: Direct PagerDuty API call on failure │
└──────────────────────────────────────────────────┘

┌─ Escalation Path (Async Task) ───────────────────┐
│ run_escalation_pipeline():                       │
│   ├── Wait 3 minutes                            │
│   ├── Check if alert is already resolved        │
│   ├── Execute the Tiered Decision Framework     │
│   └── If approved → send_notification()         │
└──────────────────────────────────────────────────┘
```

## **3. The Tiered Decision Framework**

The heart of the new system is a three-tier, safety-first decision framework that replaces the old keyword-based logic. Decisions are made by evaluating the alert against each tier in order.

### **Tier 1: Safety Net (Non-Negotiable)**

This tier enforces absolute, non-negotiable rules to ensure critical alerts are *never* missed. If any of these conditions are met, the alert is **immediately escalated**, and the process stops.

*   **Critical/High Severity:** Any alert with a `critical` or `high` severity.
*   **Critical Keywords:** Presence of keywords like `outage`, `down`, `failure`, `unavailable`, `data loss`, `security`, etc.
*   **Security Alerts:** Any alert related to a potential security issue.
*   **After-Hours Priority:** A `warning` or `medium` severity alert with high-priority keywords (`degraded`, `slow`, `error`) that occurs outside of business hours.

### **Tier 2: Knowledge-Enhanced Decision**

If Tier 1 rules do not trigger, the framework consults the knowledge base (KB). A decision can be made here only if the KB data meets **high-confidence criteria**:

*   **Confidence Score:** ≥ 80%
*   **Data Freshness:** ≤ 90 days old
*   **Sufficient Volume:** Based on at least 2 historical incidents

If these criteria are met, the KB can:
*   **Suppress Escalation:** If historical data shows a high false-positive rate (e.g., >70%) or indicates planned maintenance. This is the only way a policy-approved escalation can be overridden.
*   **Force Escalation:** If historical data shows a low false-positive rate and a high resolution success rate, it can recommend escalation even if the policy check did not.

### **Tier 3: Intelligent Policy Fallback**

If Tier 1 is not triggered and the KB analysis is inconclusive or lacks confidence, the decision falls back to the **Intelligent Policy Engine**. This engine is a major upgrade from the old day-based rules.

*   **Context-Aware Rules:** It analyzes the alert title and content to assess:
    *   **Business Impact:** (Critical, High, Medium, Low)
    *   **Service Tier:** (Production, Staging, Dev)
    *   **Metric Type:** (CPU, Database, Payment, etc.)
    *   **Time Context:** (Business hours vs. after-hours)
*   **Dynamic Cooldowns:** The "recent escalation" cooldown period is now dynamic, ranging from 2 hours for critical issues to 48 hours for low-impact ones.
*   **Safety Default:** If the policy result is still unclear, the system defaults to **escalating the alert** to ensure safety.

## **4. AI Agent Roles in the New Framework**

The roles of the AI agents are now more specialized and integrated into the decision framework.

**Agent: `escalation_checker`**
*   **Role:** Provides the "AI Analysis" input for the Tiered Decision Framework.
*   **Context:** Receives the alert data and a rich summary from the **`KnowledgeQuery`** tool, which includes data freshness, reliability scores, and historical patterns.
*   **Task:** "Analyze the alert and provide an escalation recommendation based on the provided knowledge base context."
*   **Output:** A detailed analysis that is fed into the Tiered Decision Framework to be weighed alongside policy and safety rules.

**Agent: `communicator`**
*   **Role:** Crafts the final notification message *after* the Tiered Decision Framework has approved an escalation.
*   **Task:** "Craft a detailed and professional escalation notification..."
*   **Output:** A structured JSON object containing the email subject and body, ensuring reliable and well-formatted notifications.

## **5. Information Sources**

The system now relies on a more robust and intelligent set of information sources.

*   **Knowledge Base:** The primary source for historical context, including:
    *   `alert_patterns.json`: Tracks false-positive rates, resolution patterns, and business context. Includes `last_updated` timestamps for freshness scoring.
    *   `incident_knowledge.json`: A log of past incidents and their outcomes.
*   **Intelligent Policy Engine:** The new rule-based system that provides a dynamic, context-aware recommendation.
*   **AI Analysis:** The `escalation_checker` agent's analysis, which provides a qualitative assessment based on KB data.
*   **PagerDuty API:** Used to check the current incident status.
