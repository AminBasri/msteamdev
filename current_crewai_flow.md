# Current CrewAI Pipeline Flow Analysis

## **Actual System Flow** (No Customer Interaction)

### 1. **Alert Reception** (`webhook_receiver.py`)
```
PagerDuty Webhook → FastAPI → Extract alert data → Save to alert_log.json
↓
start_alert_pipeline(alert) → Background thread
```

### 2. **Pipeline Orchestration** (`crew.py`)
```
_run_alert_pipeline_async(alert):
  ├── Load MCP tools
  ├── Check if already scheduled (Redis cache)
  ├── Calculate escalation delay (3 minutes default)
  ├── Schedule acknowledgment task (1 minute delay)
  └── Schedule escalation pipeline (3 minutes delay)
```

### 3. **Parallel Processing** 
```
┌─ Acknowledgment Path ────────────────────────────┐
│ check_and_acknowledge_alert_task():              │
│   ├── Wait 1 minute                             │
│   ├── CrewAI Agent: pagerduty_manager           │
│   ├── Tools: GetIncidentStatus, AcknowledgeIncident │
│   └── Auto-acknowledge if triggered             │
└──────────────────────────────────────────────────┘

┌─ Escalation Path ────────────────────────────────┐
│ run_escalation_pipeline():                       │
│   ├── Wait 3 minutes                            │
│   ├── Check if resolved (skip escalation)       │
│   ├── Policy Check: check_escalation_eligibility │
│   ├── CrewAI Agents: escalation_checker + communicator │
│   ├── AI Decision: Should escalate?             │
│   └── If yes → send_notification()              │
└──────────────────────────────────────────────────┘
```

### 4. **AI Decision Making** (CrewAI Crew)
```
Agent: escalation_checker
├── Tools: ReadAlertLog, ReadEscalationLog, GetMatchingAlerts
├── Context: Alert history + Policy result + Raw logs
├── Task: "Verify policy output, override if incorrect"
└── Output: Escalation recommendation

Agent: communicator  
├── Context: escalation_checker output
├── Task: "Compose notification if escalation needed"
└── Output: Email content + decision
```

### 5. **Escalation Decision Logic**
```
AI Keyword Detection in communicator output:
Keywords: ["yes", "escalate", "send", "notify", "proceed", "approved", "urgent", "critical"]

If keywords found OR policy says escalate:
├── send_notification() → Email + Rocket.Chat
├── Log to escalation_log.json  
└── Mark as escalated

Else:
└── Suppress (no notification)
```

### 6. **Information Sources** (No Customer Input)
- **Alert History**: `alert_log.json` - all past alerts
- **Escalation History**: `escalation_log.json` - past escalation decisions  
- **Policy Logic**: `alert_store.py` - span-based rules
- **PagerDuty API**: Current incident status
- **AI Analysis**: Pattern recognition from CrewAI agents

## **Current Escalation Policy** (`alert_store.py`)

### The Actual Logic:
```python
def check_escalation_eligibility_sync(current_alert):
    # 1. Recent Escalation Check (Primary Block)
    if recent_escalations_within_threshold:
        return False, "Suppressed - recent escalation"
    
    # 2. Historical Span Analysis  
    matching_alerts = find_matching_triggered_alerts()
    if matching_alerts:
        span_days = count_weekdays(earliest, latest)
        if span_days > threshold:  # 5 days warning, 3 critical
            return True, "Escalate - span exceeds threshold"
        else:
            return False, "Suppress - within span threshold" 
    
    # 3. First Occurrence
    return True, "Escalate - first occurrence"
```

### The Problem with Current Logic:
```
Day 1: CPU Alert → No history → ESCALATE ✅
Day 2: CPU Alert → Recent escalation (1 day ago) → SUPPRESS ❌
Day 3: CPU Alert → Recent escalation (2 days ago) → SUPPRESS ❌  
Day 4: CPU Alert → Recent escalation (3 days ago) → SUPPRESS ❌
Day 5: CPU Alert → Recent escalation (4 days ago) → SUPPRESS ❌
Day 6: CPU Alert → Recent escalation (5 days ago) → SUPPRESS ❌
Day 7: CPU Alert → No recent escalation, check span...
        Span = Day1 to Day7 = X weekdays
        If X > 5 → Maybe escalate, If X ≤ 5 → Suppress
```

## **Your Desired vs Current Behavior**

### Your Desired Rule:
```
Day 1: ESCALATE → Days 2-5: SUPPRESS → Day 6: ESCALATE → Days 7-9: SUPPRESS → Day 10: ESCALATE
```

### Current System Behavior:
```  
Day 1: ESCALATE → Days 2-6+: SUPPRESS (recent escalation cooldown)
Day 7+: Depends on span calculation (unpredictable)
```

## **Information Flow Reality**

### What the AI Agents Actually See:
1. **Historical Context**: All past alerts and escalations
2. **Policy Recommendation**: Escalate/suppress with reasoning
3. **Raw Log Data**: Complete audit trail
4. **PagerDuty Status**: Current incident state

### What's Missing:
- ❌ Customer maintenance windows
- ❌ Business context about ongoing work
- ❌ Resolution status from customer
- ❌ Planned outages or batch jobs

### What CrewAI Does Well:
- ✅ Analyzes patterns in alert history
- ✅ Can override policy decisions based on context
- ✅ Provides detailed reasoning for decisions
- ✅ Learns from historical escalation patterns

## **The Core Issue**

Your CrewAI agents are **intelligent but blind to business context**. They can analyze technical patterns but don't know:
- "Customer is running batch job until month-end" 
- "Issue was resolved 2 hours ago"
- "This is planned maintenance"
- "Customer is actively working on this"

## **Recommended Fix** (Minimal Changes)

### Option A: Fix Escalation Policy Only
```python
# Replace span-based logic with simple periodic logic
def check_periodic_escalation(alert):
    last_escalation = get_last_escalation_same_type(alert)
    if not last_escalation:
        return True, "First occurrence"
    
    days_since = get_days_between(last_escalation.timestamp, alert.timestamp)
    threshold = 5 if alert.severity == "warning" else 3
    
    if days_since >= threshold:
        return True, f"Periodic escalation due ({days_since} days since last)"
    else:
        return False, f"Within {threshold}-day cycle ({days_since} days elapsed)"
```

### Option B: Enhance AI Context (Recommended)
Keep current CrewAI intelligence but improve the context:

```python
# Enhance escalation_checker agent prompt with better instructions
context = f"""
Alert Analysis Context:
- Alert: {alert}  
- Policy Result: {policy_result}
- Recent History: {recent_similar_alerts}
- Business Hours: {is_business_hours}
- Pattern Analysis: {detect_patterns}

ESCALATION RULES:
1. First occurrence → Always escalate
2. Severity increase → Always escalate immediately  
3. Periodic timing → Every {threshold} days
4. Recent escalation within {threshold} days → Generally suppress
5. Consider: Is this likely planned maintenance? Batch job? Weekend work?

Override policy if you detect patterns suggesting this is business-as-usual.
"""
```

## **Recommendation**

**Keep your excellent CrewAI pipeline** - it's sophisticated and works well.

**Fix the escalation policy** to implement your desired periodic timing instead of the current span-based approach.

**Enhance agent context** with better business logic awareness, even without direct customer input.

The system can be much more effective by fixing the core timing logic while preserving the AI intelligence you've built.