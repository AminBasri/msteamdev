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

*   **Confidence Score:** ≥ 70%
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
*   **Dynamic Cooldowns:** The "recent escalation" cooldown period is now dynamic, ranging from 2 hours for critical issues to 48 hours for low-impact ones. The suppression rule takes precedence over other rules.
*   **Boolean-Based Logic:** The Tier 3 framework directly uses the `True` or `False` output from the policy engine, making the logic robust and predictable.

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

## **6. Testing and Debugging**

A replay script is available to test the escalation pipeline without needing to trigger a live alert from PagerDuty.

*   **Script:** `tests/replay_escalation.py`
*   **Functionality:** The script automatically reads the `alert_log.json` file, selects the most recent alert, and runs the `run_escalation_pipeline` function for that alert.
*   **Usage:** `python3 tests/replay_escalation.py`
*   **Purpose:** This is extremely useful for debugging and for verifying changes to the `intelligent_policy.py` or `tiered_decision.py` logic.

---

## **7. AI Confidence Scoring & Tiered Framework Examples**

To understand the framework's logic, let's walk through an example for each tier.

### **How the KB Confidence Score is Calculated**

The KB Confidence Score is a crucial metric that determines whether the system can make a high-confidence decision in Tier 2. It is a weighted average of four key factors, each measuring a different aspect of the knowledge base's quality and relevance to the current alert.

The score is calculated as follows:

**`KB Confidence Score = (Data Reliability * 0.4) + (Data Volume * 0.2) + (Data Freshness * 0.2) + (Pattern Clarity * 0.2)`**

---

#### **1. Data Reliability (40% Weight)**

*   **What it measures:** The overall trustworthiness of the historical data for a given metric type (e.g., "cpu").
*   **How it's calculated:** This is a sub-score based on:
    *   **Data Age:** Newer data is considered more reliable.
    *   **Data Volume:** A higher number of past incidents provides a more reliable sample.
    *   **Pattern Clarity:** A clear pattern (e.g., a very high or very low false-positive rate) is more reliable than an ambiguous one.
*   **Source:** The underlying data comes from `incident_knowledge.json` and `alert_patterns.json`.

#### **2. Data Volume (20% Weight)**

*   **What it measures:** The number of similar incidents found in the knowledge base.
*   **How it's calculated:** The score is higher if more incidents are found (e.g., 10+ incidents = 1.0, 5-9 incidents = 0.8, 2-4 incidents = 0.6).
*   **Source:** `incident_knowledge.json`.

#### **3. Data Freshness (20% Weight)**

*   **What it measures:** How recently the knowledge base patterns for the alert's metric type were updated.
*   **How it's calculated:** The score is higher for more recently updated data (e.g., ≤ 30 days = 1.0, ≤ 90 days = 0.8, ≤ 180 days = 0.6).
*   **Source:** The `last_updated` timestamp in `alert_patterns.json`.

#### **4. Pattern Clarity (20% Weight)**

*   **What it measures:** How clear the historical pattern is for the alert.
*   **How it's calculated:** The score is higher if there is a very high (e.g., ≥ 70%) or very low false-positive rate, as this indicates a clear and predictable pattern.
*   **Source:** `alert_patterns.json` and `incident_knowledge.json`.

### **Example 1: Tier 2 (KB-Enhanced Suppression)**

This example shows the AI confidently suppressing a "noisy" alert based on rich historical data.

#### **The Input: A "Noisy" Alert Arrives**

At 3 AM, a new alert comes in from a non-production server.

*   **Incident:** #98765
*   **Title:** `ALARM: [WARNING] [STAGING] Synergi CORE - High CPU Utilization on web-s-04`
*   **Severity:** `warning`
*   **Timestamp:** `2025-10-03T03:00:00Z` (After-hours)

#### **Processing Step 1: Tier 1 (Safety Net)**

The alert is a `warning` and has no critical keywords, so it passes the safety checks. The framework proceeds to Tier 2.

