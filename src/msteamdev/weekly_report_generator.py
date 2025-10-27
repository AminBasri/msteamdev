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

# Import logging setup
from src.msteamdev.logging_setup import get_module_logger
from src.msteamdev.daily_metrics_storage import DailyMetricsStorage, DailyMetrics, daily_storage
from src.msteamdev.crew import load_agents, load_yaml
from src.msteamdev.models import ShiftReportOutput, ReportMetadata
from crewai import Task, Crew

logger = get_module_logger(__name__, log_filename='weekly_report.log')

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
    avg_mttfr_minutes: float
    
    # Average rates
    avg_resolution_rate: float
    avg_acknowledgment_rate: float
    avg_escalation_rate: float
    
    # SLA metrics
    avg_sla_compliance: float
    total_sla_breaches: int
    avg_s2_sla_compliance: float
    avg_s3_sla_compliance: float
    
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
        valid_mttfr = [m.mttfr_minutes for m in daily_metrics if m.mttfr_minutes > 0]
        
        avg_mtta = sum(valid_mtta) / len(valid_mtta) if valid_mtta else 0.0
        avg_mttr = sum(valid_mttr) / len(valid_mttr) if valid_mttr else 0.0
        avg_mttfr = sum(valid_mttfr) / len(valid_mttfr) if valid_mttfr else 0.0
        
        # Calculate average rates
        avg_resolution_rate = sum(m.resolution_rate for m in daily_metrics) / total_shifts
        avg_acknowledgment_rate = sum(m.acknowledgment_rate for m in daily_metrics) / total_shifts
        avg_escalation_rate = sum(m.escalation_rate for m in daily_metrics) / total_shifts
        
        # Calculate average SLA metrics
        avg_sla_compliance = sum(m.sla_compliance for m in daily_metrics) / total_shifts
        total_sla_breaches = sum(m.sla_breaches for m in daily_metrics)
        
        valid_s2_sla = [m.s2_sla_compliance for m in daily_metrics if m.s2_sla_compliance > 0]
        valid_s3_sla = [m.s3_sla_compliance for m in daily_metrics if m.s3_sla_compliance > 0]
        
        avg_s2_sla_compliance = sum(valid_s2_sla) / len(valid_s2_sla) if valid_s2_sla else 0.0
        avg_s3_sla_compliance = sum(valid_s3_sla) / len(valid_s3_sla) if valid_s3_sla else 0.0
        
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
            avg_mttfr_minutes=avg_mttfr,
            
            avg_resolution_rate=avg_resolution_rate,
            avg_acknowledgment_rate=avg_acknowledgment_rate,
            avg_escalation_rate=avg_escalation_rate,
            
            avg_sla_compliance=avg_sla_compliance,
            total_sla_breaches=total_sla_breaches,
            avg_s2_sla_compliance=avg_s2_sla_compliance,
            avg_s3_sla_compliance=avg_s3_sla_compliance,
            
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
            
            # SLA compliance trend
            sla_compliance = [m.sla_compliance for m in sorted_metrics]
            trends['sla_compliance'] = {
                'daily_compliance': sla_compliance,
                'trend': 'improving' if len(sla_compliance) > 1 and sla_compliance[-1] > sla_compliance[0] else 'declining',
                'best_day': sorted_metrics[sla_compliance.index(max(sla_compliance))].date if sla_compliance else None,
                'worst_day': sorted_metrics[sla_compliance.index(min(sla_compliance))].date if sla_compliance else None
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
    
    def print_detailed_weekly_report(self, aggregated: WeeklyAggregatedMetrics) -> None:
        """Print detailed weekly report similar to test_timing_fix.py format."""
        
        print("=" * 80)
        print(f"WEEKLY NOC REPORT | {aggregated.week_start} to {aggregated.week_end}")
        print("=" * 80)
        
        print(f"\n1. WEEKLY SUMMARY:")
        print("-" * 50)
        print(f"   Period: {aggregated.week_start} to {aggregated.week_end}")
        print(f"   Total Shifts: {aggregated.total_shifts}")
        print(f"   Total Alerts: {aggregated.total_alerts}")
        print(f"   Total Incidents: {aggregated.total_incidents}")
        
        print(f"\n2. ALERT BREAKDOWN:")
        print("-" * 50)
        print(f"   Resolved Alerts: {aggregated.total_resolved}")
        print(f"   Acknowledged Alerts: {aggregated.total_acknowledged}")
        print(f"   Critical Alerts: {aggregated.total_critical}")
        print(f"   Warning Alerts: {aggregated.total_warning}")
        print(f"   Escalated Alerts: {aggregated.total_escalated}")
        
        print(f"\n3. AVERAGE TIMING METRICS:")
        print("-" * 50)
        print(f"   Average MTTA: {aggregated.avg_mtta_minutes:.1f}m")
        print(f"   Average MTTR: {aggregated.avg_mttr_minutes:.1f}m")
        print(f"   Average MTTFR: {aggregated.avg_mttfr_minutes:.1f}m")
        
        print(f"\n4. AVERAGE RATES:")
        print("-" * 50)
        print(f"   Average Resolution Rate: {aggregated.avg_resolution_rate:.1f}%")
        print(f"   Average Acknowledgment Rate: {aggregated.avg_acknowledgment_rate:.1f}%")
        print(f"   Average Escalation Rate: {aggregated.avg_escalation_rate:.1f}%")
        
        print(f"\n5. WEEKLY SLA ANALYSIS:")
        print("-" * 50)
        print(f"   Average SLA Compliance: {aggregated.avg_sla_compliance:.1f}% (MTTA/MTTFR - 5min threshold)")
        print(f"   Total SLA Breaches: {aggregated.total_sla_breaches}")
        print(f"   Average S2 SLA Compliance: {aggregated.avg_s2_sla_compliance:.1f}% (Critical - 8h resolution)")
        print(f"   Average S3 SLA Compliance: {aggregated.avg_s3_sla_compliance:.1f}% (Warning - 24h resolution)")
        
        print(f"\n6. DAILY BREAKDOWN:")
        print("-" * 50)
        for metrics in aggregated.daily_metrics:
            print(f"   {metrics.date} ({metrics.shift_type}):")
            print(f"     Alerts: {metrics.total_alerts}, Resolved: {metrics.resolved_alerts}")
            print(f"     SLA: {metrics.sla_compliance:.1f}%, Breaches: {metrics.sla_breaches}")
            print(f"     MTTA: {metrics.mtta_minutes:.1f}m, MTTR: {metrics.mttr_minutes:.1f}m")
        
        print(f"\n7. TREND ANALYSIS:")
        print("-" * 50)
        if aggregated.trends:
            trends = aggregated.trends
            
            # Alert volume trend
            if 'alert_volume' in trends:
                alert_trend = trends['alert_volume']
                print(f"   Alert Volume Trend: {alert_trend['trend']}")
                if alert_trend['peak_day']:
                    print(f"   Peak Alert Day: {alert_trend['peak_day']}")
                if alert_trend['lowest_day']:
                    print(f"   Lowest Alert Day: {alert_trend['lowest_day']}")
            
            # SLA compliance trend
            if 'sla_compliance' in trends:
                sla_trend = trends['sla_compliance']
                print(f"   SLA Compliance Trend: {sla_trend['trend']}")
                if sla_trend['best_day']:
                    print(f"   Best SLA Day: {sla_trend['best_day']}")
                if sla_trend['worst_day']:
                    print(f"   Worst SLA Day: {sla_trend['worst_day']}")
            
            # Critical alerts analysis
            if 'critical_alerts' in trends:
                critical_trend = trends['critical_alerts']
                print(f"   Total Critical Alerts: {critical_trend['total_critical']}")
                print(f"   Days with Critical Alerts: {critical_trend['days_with_critical']}/{aggregated.total_shifts}")
        
        print(f"\n8. WEEKLY PERFORMANCE ASSESSMENT:")
        print("-" * 50)
        
        # Performance assessment
        if aggregated.avg_sla_compliance >= 90 and aggregated.avg_resolution_rate >= 80:
            performance = "EXCELLENT"
            emoji = "🟢"
        elif aggregated.avg_sla_compliance >= 80 and aggregated.avg_resolution_rate >= 70:
            performance = "GOOD"
            emoji = "🟡"
        else:
            performance = "NEEDS IMPROVEMENT"
            emoji = "🔴"
        
        print(f"   Overall Performance: {emoji} {performance}")
        print(f"   Key Metrics:")
        print(f"     - SLA Compliance: {aggregated.avg_sla_compliance:.1f}% (Target: ≥90%)")
        print(f"     - Resolution Rate: {aggregated.avg_resolution_rate:.1f}% (Target: ≥80%)")
        print(f"     - Escalation Rate: {aggregated.avg_escalation_rate:.1f}% (Lower is better)")
        
        print(f"\n9. RECOMMENDATIONS:")
        print("-" * 50)
        
        recommendations = []
        
        if aggregated.avg_sla_compliance < 90:
            recommendations.append("Focus on improving first response times to meet 5-minute SLA threshold")
        
        if aggregated.avg_resolution_rate < 80:
            recommendations.append("Increase resolution rate through better incident management processes")
        
        if aggregated.avg_escalation_rate > 30:
            recommendations.append("Review escalation policies to reduce unnecessary escalations")
        
        if aggregated.total_critical > 0:
            recommendations.append("Investigate root causes of critical alerts to prevent recurrence")
        
        if not recommendations:
            recommendations.append("Continue current operational excellence")
        
        for i, rec in enumerate(recommendations, 1):
            print(f"   {i}. {rec}")
        
        print("\n" + "=" * 80)
        print("END OF WEEKLY REPORT")
        print("=" * 80)
    
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
                    avg_mttfr_minutes=aggregated.avg_mttfr_minutes,
                    avg_resolution_rate=aggregated.avg_resolution_rate,
                    avg_acknowledgment_rate=aggregated.avg_acknowledgment_rate,
                    avg_escalation_rate=aggregated.avg_escalation_rate,
                    avg_sla_compliance=aggregated.avg_sla_compliance,
                    total_sla_breaches=aggregated.total_sla_breaches,
                    avg_s2_sla_compliance=aggregated.avg_s2_sla_compliance,
                    avg_s3_sla_compliance=aggregated.avg_s3_sla_compliance,
                    daily_breakdown_data=daily_breakdown_data,
                    trend_analysis_data=trend_analysis_data,
                    performance_status=performance_status,
                    performance_grade=performance_grade,
                    performance_emoji=performance_emoji,
                    alert_volume_trend=aggregated.trends.get('alert_volume', {}).get('trend', 'stable'),
                    sla_compliance_trend=aggregated.trends.get('sla_compliance', {}).get('trend', 'stable'),
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
                f"SLA: {metrics.sla_compliance:.1f}%, "
                f"Breaches: {metrics.sla_breaches}, "
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
        
        if 'sla_compliance' in trends:
            sla_trend = trends['sla_compliance']
            trend_lines.append(f"SLA Compliance: {sla_trend.get('trend', 'stable')}")
            if sla_trend.get('best_day'):
                trend_lines.append(f"Best SLA Day: {sla_trend['best_day']}")
            if sla_trend.get('worst_day'):
                trend_lines.append(f"Worst SLA Day: {sla_trend['worst_day']}")
        
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
        if aggregated.avg_sla_compliance >= 90 and aggregated.avg_resolution_rate >= 80:
            performance_status = "EXCELLENT"
            performance_grade = "A"
            performance_emoji = "🟢"
        elif aggregated.avg_sla_compliance >= 80 and aggregated.avg_resolution_rate >= 70:
            performance_status = "GOOD"
            performance_grade = "B"
            performance_emoji = "🟡"
        elif aggregated.avg_sla_compliance >= 70 and aggregated.avg_resolution_rate >= 60:
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
                        sla_breaches=0,
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
                sla_breaches=0,
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
                print("=" * 80)
                print("AI-POWERED WEEKLY REPORT")
                print("=" * 80)
                print(f"Subject: {ai_output.subject}")
                print(f"\nBody:\n{ai_output.body}")
                print("\n" + "=" * 80)
                print("END OF AI-POWERED WEEKLY REPORT")
                print("=" * 80)
            else:
                print("AI report generation failed, falling back to detailed report")
                generator.print_detailed_weekly_report(aggregated)
        else:
            # Generate detailed text report
            generator.print_detailed_weekly_report(aggregated)
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
