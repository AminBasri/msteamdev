#!/usr/bin/env python3
"""
Test script to verify the timing calculation fix for daily_report.py
This script helps debug and test time to resolve calculations for specific incidents.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from msteamdev.daily_report import (
    load_alerts, 
    build_incident_states, 
    create_alert_details_with_timing,
    _load_log_sync,
    parse_ts_utc,
    calculate_time_to_resolve
)
from datetime import datetime
import arrow

def test_timing_calculations():
    """Test the timing calculations for specific incidents."""
    
    # Set up a test shift window that includes the incidents from crew.txt
    # Based on the test output, these incidents are in the morning shift window
    shift_start = datetime(2025, 10, 24, 7, 0, 0)  # 7 AM local time
    shift_end = datetime(2025, 10, 24, 16, 0, 0)   # 4 PM local time
    
    print("Testing timing calculations for incidents 410, 420, 421, 422, 423, 424, 425")
    print("=" * 80)
    
    # Load alerts for the shift window
    alerts = load_alerts(shift_start, shift_end)
    print(f"Found {len(alerts)} alerts in shift window")
    
    # Build incident states
    incident_numbers_in_window = set(str(alert.get('incident_number')) for alert in alerts)
    all_alerts = _load_log_sync()
    incident_states = build_incident_states(all_alerts, incident_numbers_in_window)
    
    print(f"Built incident states for {len(incident_states)} incidents")
    
    # Create alert details with timing
    alert_details = create_alert_details_with_timing(alerts, incident_states)
    
    print(f"Created {len(alert_details)} alert details with timing")
    print("\nDetailed timing information:")
    print("-" * 80)
    
    for detail in alert_details:
        print(f"Incident #{detail.incident_number}:")
        print(f"  Title: {detail.title[:60]}...")
        print(f"  Status: {detail.status}")
        print(f"  Severity: {detail.severity}")
        print(f"  Timestamp: {detail.timestamp}")
        print(f"  Acknowledged at: {detail.acknowledged_at or 'N/A'}")
        print(f"  Resolved at: {detail.resolved_at or 'N/A'}")
        print(f"  First response at: {detail.first_response_at or 'N/A'}")
        
        # Calculate time to resolve if we have both triggered and resolved times
        if detail.resolved_at and detail.timestamp:
            try:
                # The timestamp field is already in local time, so we need to find the original UTC timestamp
                # Let's look up the original triggered timestamp from the alert log
                triggered_ts = None
                resolved_ts = None
                
                for alert in all_alerts:
                    if str(alert.get('incident_number')) == str(detail.incident_number):
                        if alert.get('status') == 'triggered':
                            triggered_ts = parse_ts_utc(alert.get('timestamp'))
                        elif alert.get('status') == 'resolved':
                            resolved_ts = parse_ts_utc(alert.get('timestamp'))
                
                if triggered_ts and resolved_ts:
                    ttr = calculate_time_to_resolve(triggered_ts, resolved_ts)
                    print(f"  Time to Resolve: {ttr}")
                else:
                    print(f"  Time to Resolve: N/A (missing triggered/resolved data)")
            except Exception as e:
                print(f"  Time to Resolve: Error calculating - {e}")
        else:
            print(f"  Time to Resolve: N/A (missing data)")
        print()

def test_kpi_calculations():
    """Test the KPI calculations with detailed calculation steps."""
    
    print("\n" + "=" * 80)
    print("Testing KPI Calculations with Detailed Steps")
    print("=" * 80)
    
    # Set up a test shift window
    shift_start = datetime(2025, 10, 24, 7, 0, 0)
    shift_end = datetime(2025, 10, 24, 16, 0, 0)
    
    # Load alerts and calculate KPIs
    alerts = load_alerts(shift_start, shift_end)
    shift_start_arrow = arrow.get(shift_start)
    shift_end_arrow = arrow.get(shift_end)
    
    print(f"Shift Window: {shift_start_arrow.to('Asia/Kuala_Lumpur').format('YYYY-MM-DD HH:mm:ss')} to {shift_end_arrow.to('Asia/Kuala_Lumpur').format('YYYY-MM-DD HH:mm:ss')}")
    print(f"Total alerts in window: {len(alerts)}")
    print()
    
    # Manual calculation to show steps
    print("STEP-BY-STEP CALCULATION:")
    print("-" * 50)
    
    # Load all alerts to track state transitions
    all_alerts = _load_log_sync()
    incident_numbers_in_window = set(str(alert.get('incident_number')) for alert in alerts)
    incident_states = build_incident_states(all_alerts, incident_numbers_in_window)
    
    print(f"1. Incident States Built: {len(incident_states)} incidents")
    print("   Incident breakdown:")
    
    # Count by status and severity
    resolved_count = 0
    acknowledged_count = 0
    critical_count = 0
    warning_count = 0
    
    for inc_num, state in incident_states.items():
        status = state.get('final_status', 'unknown')
        severity = state.get('severity', 'unknown')
        
        if status == 'resolved':
            resolved_count += 1
        if status in ['acknowledged', 'resolved']:
            acknowledged_count += 1
        if severity == 'critical':
            critical_count += 1
        elif severity == 'warning':
            warning_count += 1
            
        print(f"   - Incident {inc_num}: {status.upper()} ({severity.upper()})")
    
    print(f"\n2. Counts:")
    print(f"   - Resolved: {resolved_count}")
    print(f"   - Acknowledged: {acknowledged_count}")
    print(f"   - Critical: {critical_count}")
    print(f"   - Warning: {warning_count}")
    
    # Calculate timing metrics manually
    print(f"\n3. Timing Calculations:")
    print("-" * 30)
    
    ttr_values = []  # Time to resolve
    tta_values = []  # Time to acknowledge
    ttfr_values = []  # Time to first response
    
    for inc_num, state in incident_states.items():
        if state['triggered_at']:
            print(f"   Incident {inc_num}:")
            
            # Time to acknowledge
            if state['acknowledged_at']:
                tta = (state['acknowledged_at'] - state['triggered_at']).total_seconds() / 60
                if tta >= 0:
                    tta_values.append(tta)
                    ttfr_values.append(tta)  # First response was acknowledgment
                    print(f"     TTA: {tta:.1f}m (triggered → acknowledged)")
            
            # Time to resolve
            if state['resolved_at']:
                ttr = (state['resolved_at'] - state['triggered_at']).total_seconds() / 60
                if ttr >= 0:
                    ttr_values.append(ttr)
                    # If resolved without acknowledgment, count as first response
                    if not state['acknowledged_at']:
                        ttfr_values.append(ttr)
                    print(f"     TTR: {ttr:.1f}m (triggered → resolved)")
    
    # Calculate averages
    print(f"\n4. Average Calculations:")
    print("-" * 30)
    
    if tta_values:
        mtta = sum(tta_values) / len(tta_values)
        print(f"   MTTA = {sum(tta_values):.1f}m ÷ {len(tta_values)} = {mtta:.1f}m")
    else:
        mtta = 0
        print(f"   MTTA = N/A (no acknowledged incidents)")
    
    if ttr_values:
        mttr = sum(ttr_values) / len(ttr_values)
        print(f"   MTTR = {sum(ttr_values):.1f}m ÷ {len(ttr_values)} = {mttr:.1f}m")
    else:
        mttr = 0
        print(f"   MTTR = N/A (no resolved incidents)")
    
    if ttfr_values:
        mttfr = sum(ttfr_values) / len(ttfr_values)
        print(f"   MTTFR = {sum(ttfr_values):.1f}m ÷ {len(ttfr_values)} = {mttfr:.1f}m")
    else:
        mttfr = 0
        print(f"   MTTFR = N/A (no first responses)")
    
    # Calculate rates
    print(f"\n5. Rate Calculations:")
    print("-" * 30)
    
    total_incidents = len(incident_states)
    resolution_rate = (resolved_count / total_incidents * 100) if total_incidents > 0 else 0
    acknowledgment_rate = (acknowledged_count / total_incidents * 100) if total_incidents > 0 else 0
    
    print(f"   Resolution Rate = {resolved_count} ÷ {total_incidents} × 100 = {resolution_rate:.1f}%")
    print(f"   Acknowledgment Rate = {acknowledged_count} ÷ {total_incidents} × 100 = {acknowledgment_rate:.1f}%")
    
    # Calculate escalations
    escalated_alerts = []
    for alert in alerts:
        from msteamdev.daily_report import check_escalation_eligibility
        is_escalated, reason = check_escalation_eligibility(alert)
        if is_escalated:
            escalated_alerts.append(alert)
    
    escalation_rate = (len(escalated_alerts) / total_incidents * 100) if total_incidents > 0 else 0
    print(f"   Escalation Rate = {len(escalated_alerts)} ÷ {total_incidents} × 100 = {escalation_rate:.1f}%")
    
    # SLA calculations
    print(f"\n6. S2/S3 SLA Calculations (Resolution thresholds):")
    print("-" * 50)
    
    # Severity-based SLA calculations
    from msteamdev.severity_config import SeverityConfig
    
    print(f"   Severity-based SLA Analysis:")
    print(f"   " + "-" * 40)
    
    # Get severity distribution
    severity_stats = SeverityConfig.get_severity_stats(alerts)
    print(f"   Severity Distribution: {severity_stats}")
    
    # Calculate SLA for each severity level
    for severity_level in ['S2', 'S3']:  # Focus on S2 and S3 for alerts
        severity_alerts = [alert for alert in alerts if SeverityConfig.map_alert_severity(alert) == severity_level]
        if not severity_alerts:
            print(f"   {severity_level} SLA: N/A (no {severity_level} alerts)")
            continue
        
        # Get resolution threshold for this severity (in hours, convert to minutes)
        resolution_threshold_hours = SeverityConfig.get_resolution_threshold(severity_level)
        resolution_threshold_minutes = resolution_threshold_hours * 60
        description = SeverityConfig.get_severity_description(severity_level)
        
        print(f"\n   {severity_level} SLA Analysis:")
        print(f"     Description: {description}")
        print(f"     Threshold: {resolution_threshold_hours}h ({resolution_threshold_minutes}min)")
        print(f"     Total alerts: {len(severity_alerts)}")
        
        # Calculate resolution breaches for this severity
        severity_ttr_values = []
        print(f"     Incident Analysis:")
        
        for alert in severity_alerts:
            inc_num = str(alert.get('incident_number'))
            if inc_num in incident_states and incident_states[inc_num].get('triggered_at'):
                state = incident_states[inc_num]
                # Only count incidents that were resolved
                if state.get('resolved_at'):
                    ttr = (state['resolved_at'] - state['triggered_at']).total_seconds() / 60
                    severity_ttr_values.append(ttr)
                    breach_status = "BREACH" if ttr > resolution_threshold_minutes else "OK"
                    print(f"       Incident {inc_num}: {ttr:.1f}m - {breach_status}")
                else:
                    print(f"       Incident {inc_num}: Not resolved - N/A")
        
        # Calculate compliance
        severity_breaches = sum(1 for t in severity_ttr_values if t > resolution_threshold_minutes)
        severity_total = len(severity_ttr_values)
        severity_compliance = ((severity_total - severity_breaches) / severity_total * 100) if severity_total > 0 else 0
        
        print(f"     Summary:")
        print(f"       Resolved incidents: {severity_total}")
        print(f"       Breaches (>{resolution_threshold_hours}h): {severity_breaches}")
        print(f"       Compliance: {severity_total - severity_breaches}/{severity_total} = {severity_compliance:.1f}%")
    
    # Final results
    print(f"\n7. FINAL RESULTS:")
    print("=" * 50)
    print(f"   Total Alerts: {len(alerts)}")
    print(f"   Unique Incidents: {total_incidents}")
    print(f"   Resolved Alerts: {resolved_count}")
    print(f"   Acknowledged Alerts: {acknowledged_count}")
    print(f"   Critical Alerts: {critical_count}")
    print(f"   Warning Alerts: {warning_count}")
    print(f"   Escalated Alerts: {len(escalated_alerts)}")
    print()
    print(f"   MTTA: {mtta:.1f}m")
    print(f"   MTTR: {mttr:.1f}m")
    print(f"   MTTFR: {mttfr:.1f}m")
    print()
    print(f"   Resolution Rate: {resolution_rate:.1f}%")
    print(f"   Acknowledgment Rate: {acknowledgment_rate:.1f}%")
    print(f"   Escalation Rate: {escalation_rate:.1f}%")
    
    # Calculate overall SLA compliance (MTTA/MTTFR with 5-minute threshold)
    print(f"\n5. SLA Compliance Calculation (MTTA/MTTFR - 5min threshold):")
    print("-" * 50)
    
    acknowledgment_threshold = 5  # 5-minute threshold for acknowledgment/first response
    total_breaches = 0
    total_with_timing = 0
    
    print(f"   Threshold: {acknowledgment_threshold} minutes")
    print(f"   Incident Analysis:")
    
    for inc_num, state in incident_states.items():
        if state.get('triggered_at'):
            # Calculate time to first response (acknowledgment or resolution)
            first_response_time = None
            response_type = None
            
            if state.get('acknowledged_at'):
                first_response_time = (state['acknowledged_at'] - state['triggered_at']).total_seconds() / 60
                response_type = "acknowledged"
            elif state.get('resolved_at'):
                first_response_time = (state['resolved_at'] - state['triggered_at']).total_seconds() / 60
                response_type = "resolved"
            
            if first_response_time is not None:
                total_with_timing += 1
                breach_status = "BREACH" if first_response_time > acknowledgment_threshold else "OK"
                if first_response_time > acknowledgment_threshold:
                    total_breaches += 1
                
                print(f"     Incident {inc_num}: {first_response_time:.1f}m ({response_type}) - {breach_status}")
    
    print(f"\n   Summary:")
    print(f"     Total incidents with timing: {total_with_timing}")
    print(f"     Breaches (>5min): {total_breaches}")
    print(f"     Compliance: {total_with_timing - total_breaches}/{total_with_timing} = {((total_with_timing - total_breaches) / total_with_timing * 100):.1f}%")
    
    sla_compliance = ((total_with_timing - total_breaches) / total_with_timing * 100) if total_with_timing > 0 else 0
    sla_breaches = total_breaches
    
    print(f"   SLA Compliance: {sla_compliance:.1f}% (MTTA/MTTFR - 5min threshold)")
    print(f"   SLA Breaches: {sla_breaches}")

def test_specific_incident(incident_number):
    """Test timing calculations for a specific incident."""
    
    print(f"\n" + "=" * 80)
    print(f"Testing Incident #{incident_number}")
    print("=" * 80)
    
    all_alerts = _load_log_sync()
    incident_alerts = []
    
    for alert in all_alerts:
        if str(alert.get('incident_number')) == str(incident_number):
            incident_alerts.append(alert)
    
    if not incident_alerts:
        print(f"No alerts found for incident #{incident_number}")
        return
    
    print(f"Found {len(incident_alerts)} alerts for incident #{incident_number}")
    print("\nAlert timeline:")
    print("-" * 40)
    
    # Sort by timestamp
    incident_alerts.sort(key=lambda x: x.get('timestamp', ''))
    
    for alert in incident_alerts:
        status = alert.get('status', 'unknown')
        timestamp = alert.get('timestamp', 'unknown')
        try:
            parsed_ts = parse_ts_utc(timestamp)
            local_time = parsed_ts.to('Asia/Kuala_Lumpur').format('YYYY-MM-DD HH:mm:ss')
            print(f"  {local_time} - {status.upper()}")
        except:
            print(f"  {timestamp} - {status.upper()}")
    
    # Calculate timing
    triggered_ts = None
    acknowledged_ts = None
    resolved_ts = None
    
    for alert in incident_alerts:
        status = alert.get('status', '').lower()
        timestamp = alert.get('timestamp')
        
        try:
            parsed_ts = parse_ts_utc(timestamp)
            if status == 'triggered' and not triggered_ts:
                triggered_ts = parsed_ts
            elif status == 'acknowledged' and not acknowledged_ts:
                acknowledged_ts = parsed_ts
            elif status == 'resolved' and not resolved_ts:
                resolved_ts = parsed_ts
        except:
            continue
    
    print(f"\nTiming Analysis:")
    if triggered_ts:
        print(f"  Triggered: {triggered_ts.to('Asia/Kuala_Lumpur').format('YYYY-MM-DD HH:mm:ss')}")
    if acknowledged_ts:
        print(f"  Acknowledged: {acknowledged_ts.to('Asia/Kuala_Lumpur').format('YYYY-MM-DD HH:mm:ss')}")
    if resolved_ts:
        print(f"  Resolved: {resolved_ts.to('Asia/Kuala_Lumpur').format('YYYY-MM-DD HH:mm:ss')}")
    
    if triggered_ts and acknowledged_ts:
        tta = (acknowledged_ts - triggered_ts).total_seconds() / 60
        print(f"  Time to Acknowledge: {tta:.1f} minutes")
    
    if triggered_ts and resolved_ts:
        ttr = (resolved_ts - triggered_ts).total_seconds() / 60
        print(f"  Time to Resolve: {ttr:.1f} minutes")
        print(f"  Time to Resolve (formatted): {calculate_time_to_resolve(triggered_ts, resolved_ts)}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test timing calculations for daily report')
    parser.add_argument('--incident', type=int, help='Test specific incident number')
    parser.add_argument('--kpis', action='store_true', help='Test KPI calculations')
    parser.add_argument('--all', action='store_true', help='Run all tests')
    
    args = parser.parse_args()
    
    if args.incident:
        test_specific_incident(args.incident)
    elif args.kpis:
        test_kpi_calculations()
    elif args.all:
        test_timing_calculations()
        test_kpi_calculations()
    else:
        # Default: run timing calculations test
        test_timing_calculations()
