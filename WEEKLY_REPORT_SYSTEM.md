# Weekly Report System for NOC Operations

## Overview

This system provides comprehensive weekly reporting capabilities for NOC operations, similar to Otobo's data storage approach. It automatically aggregates daily shift metrics and generates detailed weekly analysis reports with trends, recommendations, and performance assessments.

## System Architecture

### 1. Daily Metrics Storage (`daily_metrics_storage.py`)
- **Purpose**: Stores daily shift metrics to JSON files for weekly aggregation
- **Location**: `data/daily_metrics/` directory
- **Format**: `YYYY-MM-DD_shift_metrics.json` (e.g., `2025-10-24_morning_metrics.json`)
- **Data Structure**: Comprehensive metrics including alerts, timing, SLA compliance, and incident details

### 2. Weekly Report Generator (`weekly_report_generator.py`)
- **Purpose**: Aggregates daily metrics and generates detailed weekly reports
- **Features**: 
  - Trend analysis across the week
  - Performance assessment with recommendations
  - Detailed breakdown by day and shift
  - SLA compliance analysis
  - Critical alert tracking

### 3. Integration with Daily Reports (`daily_report.py`)
- **Automatic Storage**: Every daily report automatically saves metrics to JSON
- **Seamless Integration**: No manual intervention required
- **Error Handling**: Metrics storage failures don't affect daily report generation

## Key Features

### Daily Metrics Storage
- **Comprehensive Data**: Total alerts, incidents, timing metrics, SLA compliance
- **Incident Details**: Full incident information for detailed analysis
- **Metadata**: Generation timestamps, data versioning
- **Error Resilience**: Graceful handling of storage failures

### Weekly Report Analysis
- **Aggregated Metrics**: Week-long totals and averages
- **Trend Analysis**: Alert volume, SLA compliance, resolution rates
- **Performance Assessment**: Automated performance grading (🟢 Excellent, 🟡 Good, 🔴 Needs Improvement)
- **Recommendations**: Actionable insights based on performance data
- **Daily Breakdown**: Individual day performance within the week

### SLA Compliance Tracking
- **Overall SLA**: MTTA/MTTFR compliance with 5-minute threshold
- **Severity-based SLA**: S2 (8h resolution) and S3 (24h resolution) compliance
- **Breach Analysis**: Detailed breach tracking and analysis

## Usage Examples

### Generate Daily Report (with automatic metrics storage)
```bash
# Morning shift
python -m msteamdev.daily_report --shift morning

# Evening shift  
python -m msteamdev.daily_report --shift evening

# Specific date range
python -c "
from datetime import datetime
from msteamdev.daily_report import run
run('morning', datetime(2025, 10, 24, 7, 0, 0), datetime(2025, 10, 24, 16, 0, 0))
"
```

### Generate Weekly Reports
```bash
# Last week's report
python -m msteamdev.weekly_report_generator --last-week

# Specific date range
python -m msteamdev.weekly_report_generator --start 2025-10-21 --end 2025-10-27

# Single day (for testing)
python -m msteamdev.weekly_report_generator --start 2025-10-24 --end 2025-10-24
```

### Test the Complete System
```bash
# Run comprehensive test
python tests/test_weekly_report_system.py --test

# Simulate multiple days
python tests/test_weekly_report_system.py --simulate
```

## Sample Weekly Report Output

```
================================================================================
WEEKLY NOC REPORT | 2025-10-24 to 2025-10-24
================================================================================

1. WEEKLY SUMMARY:
--------------------------------------------------
   Period: 2025-10-24 to 2025-10-24
   Total Shifts: 1
   Total Alerts: 7
   Total Incidents: 7

2. ALERT BREAKDOWN:
--------------------------------------------------
   Resolved Alerts: 5
   Acknowledged Alerts: 7
   Critical Alerts: 2
   Warning Alerts: 5
   Escalated Alerts: 3

3. AVERAGE TIMING METRICS:
--------------------------------------------------
   Average MTTA: 1454.6m
   Average MTTR: 2042.2m
   Average MTTFR: 1454.6m

4. AVERAGE RATES:
--------------------------------------------------
   Average Resolution Rate: 71.4%
   Average Acknowledgment Rate: 100.0%
   Average Escalation Rate: 42.9%

5. WEEKLY SLA ANALYSIS:
--------------------------------------------------
   Average SLA Compliance: 57.1% (MTTA/MTTFR - 5min threshold)
   Total SLA Breaches: 3
   Average S2 SLA Compliance: 100.0% (Critical - 8h resolution)
   Average S3 SLA Compliance: 75.0% (Warning - 24h resolution)

6. DAILY BREAKDOWN:
--------------------------------------------------
   2025-10-24 (morning):
     Alerts: 7, Resolved: 5
     SLA: 57.1%, Breaches: 3
     MTTA: 1454.6m, MTTR: 2042.2m

7. TREND ANALYSIS:
--------------------------------------------------
   Alert Volume Trend: decreasing
   SLA Compliance Trend: declining
   Total Critical Alerts: 2
   Days with Critical Alerts: 1/1

8. WEEKLY PERFORMANCE ASSESSMENT:
--------------------------------------------------
   Overall Performance: 🔴 NEEDS IMPROVEMENT
   Key Metrics:
     - SLA Compliance: 57.1% (Target: ≥90%)
     - Resolution Rate: 71.4% (Target: ≥80%)
     - Escalation Rate: 42.9% (Lower is better)

9. RECOMMENDATIONS:
--------------------------------------------------
   1. Focus on improving first response times to meet 5-minute SLA threshold
   2. Increase resolution rate through better incident management processes
   3. Review escalation policies to reduce unnecessary escalations
   4. Investigate root causes of critical alerts to prevent recurrence
```