#### **Processing Step 2: Tier 2 (KB-Enhanced Decision)**

The system queries the Knowledge Base and finds:
*   **Data Freshness:** Last updated **25 days ago**.
*   **Data Volume:** **15 similar incidents** found.
*   **Pattern Analysis:** **11 of the 15 (73%)** were false positives caused by a nightly backup job.

This data is used to calculate a **KB Confidence Score of 75%**. Because the score is high (≥70%) and the data shows a clear false positive pattern, the system decides to suppress.

#### **The Output: Confident Suppression**

The framework stops at Tier 2 and generates its final decision.

```json
{
  "escalate": false,
  "tier": "kb_enhanced",
  "confidence": "high",
  "reason": "KB SUPPRESSION: High confidence (0.75) suppression with 73.0% false positive rate"
}
```
**Conclusion:** The alert is autonomously suppressed, preventing unnecessary noise.

---

### **Example 2: Tier 1 (Safety Net Escalation)**

This example shows a critical, service-impacting alert that is immediately escalated without any AI analysis.

#### **The Input: A Critical Outage**

*   **Incident:** #11223
*   **Title:** `ALARM: [CRITICAL] Production Payment Gateway is DOWN`
*   **Severity:** `critical`
*   **Timestamp:** `2025-10-03T11:00:00Z` (Business hours)

#### **Processing Step 1: Tier 1 (Safety Net)**

The framework begins its checks:
1.  **Severity Check:** The alert's severity is `critical`. This is a non-negotiable trigger.

**The decision is made instantly.** The framework stops all further processing. Tiers 2 and 3 are never evaluated because safety comes first.

#### **The Output: Immediate Escalation**

```json
{
  "escalate": true,
  "tier": "safety_net",
  "confidence": "high",
  "reason": "SAFETY NET: CRITICAL severity requires immediate escalation",
  "safety_override": true
}
```
**Conclusion:** The alert is escalated immediately, ensuring the on-call team is notified within seconds of a critical issue.

---

### **Example 3: Tier 3 (Policy Fallback Escalation)**

This example shows a new, unknown alert that the AI cannot confidently assess, forcing a fallback to the intelligent policy rules.

#### **The Input: A New, Unknown Anomaly**

*   **Incident:** #44556
*   **Title:** `ALARM: [WARNING] [PROD] New User Signup Service - Latency Anomaly Detected`
*   **Severity:** `warning`
*   **Timestamp:** `2025-10-03T14:00:00Z` (Business hours)

#### **Processing Step 1: Tier 1 (Safety Net)**

The alert is a `warning` with no critical keywords, so it passes the safety checks.

#### **Processing Step 2: Tier 2 (KB-Enhanced Decision)**

The system queries the Knowledge Base for "Latency Anomaly" on the "New User Signup Service."
*   **Data Volume:** It finds **0 similar incidents**.

Because there is no historical data, the **KB Confidence Score is extremely low (e.g., 15%)**. This is far below the 70% threshold required to make an autonomous decision. The framework proceeds to Tier 3.

#### **Processing Step 3: Tier 3 (Intelligent Policy Engine)**

The decision now rests on the policy engine, which analyzes the alert's content:
*   **Business Impact:** "Latency" on a "User Signup Service" is assessed as **High**, as it could prevent new customers from joining.
*   **Service Tier:** The `[PROD]` tag indicates a **Production** environment.
*   **Time Context:** The alert occurred during **business hours**.

The engine's rules state that a **High** impact alert on a **Production** service during **business hours** must be investigated. It therefore returns `True` for escalation.

#### **The Output: Safe Escalation by Policy**

```json
{
  "escalate": true,
  "tier": "policy_fallback",
  "confidence": "medium",
  "reason": "POLICY ESCALATION: Policy criteria met for escalation"
}
```
**Conclusion:** Even though the AI was uncertain, the system remained safe by falling back to its intelligent rules, ensuring a potentially customer-affecting issue was not ignored.