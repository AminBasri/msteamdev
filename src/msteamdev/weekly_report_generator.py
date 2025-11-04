"""
Weekly Report Generator

This module generates comprehensive weekly reports with detailed analysis,
similar to the test_timing_fix.py output but aggregated across the week.
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
import arrow
from dataclasses import dataclass
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
import smtplib

# Import logging setup
from src.msteamdev.logging_setup import get_module_logger
from src.msteamdev.daily_metrics_storage import DailyMetricsStorage, DailyMetrics, daily_storage
from src.msteamdev.crew import load_agents, load_yaml
from src.msteamdev.models import ShiftReportOutput, ReportMetadata
from crewai import Task, Crew

logger = get_module_logger(__name__, log_filename='weekly_report.log')

def send_report_email(subject: str, body: str, report_metadata: Optional[ReportMetadata] = None) -> bool:
    """Send the report via email."""
    smtp_host = os.getenv('SMTP_HOST', '')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    smtp_username = os.getenv('SMTP_USERNAME', '')
    smtp_password = os.getenv('SMTP_PASSWORD', '')
    report_email = os.getenv('REPORT_EMAIL', '')
    
    if not all([smtp_host, smtp_username, smtp_password, report_email]):
        logger.error("Missing SMTP configuration")
        return False
        
    try:
        logger.info(f"Preparing to send email to {report_email}")
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = formataddr((str(Header('NOC Team', 'utf-8')), 'noc@infopro.com.my'))
        msg['To'] = report_email
        
        text = MIMEText(body, 'plain')
        msg.attach(text)
        
        logger.info(f"Connecting to SMTP server {smtp_host}:{smtp_port}")
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
            
        logger.info("Email sent successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False

def send_rocketchat_webhook_message(message: str) -> bool:
    """Send a message to Rocket.Chat via webhook."""
    webhook_url = os.getenv("ROCKETCHAT_WEBHOOK_URL", "")
    
    if not webhook_url:
        logger.warning("ROCKETCHAT_WEBHOOK_URL not configured")
        return False
        
    webhook_token = os.getenv("ROCKETCHAT_WEBHOOK_TOKEN")
    if webhook_token and webhook_token not in webhook_url:
        webhook_url = f"{webhook_url}/{webhook_token}"
    
    try:
        payload = {
            "text": message,
            "alias": "NOC Weekly Report",
            "emoji": ":chart_with_upwards_trend:"
        }
        response = requests.post(webhook_url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("Successfully sent Rocket.Chat webhook notification")
            return True
        else:
            logger.error(f"Rocket.Chat webhook failed: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Failed to send Rocket.Chat webhook: {str(e)}")
        return False

@dataclass
class WeeklyAggregatedMetrics:
    """Weekly aggregated metrics data structure."""
    week_start: str  # YYYY-MM-DD
    week_end: str    # YYYY-MM-DD
    total_shifts: int
    
    # Aggregated counts
    total_alerts: int
    total_incidents: int
    total_resolved: int
    total_acknowledged: int
    total_critical: int
    total_warning: int
    total_escalated: int
    
    # Average timing metrics
    avg_mtta_minutes: float
    avg_mttr_minutes: float
    
    # Average rates
    avg_resolution_rate: float
    avg_acknowledgment_rate: float
    avg_escalation_rate: float
    
    # KPI metrics
    avg_kpi_compliance: float
    total_kpi_breaches: int
    avg_p2_kpi_compliance: float
    avg_p3_kpi_compliance: float
    
    # Daily breakdown
    daily_metrics: List[DailyMetrics]
    
    # Trend analysis
    trends: Dict[str, Any]

class WeeklyReportGenerator:
    """Generates comprehensive weekly reports with detailed analysis."""
    
    def __init__(self, storage: DailyMetricsStorage = None):
        """Initialize with storage instance."""
        self.storage = storage or daily_storage
    
    def generate_weekly_report(self, week_start: str, week_end: str) -> Optional[WeeklyAggregatedMetrics]:
        """Generate comprehensive weekly report."""
        try:
            logger.info(f"Generating weekly report for {week_start} to {week_end}")
            
            # Load all daily metrics for the week
            daily_metrics_list = self.storage.get_weekly_metrics(week_start, week_end)
            
            if not daily_metrics_list:
                logger.warning(f"No daily metrics found for period {week_start} to {week_end}")
                return None
            
            # Aggregate metrics
            aggregated = self._aggregate_weekly_metrics(daily_metrics_list, week_start, week_end)
            
            # Analyze trends
            aggregated.trends = self._analyze_trends(daily_metrics_list)
            
            logger.info(f"Weekly report generated: {aggregated.total_alerts} alerts across {aggregated.total_shifts} shifts")
            return aggregated
            
        except Exception as e:
            logger.error(f"Failed to generate weekly report: {e}")
            return None
    
    def _aggregate_weekly_metrics(self, daily_metrics: List[DailyMetrics], week_start: str, week_end: str) -> WeeklyAggregatedMetrics:
        """Aggregate daily metrics into weekly totals."""
        
        total_shifts = len(daily_metrics)
        
        # Sum all counts
        total_alerts = sum(m.total_alerts for m in daily_metrics)
        total_incidents = sum(m.unique_incidents for m in daily_metrics)
        total_resolved = sum(m.resolved_alerts for m in daily_metrics)
        total_acknowledged = sum(m.acknowledged_alerts for m in daily_metrics)
        total_critical = sum(m.critical_alerts for m in daily_metrics)
        total_warning = sum(m.warning_alerts for m in daily_metrics)
        total_escalated = sum(m.escalated_alerts for m in daily_metrics)
        
        # Calculate averages for timing metrics
        valid_mtta = [m.mtta_minutes for m in daily_metrics if m.mtta_minutes > 0]
        valid_mttr = [m.mttr_minutes for m in daily_metrics if m.mttr_minutes > 0]
        
        avg_mtta = sum(valid_mtta) / len(valid_mtta) if valid_mtta else 0.0
        avg_mttr = sum(valid_mttr) / len(valid_mttr) if valid_mttr else 0.0
        
        # Calculate average rates
        avg_resolution_rate = sum(m.resolution_rate for m in daily_metrics) / total_shifts
        avg_acknowledgment_rate = sum(m.acknowledgment_rate for m in daily_metrics) / total_shifts
        avg_escalation_rate = sum(m.escalation_rate for m in daily_metrics) / total_shifts
        
        # Calculate average KPI metrics
        avg_kpi_compliance = sum(m.kpi_compliance for m in daily_metrics) / total_shifts
        total_kpi_breaches = sum(m.kpi_breaches for m in daily_metrics)
        
        valid_p2_kpi = [m.p2_kpi_compliance for m in daily_metrics if m.p2_kpi_compliance > 0]
        valid_p3_kpi = [m.p3_kpi_compliance for m in daily_metrics if m.p3_kpi_compliance > 0]
        
        avg_p2_kpi_compliance = sum(valid_p2_kpi) / len(valid_p2_kpi) if valid_p2_kpi else 0.0
        avg_p3_kpi_compliance = sum(valid_p3_kpi) / len(valid_p3_kpi) if valid_p3_kpi else 0.0
        
        return WeeklyAggregatedMetrics(
            week_start=week_start,
            week_end=week_end,
            total_shifts=total_shifts,
            
            total_alerts=total_alerts,
            total_incidents=total_incidents,
            total_resolved=total_resolved,
            total_acknowledged=total_acknowledged,
            total_critical=total_critical,
            total_warning=total_warning,
            total_escalated=total_escalated,
            
            avg_mtta_minutes=avg_mtta,
            avg_mttr_minutes=avg_mttr,
            
            avg_resolution_rate=avg_resolution_rate,
            avg_acknowledgment_rate=avg_acknowledgment_rate,
            avg_escalation_rate=avg_escalation_rate,
            
            avg_kpi_compliance=avg_kpi_compliance,
            total_kpi_breaches=total_kpi_breaches,
            avg_p2_kpi_compliance=avg_p2_kpi_compliance,
            avg_p3_kpi_compliance=avg_p3_kpi_compliance,
            
            daily_metrics=daily_metrics,
            trends={}  # Will be filled by _analyze_trends
        )
    
    def _analyze_trends(self, daily_metrics: List[DailyMetrics]) -> Dict[str, Any]:
        """Analyze trends across the week."""
        trends = {}
        
        try:
            # Sort by date
            sorted_metrics = sorted(daily_metrics, key=lambda x: x.date)
            
            # Alert volume trend
            alert_counts = [m.total_alerts for m in sorted_metrics]
            trends['alert_volume'] = {
                'daily_counts': alert_counts,
                'trend': 'increasing' if len(alert_counts) > 1 and alert_counts[-1] > alert_counts[0] else 'decreasing',
                'peak_day': sorted_metrics[alert_counts.index(max(alert_counts))].date if alert_counts else None,
                'lowest_day': sorted_metrics[alert_counts.index(min(alert_counts))].date if alert_counts else None
            }
            
            # KPI compliance trend
            kpi_compliance = [m.kpi_compliance for m in sorted_metrics]
            trends['kpi_compliance'] = {
                'daily_compliance': kpi_compliance,
                'trend': 'improving' if len(kpi_compliance) > 1 and kpi_compliance[-1] > kpi_compliance[0] else 'declining',
                'best_day': sorted_metrics[kpi_compliance.index(max(kpi_compliance))].date if kpi_compliance else None,
                'worst_day': sorted_metrics[kpi_compliance.index(min(kpi_compliance))].date if kpi_compliance else None
            }
            
            # Resolution rate trend
            resolution_rates = [m.resolution_rate for m in sorted_metrics]
            trends['resolution_rate'] = {
                'daily_rates': resolution_rates,
                'trend': 'improving' if len(resolution_rates) > 1 and resolution_rates[-1] > resolution_rates[0] else 'declining'
            }
            
            # Critical alerts trend
            critical_counts = [m.critical_alerts for m in sorted_metrics]
            trends['critical_alerts'] = {
                'daily_counts': critical_counts,
                'total_critical': sum(critical_counts),
                'days_with_critical': sum(1 for count in critical_counts if count > 0)
            }
            
            return trends
            
        except Exception as e:
            logger.error(f"Failed to analyze trends: {e}")
            return {}
    
    def print_detailed_weekly_report(self, aggregated: WeeklyAggregatedMetrics) -> str:
        """Generate detailed weekly report text similar to test_timing_fix.py format."""
        output = []
        
        output.append("=" * 80)
        output.append(f"WEEKLY NOC REPORT | {aggregated.week_start} to {aggregated.week_end}")
        output.append("=" * 80)
        
        output.append(f"\n1. WEEKLY SUMMARY:")
        output.append("-" * 50)
        output.append(f"   Period: {aggregated.week_start} to {aggregated.week_end}")
        output.append(f"   Total Shifts: {aggregated.total_shifts}")
        output.append(f"   Total Alerts: {aggregated.total_alerts}")
        output.append(f"   Total Incidents: {aggregated.total_incidents}")
        
        output.append(f"\n2. ALERT BREAKDOWN:")
        output.append("-" * 50)
        output.append(f"   Resolved Alerts: {aggregated.total_resolved}")
        output.append(f"   Acknowledged Alerts: {aggregated.total_acknowledged}")
        output.append(f"   Critical Alerts: {aggregated.total_critical}")
        output.append(f"   Warning Alerts: {aggregated.total_warning}")
        output.append(f"   Escalated Alerts: {aggregated.total_escalated}")
        
        output.append(f"\n3. AVERAGE TIMING METRICS:")
        output.append("-" * 50)
        output.append(f"   Average MTTA: {aggregated.avg_mtta_minutes:.1f}m")
        output.append(f"   Average MTTR: {aggregated.avg_mttr_minutes:.1f}m")
        
        output.append(f"\n4. AVERAGE RATES:")
        output.append("-" * 50)
        output.append(f"   Average Resolution Rate: {aggregated.avg_resolution_rate:.1f}%")
        output.append(f"   Average Acknowledgment Rate: {aggregated.avg_acknowledgment_rate:.1f}%")
        output.append(f"   Average Escalation Rate: {aggregated.avg_escalation_rate:.1f}%")
        
        output.append(f"\n5. WEEKLY KPI ANALYSIS:")
        output.append("-" * 50)
        output.append(f"   Average KPI Compliance: {aggregated.avg_kpi_compliance:.1f}% (MTTA - 5min threshold)")
        output.append(f"   Total KPI Breaches: {aggregated.total_kpi_breaches}")
        output.append(f"   Average P2 KPI Compliance: {aggregated.avg_p2_kpi_compliance:.1f}% (Critical - 8h resolution)")
        output.append(f"   Average P3 KPI Compliance: {aggregated.avg_p3_kpi_compliance:.1f}% (Warning - 24h resolution)")
        
        output.append(f"\n6. DAILY BREAKDOWN:")
        output.append("-" * 50)
        for metrics in aggregated.daily_metrics:
            output.append(f"   {metrics.date} ({metrics.shift_type}):")
            output.append(f"     Alerts: {metrics.total_alerts}, Resolved: {metrics.resolved_alerts}")
            output.append(f"     KPI: {metrics.kpi_compliance:.1f}%, Breaches: {metrics.kpi_breaches}")
            output.append(f"     MTTA: {metrics.mtta_minutes:.1f}m, MTTR: {metrics.mttr_minutes:.1f}m")
        
        output.append(f"\n7. TREND ANALYSIS:")
        output.append("-" * 50)
        if aggregated.trends:
            trends = aggregated.trends
            
            # Alert volume trend
            if 'alert_volume' in trends:
                alert_trend = trends['alert_volume']
                output.append(f"   Alert Volume Trend: {alert_trend['trend']}")
                if alert_trend['peak_day']:
                    output.append(f"   Peak Alert Day: {alert_trend['peak_day']}")
                if alert_trend['lowest_day']:
                    output.append(f"   Lowest Alert Day: {alert_trend['lowest_day']}")
            
            # KPI compliance trend
            if 'kpi_compliance' in trends:
                kpi_trend = trends['kpi_compliance']
                output.append(f"   KPI Compliance Trend: {kpi_trend['trend']}")
                if kpi_trend['best_day']:
                    output.append(f"   Best KPI Day: {kpi_trend['best_day']}")
                if kpi_trend['worst_day']:
                    output.append(f"   Worst KPI Day: {kpi_trend['worst_day']}")
            
            # Critical alerts analysis
            if 'critical_alerts' in trends:
                critical_trend = trends['critical_alerts']
                output.append(f"   Total Critical Alerts: {critical_trend['total_critical']}")
                output.append(f"   Days with Critical Alerts: {critical_trend['days_with_critical']}/{aggregated.total_shifts}")
        
        output.append(f"\n8. WEEKLY PERFORMANCE ASSESSMENT:")
        output.append("-" * 50)
        
        # Performance assessment
        if aggregated.avg_kpi_compliance >= 90 and aggregated.avg_resolution_rate >= 80:
            performance = "EXCELLENT"
            emoji = "🟢"
        elif aggregated.avg_kpi_compliance >= 80 and aggregated.avg_resolution_rate >= 70:
            performance = "GOOD"
            emoji = "🟡"
        else:
            performance = "NEEDS IMPROVEMENT"
            emoji = "🔴"
        
        output.append(f"   Overall Performance: {emoji} {performance}")
        output.append(f"   Key Metrics:")
        output.append(f"     - KPI Compliance: {aggregated.avg_kpi_compliance:.1f}% (Target: ≥90%)")
        output.append(f"     - Resolution Rate: {aggregated.avg_resolution_rate:.1f}% (Target: ≥80%)")
        output.append(f"     - Escalation Rate: {aggregated.avg_escalation_rate:.1f}% (Lower is better)")
        
        output.append(f"\n9. RECOMMENDATIONS:")
        output.append("-" * 50)
        
        recommendations = []
        
        if aggregated.avg_kpi_compliance < 90:
            recommendations.append("1. Focus on improving first response times to meet 5-minute KPI threshold")
        
        if aggregated.avg_resolution_rate < 80:
            recommendations.append("Increase resolution rate through better incident management processes")
        
        if aggregated.avg_escalation_rate > 30:
            recommendations.append("Review escalation policies to reduce unnecessary escalations")
        
        if aggregated.total_critical > 0:
            recommendations.append("Investigate root causes of critical alerts to prevent recurrence")
        
        if not recommendations:
            recommendations.append("Continue current operational excellence")
        
        for i, rec in enumerate(recommendations, 1):
            output.append(f"   {i}. {rec}")
        
        output.append("\n" + "=" * 80)
        output.append("END OF WEEKLY REPORT")
        output.append("=" * 80)
        
        # Print the report
        report_text = "\n".join(output)
        print(report_text)
        
        return report_text
    
    def generate_ai_weekly_report(self, aggregated: WeeklyAggregatedMetrics) -> Optional[ShiftReportOutput]:
        """Generate AI-powered weekly report using CrewAI."""
        try:
            logger.info("Generating AI-powered weekly report")
            
            # Load agents and tasks
            agents = load_agents()
            tasks_def = load_yaml("src/msteamdev/config/tasks_enhanced.yaml")
            
            reporter_agent = agents.get("reporter")
            if not reporter_agent:
                logger.error("Missing reporter agent")
                return None
            
            weekly_task_def = tasks_def.get("weekly_report")
            if not weekly_task_def:
                logger.error("Missing weekly_report task definition")
                return None
            
            # Prepare data for AI analysis
            daily_breakdown_data = self._format_daily_breakdown(aggregated.daily_metrics)
            trend_analysis_data = self._format_trend_analysis(aggregated.trends)
            
            # Determine performance status and grade
            performance_status, performance_grade, performance_emoji = self._assess_performance(aggregated)
            
            # Create task
            weekly_task = Task(
                description=weekly_task_def["description"].format(
                    week_start=aggregated.week_start,
                    week_end=aggregated.week_end,
                    total_shifts=aggregated.total_shifts,
                    total_alerts=aggregated.total_alerts,
                    total_incidents=aggregated.total_incidents,
                    total_resolved=aggregated.total_resolved,
                    total_acknowledged=aggregated.total_acknowledged,
                    total_critical=aggregated.total_critical,
                    total_warning=aggregated.total_warning,
                    total_escalated=aggregated.total_escalated,
                    avg_mtta_minutes=aggregated.avg_mtta_minutes,
                    avg_mttr_minutes=aggregated.avg_mttr_minutes,
                    avg_resolution_rate=aggregated.avg_resolution_rate,
                    avg_acknowledgment_rate=aggregated.avg_acknowledgment_rate,
                    avg_escalation_rate=aggregated.avg_escalation_rate,
                    avg_kpi_compliance=aggregated.avg_kpi_compliance,
                    total_kpi_breaches=aggregated.total_kpi_breaches,
                    avg_p2_kpi_compliance=aggregated.avg_p2_kpi_compliance,
                    avg_p3_kpi_compliance=aggregated.avg_p3_kpi_compliance,
                    daily_breakdown_data=daily_breakdown_data,
                    trend_analysis_data=trend_analysis_data,
                    performance_status=performance_status,
                    performance_grade=performance_grade,
                    performance_emoji=performance_emoji,
                    alert_volume_trend=aggregated.trends.get('alert_volume', {}).get('trend', 'stable'),
                    kpi_compliance_trend=aggregated.trends.get('kpi_compliance', {}).get('trend', 'stable'),
                    resolution_rate_trend=aggregated.trends.get('resolution_rate', {}).get('trend', 'stable'),
                    critical_alert_analysis=f"Total: {aggregated.trends.get('critical_alerts', {}).get('total_critical', 0)}, Days with critical: {aggregated.trends.get('critical_alerts', {}).get('days_with_critical', 0)}/{aggregated.total_shifts}"
                ),
                expected_output=weekly_task_def["expected_output"],
                agent=reporter_agent,
                output_pydantic=ShiftReportOutput
            )
            
            # Run crew
            crew = Crew(
                agents=[reporter_agent],
                tasks=[weekly_task],
                verbose=True
            )
            
            logger.info("Kicking off AI crew for weekly report")
            result = crew.kickoff()
            
            output = self._extract_report_output(result)
            
            if not output.subject or not output.body:
                logger.warning("Invalid AI output, using fallback")
                output.subject = f"{performance_emoji} NOC Weekly Report | {aggregated.week_start} to {aggregated.week_end} | {aggregated.total_alerts} Alerts | {performance_grade} Performance"
                output.body = f"Weekly report for {aggregated.week_start} to {aggregated.week_end}\n\nProcessed {aggregated.total_alerts} alerts across {aggregated.total_shifts} shifts."
            
            logger.info("AI-powered weekly report generated successfully")
            logger.info(f"Subject: {output.subject}")
            logger.info(f"Body length: {len(output.body)} characters")
            
            return output
            
        except Exception as e:
            logger.error(f"AI-powered weekly report generation failed: {e}", exc_info=True)
            return None
    
    def _format_daily_breakdown(self, daily_metrics: List[DailyMetrics]) -> str:
        """Format daily breakdown data for AI analysis."""
        breakdown_lines = []
        
        for metrics in daily_metrics:
            breakdown_lines.append(
                f"- {metrics.date} ({metrics.shift_type}): "
                f"Alerts: {metrics.total_alerts}, "
                f"Resolved: {metrics.resolved_alerts}, "
                f"KPI: {metrics.kpi_compliance:.1f}%, "
                f"Breaches: {metrics.kpi_breaches}, "
                f"MTTA: {metrics.mtta_minutes:.1f}m, "
                f"MTTR: {metrics.mttr_minutes:.1f}m"
            )
        
        return "\n".join(breakdown_lines) if breakdown_lines else "No daily data available"
    
    def _format_trend_analysis(self, trends: Dict[str, Any]) -> str:
        """Format trend analysis data for AI analysis."""
        trend_lines = []
        
        if 'alert_volume' in trends:
            alert_trend = trends['alert_volume']
            trend_lines.append(f"Alert Volume: {alert_trend.get('trend', 'stable')}")
            if alert_trend.get('peak_day'):
                trend_lines.append(f"Peak Alert Day: {alert_trend['peak_day']}")
            if alert_trend.get('lowest_day'):
                trend_lines.append(f"Lowest Alert Day: {alert_trend['lowest_day']}")
        
        if 'kpi_compliance' in trends:
            kpi_trend = trends['kpi_compliance']
            trend_lines.append(f"KPI Compliance: {kpi_trend.get('trend', 'stable')}")
            if kpi_trend.get('best_day'):
                trend_lines.append(f"Best KPI Day: {kpi_trend['best_day']}")
            if kpi_trend.get('worst_day'):
                trend_lines.append(f"Worst KPI Day: {kpi_trend['worst_day']}")
        
        if 'resolution_rate' in trends:
            resolution_trend = trends['resolution_rate']
            trend_lines.append(f"Resolution Rate: {resolution_trend.get('trend', 'stable')}")
        
        if 'critical_alerts' in trends:
            critical_trend = trends['critical_alerts']
            trend_lines.append(f"Total Critical Alerts: {critical_trend.get('total_critical', 0)}")
            trend_lines.append(f"Days with Critical: {critical_trend.get('days_with_critical', 0)}")
        
        return "\n".join(trend_lines) if trend_lines else "No trend data available"
    
    def _assess_performance(self, aggregated: WeeklyAggregatedMetrics) -> Tuple[str, str, str]:
        """Assess overall performance and return status, grade, and emoji."""
        if aggregated.avg_kpi_compliance >= 90 and aggregated.avg_resolution_rate >= 80:
            performance_status = "EXCELLENT"
            performance_grade = "A"
            performance_emoji = "🟢"
        elif aggregated.avg_kpi_compliance >= 80 and aggregated.avg_resolution_rate >= 70:
            performance_status = "GOOD"
            performance_grade = "B"
            performance_emoji = "🟡"
        elif aggregated.avg_kpi_compliance >= 70 and aggregated.avg_resolution_rate >= 60:
            performance_status = "FAIR"
            performance_grade = "C"
            performance_emoji = "🟠"
        else:
            performance_status = "NEEDS IMPROVEMENT"
            performance_grade = "D"
            performance_emoji = "🔴"
        
        return performance_status, performance_grade, performance_emoji
    
    def _extract_report_output(self, result: Any) -> ShiftReportOutput:
        """Extract report output from crew result."""
        try:
            if hasattr(result, 'pydantic') and result.pydantic:
                logger.info("Using pydantic structured output")
                return result.pydantic
                
            elif hasattr(result, 'json_dict') and result.json_dict:
                logger.info("Using json_dict output")
                return ShiftReportOutput(**result.json_dict)
                
            elif hasattr(result, 'raw') and result.raw:
                logger.info("Parsing raw output")
                lines = result.raw.split('\n')
                subject = lines[0] if lines else "NOC Weekly Report"
                body = '\n'.join(lines[1:]) if len(lines) > 1 else "No content available"
                
                return ShiftReportOutput(
                    subject=subject,
                    body=body,
                    metadata=ReportMetadata(
                        generation_timestamp=datetime.now(timezone.utc).isoformat(),
                        alert_count=0,
                        critical_alerts=0,
                        kpi_breaches=0,
                        mttr_minutes=0.0
                    )
                )
        except Exception as e:
            logger.error(f"Failed to extract report: {e}")
        
        # Fallback
        return ShiftReportOutput(
            subject="NOC Weekly Report",
            body="Weekly report generation encountered an error.",
            metadata=ReportMetadata(
                generation_timestamp=datetime.now(timezone.utc).isoformat(),
                alert_count=0,
                critical_alerts=0,
                kpi_breaches=0,
                mttr_minutes=0.0
            )
        )

def generate_weekly_report_for_date_range(start_date: str, end_date: str, use_ai: bool = True) -> None:
    """Generate and print weekly report for specified date range."""
    generator = WeeklyReportGenerator()
    aggregated = generator.generate_weekly_report(start_date, end_date)
    
    if aggregated:
        if use_ai:
            # Generate AI-powered report
            ai_output = generator.generate_ai_weekly_report(aggregated)
            if ai_output:
                # Print report
                print("=" * 80)
                print("AI-POWERED WEEKLY REPORT")
                print("=" * 80)
                print(f"Subject: {ai_output.subject}")
                print(f"\nBody:\n{ai_output.body}")
                print("\n" + "=" * 80)
                print("END OF AI-POWERED WEEKLY REPORT")
                print("=" * 80)
                
                # Send notifications
                send_report_email(ai_output.subject, ai_output.body, ai_output.metadata)
                send_rocketchat_webhook_message(f"**{ai_output.subject}**\n\n{ai_output.body[:500]}...")
                
                logger.info("Weekly report sent successfully")
                logger.info(f"Subject: {ai_output.subject}")
                logger.info(f"Body length: {len(ai_output.body)} characters")
            else:
                print("AI report generation failed, falling back to detailed report")
                text_report = generator.print_detailed_weekly_report(aggregated)
                
                # Send notifications with detailed report
                subject = f"🔴 NOC Weekly Report | {start_date} to {end_date} | {aggregated.total_alerts} Alerts"
                send_report_email(subject, text_report)
                send_rocketchat_webhook_message(f"**{subject}**\n\n{text_report[:500]}...")
        else:
            # Generate detailed text report
            text_report = generator.print_detailed_weekly_report(aggregated)
            
            # Send notifications with detailed report
            subject = f"🔴 NOC Weekly Report | {start_date} to {end_date} | {aggregated.total_alerts} Alerts"
            send_report_email(subject, text_report)
            send_rocketchat_webhook_message(f"**{subject}**\n\n{text_report[:500]}...")
    else:
        print(f"No data available for period {start_date} to {end_date}")

def generate_last_week_report(use_ai: bool = True) -> None:
    """Generate weekly report for the previous week."""
    # Get last week's Monday to Sunday
    now = arrow.now()
    last_week_start = now.shift(weeks=-1).replace(hour=0, minute=0, second=0, microsecond=0)
    last_week_end = last_week_start.shift(days=6).replace(hour=23, minute=59, second=59)
    
    start_date = last_week_start.format('YYYY-MM-DD')
    end_date = last_week_end.format('YYYY-MM-DD')
    
    print(f"Generating weekly report for {start_date} to {end_date}")
    generate_weekly_report_for_date_range(start_date, end_date, use_ai)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate weekly NOC reports')
    parser.add_argument('--start', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', help='End date (YYYY-MM-DD)')
    parser.add_argument('--last-week', action='store_true', help='Generate report for last week')
    parser.add_argument('--no-ai', action='store_true', help='Use detailed text report instead of AI-powered report')
    
    args = parser.parse_args()
    
    use_ai = not args.no_ai
    
    if args.last_week:
        generate_last_week_report(use_ai)
    elif args.start and args.end:
        generate_weekly_report_for_date_range(args.start, args.end, use_ai)
    else:
        print("Please specify --last-week or --start and --end dates")
        print("Use --no-ai to generate detailed text report instead of AI-powered report")
