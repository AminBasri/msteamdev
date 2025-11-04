# NOC Shift Report KPI Documentation

## Overview

This document describes the Key Performance Indicators (KPIs) tracked in the NOC Shift Report system, including their calculation methods, data sources, and interpretation guidelines.

## Alert Timing Metrics

### Time to Acknowledge (MTTA)

**Definition**: Time between alert creation and first acknowledgment by NOC staff.

**Calculation**:
```python
tta = (acknowledged_at - created_at).total_seconds() / 60  # in minutes
```

**Fields Used**:
- `timestamp`: Alert creation time (UTC)
- `acknowledged_at`: Time of first acknowledgment (UTC)

**Interpretation**:
- < 5 minutes: Excellent response
- 5-15 minutes: Within target
- > 15 minutes: Requires attention

### Time to Resolve (MTTR)

**Definition**: Time between alert creation and final resolution.

**Calculation**:
```python
ttr = (resolved_at - created_at).total_seconds() / 60  # in minutes
```

**Fields Used**:
- `timestamp`: Alert creation time
- `resolved_at`: Resolution time

### Time to First Response (TTFR)

**Definition**: Time until first action taken (acknowledgment or response).

**Fields Used**:
- `timestamp`: Alert creation time
- `first_response_at`: Time of first action

## Alert Status Metrics

### Resolution Rate

**Definition**: Percentage of alerts resolved during the shift.

**Calculation**:
```python
resolution_rate = (resolved_alerts / total_alerts) * 100
```

### Escalation Rate

**Definition**: Percentage of alerts that required escalation.

**Calculation**:
```python
escalation_rate = (escalated_alerts / total_alerts) * 100
```

### Acknowledgment Rate

**Definition**: Percentage of alerts acknowledged during the shift.

**Calculation**:
```python
acknowledgment_rate = (acknowledged_alerts / total_alerts) * 100
```

## KPI Compliance

### KPI Breach Rate

**Definition**: Percentage of alerts that breached their KPI targets.

**Fields Used**:
- `kpi_breach_at`: Timestamp when KPI was breached
- Total alerts with defined KPIs

**Calculation**:
```python
kpi_compliance = ((total_with_kpi - breached) / total_with_kpi) * 100
```

## Data Quality Metrics

### Report Completeness Score

**Definition**: Measure of report content completeness against required sections.

**Components**:
1. Required sections present
2. KPI data availability
3. Alert detail completeness

**Scoring**:
- 1.0: All sections and data present
- 0.7: Using fallback data sources
- 0.5: Missing required sections
- < 0.5: Significant data gaps

### Data Freshness

**Levels**:
- "real-time": Direct from alert source
- "cached": From cache within TTL
- "fallback": Using backup data source
- "stale": Cache expired

## Report Generation Health

### Metrics Implementation

```python
class ReportMetrics:
    """Track report generation health."""
    
    def __init__(self):
        self.metrics = {
            "reports_generated": 0,
            "fallback_used_count": 0,
            "average_generation_time_ms": 0,
            "failed_deliveries": 0,
            "structured_output_success_rate": 0.0,
            "kb_analysis_used": 0,
            "ai_analysis_used": 0
        }
    
    def record_metric(self, metric: ReportGenerationMetric):
        """Record a new report generation metric"""
        self.metrics["reports_generated"] += 1
        self.metrics["generation_time_ms"] = metric.generation_time_ms
        
        if metric.fallback_used:
            self.metrics["fallback_used_count"] += 1
            
        if metric.extraction_method == "pydantic_structured":
            self.metrics["structured_output_success_rate"] = (
                self.metrics["structured_output_successes"] / 
                self.metrics["reports_generated"]
            )
    
    def should_alert_on_quality_degradation(self) -> bool:
        """Alert if fallback usage exceeds threshold."""
        fallback_rate = (self.metrics["fallback_used_count"] / 
                        self.metrics["reports_generated"])
        return fallback_rate > 0.3  # 30% threshold
```

### Key Metrics Tracked

1. **Generation Success Rate**
   - Successful vs failed generations
   - Structured output vs fallback usage
   - KB analysis utilization rate
   - AI analysis utilization rate

2. **Performance Metrics**
   - Generation time (milliseconds)
   - Cache hit/miss ratio
   - Error counts by type
   - Delivery success rate

3. **Quality Indicators**
   - Data completeness (via Pydantic validation)
   - Source reliability tracking
   - Known gaps with timestamps

### Health Monitoring

The system uses comprehensive monitoring with built-in alerts:

```python
class ReportHealthMonitor:
    """Monitor report generation health with alerts."""
    
    HEALTH_THRESHOLDS = {
        "fallback_rate_max": 0.3,      # Max 30% fallback usage
        "success_rate_min": 0.7,       # Min 70% structured output
        "completeness_min": 0.8,       # Min 80% completeness
        "error_rate_max": 0.2,         # Max 20% error rate
        "kb_freshness_days": 90,       # Max KB age in days
        "ai_analysis_rate_min": 0.5    # Min 50% AI analysis usage
    }
    
    def check_health(self, metrics: ReportMetrics) -> Dict[str, Any]:
        """Check all health indicators."""
        return {
            "healthy": self._is_healthy(metrics),
            "warnings": self._get_warnings(metrics),
            "stats": {
                "fallback_rate": metrics.get_fallback_rate(),
                "success_rate": metrics.get_success_rate(),
                "error_rate": metrics.get_error_rate(),
                "kb_freshness": metrics.get_kb_age_days()
            }
        }
    
    def should_alert(self, metrics: ReportMetrics) -> bool:
        """Determine if health status requires alert."""
        return (
            metrics.get_fallback_rate() > self.HEALTH_THRESHOLDS["fallback_rate_max"] or
            metrics.get_success_rate() < self.HEALTH_THRESHOLDS["success_rate_min"] or
            metrics.get_error_rate() > self.HEALTH_THRESHOLDS["error_rate_max"]
        )
```