## Data Storage Structure

### Daily Metrics JSON Format
```json
{
  "date": "2025-10-24",
  "shift_type": "morning",
  "shift_start": "2025-10-24T07:00:00",
  "shift_end": "2025-10-24T16:00:00",
  "total_alerts": 7,
  "unique_incidents": 7,
  "resolved_alerts": 5,
  "acknowledged_alerts": 7,
  "critical_alerts": 2,
  "warning_alerts": 5,
  "escalated_alerts": 3,
  "mtta_minutes": 1454.6,
  "mttr_minutes": 2042.2,
  "mttfr_minutes": 1454.6,
  "resolution_rate": 71.4,
  "acknowledgment_rate": 100.0,
  "escalation_rate": 42.9,
  "sla_compliance": 57.1,
  "sla_breaches": 3,
  "s2_sla_compliance": 100.0,
  "s3_sla_compliance": 75.0,
  "incident_details": [...],
  "generated_at": "2025-10-27T10:49:08.460Z",
  "data_version": "1.0"
}
```

## Benefits

### For NOC Management
- **Historical Analysis**: Track performance trends over time
- **Data-Driven Decisions**: Make informed decisions based on aggregated metrics
- **Performance Monitoring**: Identify areas for improvement
- **Compliance Tracking**: Monitor SLA compliance across severity levels

### For Operations Teams
- **Automated Reporting**: No manual data collection required
- **Detailed Analysis**: Comprehensive breakdown of daily and weekly performance
- **Actionable Insights**: Clear recommendations for process improvements
- **Trend Visibility**: Understand patterns in alert volume and resolution times

### For System Reliability
- **Proactive Monitoring**: Identify recurring issues before they become critical
- **Process Optimization**: Data-driven insights for improving incident management
- **Resource Planning**: Understand workload patterns for better resource allocation

## Integration with Existing Systems

The weekly report system seamlessly integrates with the existing daily report infrastructure:

1. **Daily Reports**: Automatically save metrics without affecting existing functionality
2. **Alert Processing**: Uses the same alert data and KPI calculations
3. **SLA Tracking**: Maintains consistency with existing SLA definitions
4. **Error Handling**: Robust error handling ensures daily reports continue even if metrics storage fails

## Future Enhancements

- **Monthly Reports**: Extend to monthly aggregation and analysis
- **Custom Date Ranges**: Support for arbitrary date range reporting
- **Export Formats**: CSV, Excel, and PDF export capabilities
- **Dashboard Integration**: Web-based dashboard for real-time metrics viewing
- **Alert Correlation**: Advanced pattern recognition across incidents
- **Performance Benchmarking**: Compare performance against industry standards

## Troubleshooting

### Common Issues
1. **Missing Metrics Files**: Ensure daily reports are running successfully
2. **Permission Errors**: Check write permissions for `data/daily_metrics/` directory
3. **Import Errors**: Verify Python path configuration in test scripts

### Debug Commands
```bash
# Check available metrics
python -c "from msteamdev.daily_metrics_storage import daily_storage; print(daily_storage.list_available_dates())"

# Test metrics loading
python -c "from msteamdev.daily_metrics_storage import daily_storage; print(daily_storage.load_daily_metrics('2025-10-24', 'morning'))"
```

This system provides a robust foundation for comprehensive NOC reporting and analysis, enabling data-driven decision making and continuous improvement of operational processes.