## Alert Processing Rules

### Tiered Decision Framework

The system uses a 3-tier decision framework:

1. **Tier 1: Safety Net**
   ```python
   CRITICAL_KEYWORDS = [
       'outage', 'down', 'failed', 'failure', 'unavailable', 'offline',
       'crashed', 'panic', 'emergency', 'disaster', 'breach', 'security',
       'data loss', 'corruption', 'timeout', 'unreachable', 'dead'
   ]
   
   HIGH_PRIORITY_KEYWORDS = [
       'degraded', 'slow', 'error', 'warning', 'threshold', 'limit',
       'capacity', 'overload', 'congestion', 'bottleneck'
   ]
   ```

2. **Tier 2: Knowledge-Based**
   - Uses weighted confidence calculation
   - Minimum 70% confidence required
   - Data must be ≤90 days old
   - Requires ≥2 historical incidents

3. **Tier 3: Policy Fallback**
   - Traditional time-based rules
   - Enhanced with KB context
   - Defaults to escalation when uncertain

### Deduplication

Alerts are deduplicated based on:
1. Incident number (primary key)
2. Latest timestamp for updates
3. State transition rules
4. Redis-based locking for atomic operations

### Timezone Handling

All timestamps are:
1. Stored in UTC for calculations
2. Displayed in Asia/Singapore time (UTC+8) in reports
3. Include timezone offset in serialization
4. Handle DST transitions properly

### State Transitions

Valid alert states with validation:
```python
VALID_TRANSITIONS = {
    'open': ['acknowledged'],
    'acknowledged': ['resolved'],
    'resolved': ['closed', 'reopened'],
    'reopened': ['acknowledged']
}

def validate_transition(current_state: str, new_state: str) -> bool:
    """Validate alert state transition."""
    return new_state in VALID_TRANSITIONS.get(current_state, [])

## Implementation Notes

### Cache Usage

The AlertCache provides:
1. Configurable TTL
2. Forced refresh option
3. Source tracking
4. Deduplication

### Error Handling

1. Invalid timestamps → excluded from averages
2. Missing data → marked as "N/A"
3. Cache misses → fallback to file
4. Failed calculations → logged and skipped

## Report Sections

Required sections checked by ShiftHandoverProtocol:
1. EXECUTIVE SUMMARY
2. KEY PERFORMANCE INDICATORS
3. ACTIVE INCIDENTS (HANDOVER)
4. RESOLVED INCIDENTS (DURING SHIFT)
5. RISK ASSESSMENT
6. HANDOVER INFORMATION
7. DATA QUALITY INDICATORS

## Example Usage

### Alert Processing Pipeline
```python
@retry()
async def run_escalation_pipeline(alert: dict):
    """Run the optimized escalation pipeline with the Tiered Decision Framework."""
    start_time = time.time()
    incident_number = alert.get("incident_number")
    
    try:
        # Get AI analysis from escalation_checker agent
        ai_analysis = str(ai_analysis_result.raw or "")
        
        # Get policy recommendation
        policy_result_dict = check_policy(alert)
        policy_result_tuple = (
            policy_result_dict.get("eligible", False), 
            policy_result_dict.get("reason", "")
        )

        # Make decision using the Tiered Framework
        decision_result = tiered_framework.make_decision(
            alert, 
            policy_result_tuple,
            None,  # KB analysis done inside framework
            ai_analysis
        )

        # Log decision for auditing
        log_decision_audit.run(
            incident_number=incident_number,
            decision_result=json.dumps(asdict(decision_result), default=enum_serializer),
            alert_data=json.dumps(alert),
            policy_result=json.dumps(policy_result_dict),
            ai_analysis=ai_analysis,
            execution_time_seconds=(time.time() - start_time)
        )

        if decision_result.escalate:
            # Handle escalation with communicator agent
            notification_result = await send_notification(alert, decision_result)
            return notification_result
            
        return {
            "status": "success",
            "message": f"Alert suppressed: {decision_result.reason}"
        }
            
    except Exception as e:
        logger.error(f"Error in escalation pipeline: {e}")
        return {"status": "error", "message": str(e)}
```

### Performance Tracking
```python
# Track report generation quality
metric = ReportGenerationMetric(
    timestamp=datetime.now(timezone.utc).isoformat(),
    shift_type="morning",
    generation_time_ms=elapsed_time,
    structured_output_success=True,
    fallback_used=False,
    extraction_method="pydantic_structured",
    alert_count=len(alerts),
    error_count=0,
    completeness_score=1.0,
    data_freshness="real-time",
    known_gaps=[],
    kb_analysis_used=True,
    ai_analysis_used=True
)

# Record metric and check health
REPORT_METRICS.record_metric(metric)
health_status = HEALTH_MONITOR.check_health(REPORT_METRICS)

if HEALTH_MONITOR.should_alert(REPORT_METRICS):
    logger.warning("Report generation quality degrading", extra=health_status)
```
```

## Troubleshooting

Common issues and solutions:

1. Missing timing data
   - Check alert source configuration
   - Verify webhook delivery
   - Check timezone conversions

2. Inconsistent counts
   - Verify deduplication logic
   - Check shift time boundaries
   - Confirm alert state transitions

3. KPI calculation issues
   - Validate KPI configuration
   - Check breach time recording
   - Verify timezone handling

4. Report quality degradation
   - Monitor fallback usage rate
   - Check data source health
   - Verify required section presence