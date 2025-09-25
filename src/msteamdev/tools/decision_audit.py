# Decision Audit Logger - Comprehensive tracking and analysis of tiered escalation decisions
# Provides detailed logging, metrics, and analysis capabilities for decision framework optimization

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from collections import defaultdict, Counter
from crewai.tools import tool

logger = logging.getLogger(__name__)

@dataclass
class DecisionMetrics:
    """Metrics for decision analysis"""
    total_decisions: int
    tier_breakdown: Dict[str, int]
    escalation_rate: float
    safety_override_rate: float
    avg_kb_confidence: Optional[float]
    top_decision_reasons: List[Dict[str, Any]]
    performance_stats: Dict[str, float]

class DecisionAuditLogger:
    """
    Comprehensive audit logging system for tiered escalation decisions.
    
    Features:
    - Real-time decision logging with full audit trails
    - Performance metrics and trend analysis
    - Decision pattern analysis for framework optimization
    - Exportable reports for stakeholder review
    - Automated alerts for decision anomalies
    """
    
    def __init__(self):
        self.log_file = "/home/crewai/msteamdev/log/decision_audit.log"
        self.summary_file = "/home/crewai/msteamdev/log/decision_summary.json"
        self.decision_history = []
        self.ensure_log_files()
    
    def ensure_log_files(self):
        """Ensure audit log files exist"""
        try:
            os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
            
            # Create files if they don't exist
            for file_path in [self.log_file, self.summary_file]:
                if not os.path.exists(file_path):
                    with open(file_path, 'w') as f:
                        if file_path.endswith('.json'):
                            json.dump({"audit_log_initialized": True, "decisions": []}, f)
                        else:
                            f.write(f"# Decision Audit Log - Initialized {datetime.now(timezone.utc).isoformat()}\n")
        except Exception as e:
            logger.warning(f"Could not initialize audit log files: {e}")
    
    def log_decision(self, incident_number: str, decision_result: Dict, 
                    alert_data: Dict, policy_result: Dict, ai_analysis: Optional[str] = None,
                    execution_time_seconds: float = 0.0):
        """
        Log a comprehensive decision audit entry
        
        Args:
            incident_number: The incident number
            decision_result: The tiered decision result
            alert_data: Original alert data
            policy_result: Policy check result  
            ai_analysis: AI analysis text (optional)
            execution_time_seconds: Decision processing time
        """
        try:
            audit_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "incident_number": incident_number,
                "decision": {
                    "escalate": decision_result.get("escalate", False),
                    "tier": decision_result.get("tier", "unknown"),
                    "confidence": decision_result.get("confidence", "unknown"),
                    "reason": decision_result.get("reason", ""),
                    "safety_override": decision_result.get("safety_override", False),
                    "kb_confidence": decision_result.get("kb_confidence")
                },
                "inputs": {
                    "alert": {
                        "title": alert_data.get("title", ""),
                        "severity": alert_data.get("severity", ""),
                        "timestamp": alert_data.get("timestamp", ""),
                        "metric": alert_data.get("metric", "")
                    },
                    "policy": {
                        "eligible": policy_result.get("eligible", False),
                        "reason_summary": policy_result.get("reason", "")[:200] + "..." if len(policy_result.get("reason", "")) > 200 else policy_result.get("reason", "")
                    },
                    "ai_analysis_provided": ai_analysis is not None,
                    "ai_analysis_length": len(ai_analysis) if ai_analysis else 0
                },
                "performance": {
                    "execution_time_seconds": execution_time_seconds,
                    "processing_date": datetime.now(timezone.utc).date().isoformat()
                },
                "audit_trail": decision_result.get("audit_trail", []),
                "details": decision_result.get("details", {}),
                "knowledge_freshness": decision_result.get("knowledge_freshness")
            }
            
            # Write to audit log file
            with open(self.log_file, 'a') as f:
                f.write(json.dumps(audit_entry) + "\n")
                
            # Update summary statistics
            self._update_summary_stats(audit_entry)
            
            logger.debug(f"Logged decision audit for incident {incident_number}")
            
        except Exception as e:
            logger.error(f"Failed to log decision audit for incident {incident_number}: {e}")
    
    def _update_summary_stats(self, audit_entry: Dict):
        """Update summary statistics with new audit entry"""
        try:
            # Load existing summary
            summary_data = {"decisions": []}
            if os.path.exists(self.summary_file):
                try:
                    with open(self.summary_file, 'r') as f:
                        summary_data = json.load(f)
                except:
                    pass
            
            # Add new decision to summary
            summary_data["decisions"].append({
                "timestamp": audit_entry["timestamp"],
                "incident_number": audit_entry["incident_number"],
                "escalate": audit_entry["decision"]["escalate"],
                "tier": audit_entry["decision"]["tier"],
                "safety_override": audit_entry["decision"]["safety_override"],
                "kb_confidence": audit_entry["decision"]["kb_confidence"],
                "execution_time": audit_entry["performance"]["execution_time_seconds"],
                "alert_severity": audit_entry["inputs"]["alert"]["severity"]
            })
            
            # Keep only last 1000 decisions in summary for performance
            if len(summary_data["decisions"]) > 1000:
                summary_data["decisions"] = summary_data["decisions"][-1000:]
            
            # Update summary metadata
            summary_data["last_updated"] = datetime.now(timezone.utc).isoformat()
            summary_data["total_decisions"] = len(summary_data["decisions"])
            
            # Write updated summary
            with open(self.summary_file, 'w') as f:
                json.dump(summary_data, f, indent=2)
                
        except Exception as e:
            logger.warning(f"Failed to update summary stats: {e}")
    
    def get_decision_metrics(self, days_back: int = 7) -> DecisionMetrics:
        """
        Get decision metrics for analysis and reporting
        
        Args:
            days_back: Number of days to analyze (default: 7)
            
        Returns:
            DecisionMetrics object with comprehensive statistics
        """
        try:
            # Load summary data
            if not os.path.exists(self.summary_file):
                return DecisionMetrics(
                    total_decisions=0,
                    tier_breakdown={},
                    escalation_rate=0.0,
                    safety_override_rate=0.0,
                    avg_kb_confidence=None,
                    top_decision_reasons=[],
                    performance_stats={}
                )
            
            with open(self.summary_file, 'r') as f:
                summary_data = json.load(f)
            
            decisions = summary_data.get("decisions", [])
            
            # Filter by date range
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
            recent_decisions = [
                d for d in decisions
                if datetime.fromisoformat(d["timestamp"]) >= cutoff_date
            ]
            
            if not recent_decisions:
                return DecisionMetrics(
                    total_decisions=0,
                    tier_breakdown={},
                    escalation_rate=0.0,
                    safety_override_rate=0.0,
                    avg_kb_confidence=None,
                    top_decision_reasons=[],
                    performance_stats={}
                )
            
            # Calculate metrics
            total_decisions = len(recent_decisions)
            escalated_count = sum(1 for d in recent_decisions if d.get("escalate", False))
            safety_overrides = sum(1 for d in recent_decisions if d.get("safety_override", False))
            
            # Tier breakdown
            tier_breakdown = Counter(d.get("tier", "unknown") for d in recent_decisions)
            
            # KB confidence stats
            kb_confidences = [d.get("kb_confidence") for d in recent_decisions if d.get("kb_confidence") is not None]
            avg_kb_confidence = sum(kb_confidences) / len(kb_confidences) if kb_confidences else None
            
            # Performance stats
            execution_times = [d.get("execution_time", 0) for d in recent_decisions]
            performance_stats = {
                "avg_execution_time": sum(execution_times) / len(execution_times) if execution_times else 0,
                "max_execution_time": max(execution_times) if execution_times else 0,
                "min_execution_time": min(execution_times) if execution_times else 0
            }
            
            # Top decision reasons (would need to be extracted from full audit log)
            top_reasons = self._get_top_decision_reasons(days_back)
            
            return DecisionMetrics(
                total_decisions=total_decisions,
                tier_breakdown=dict(tier_breakdown),
                escalation_rate=escalated_count / total_decisions * 100 if total_decisions > 0 else 0,
                safety_override_rate=safety_overrides / total_decisions * 100 if total_decisions > 0 else 0,
                avg_kb_confidence=avg_kb_confidence,
                top_decision_reasons=top_reasons,
                performance_stats=performance_stats
            )
            
        except Exception as e:
            logger.error(f"Error calculating decision metrics: {e}")
            return DecisionMetrics(
                total_decisions=0,
                tier_breakdown={},
                escalation_rate=0.0,
                safety_override_rate=0.0,
                avg_kb_confidence=None,
                top_decision_reasons=[],
                performance_stats={"error": str(e)}
            )
    
    def _get_top_decision_reasons(self, days_back: int) -> List[Dict[str, Any]]:
        """Get top decision reasons from full audit log"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
            reason_counts = Counter()
            tier_reason_map = defaultdict(list)
            
            # Read audit log to get decision reasons
            if not os.path.exists(self.log_file):
                return []
                
            with open(self.log_file, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        entry_time = datetime.fromisoformat(entry["timestamp"])
                        
                        if entry_time >= cutoff_date:
                            reason = entry["decision"].get("reason", "")[:100]  # Truncate long reasons
                            tier = entry["decision"].get("tier", "unknown")
                            
                            if reason:
                                reason_counts[reason] += 1
                                tier_reason_map[reason].append(tier)
                    except (json.JSONDecodeError, KeyError):
                        continue
            
            # Format top reasons
            top_reasons = []
            for reason, count in reason_counts.most_common(10):
                most_common_tier = Counter(tier_reason_map[reason]).most_common(1)[0][0]
                top_reasons.append({
                    "reason": reason,
                    "count": count,
                    "most_common_tier": most_common_tier,
                    "percentage": count / sum(reason_counts.values()) * 100 if reason_counts else 0
                })
            
            return top_reasons
            
        except Exception as e:
            logger.warning(f"Error getting top decision reasons: {e}")
            return []
    
    def generate_audit_report(self, days_back: int = 7, include_details: bool = True) -> Dict[str, Any]:
        """
        Generate comprehensive audit report
        
        Args:
            days_back: Number of days to include in report
            include_details: Include detailed decision breakdown
            
        Returns:
            Comprehensive audit report as dictionary
        """
        try:
            metrics = self.get_decision_metrics(days_back)
            
            report = {
                "report_metadata": {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "period_days": days_back,
                    "report_type": "tiered_decision_audit",
                    "framework_version": "3-tier_safety_first"
                },
                "summary": {
                    "total_decisions": metrics.total_decisions,
                    "escalation_rate": f"{metrics.escalation_rate:.1f}%",
                    "safety_override_rate": f"{metrics.safety_override_rate:.1f}%",
                    "avg_kb_confidence": f"{metrics.avg_kb_confidence:.2f}" if metrics.avg_kb_confidence else "N/A"
                },
                "tier_performance": {
                    "breakdown": metrics.tier_breakdown,
                    "tier_distribution": {
                        tier: f"{count / metrics.total_decisions * 100:.1f}%" 
                        for tier, count in metrics.tier_breakdown.items()
                    } if metrics.total_decisions > 0 else {}
                },
                "performance_metrics": metrics.performance_stats,
                "decision_patterns": {
                    "top_reasons": metrics.top_decision_reasons[:5],
                    "framework_effectiveness": self._assess_framework_effectiveness(metrics)
                }
            }
            
            if include_details:
                report["detailed_analysis"] = self._generate_detailed_analysis(metrics, days_back)
            
            return report
            
        except Exception as e:
            logger.error(f"Error generating audit report: {e}")
            return {
                "error": str(e),
                "report_metadata": {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "status": "error"
                }
            }
    
    def _assess_framework_effectiveness(self, metrics: DecisionMetrics) -> Dict[str, Any]:
        """Assess the effectiveness of the tiered framework"""
        assessment = {
            "overall_score": "good",  # good, fair, needs_improvement
            "observations": [],
            "recommendations": []
        }
        
        # Safety override rate assessment
        if metrics.safety_override_rate > 20:
            assessment["observations"].append(f"High safety override rate ({metrics.safety_override_rate:.1f}%) - many critical alerts detected")
        elif metrics.safety_override_rate < 5:
            assessment["observations"].append(f"Low safety override rate ({metrics.safety_override_rate:.1f}%) - good alert quality")
        
        # Tier distribution assessment
        tier_breakdown = metrics.tier_breakdown
        if tier_breakdown.get("safety_net", 0) > metrics.total_decisions * 0.3:
            assessment["observations"].append("High Tier 1 usage - may indicate alert quality issues")
            assessment["recommendations"].append("Review alert sources and thresholds")
        
        if tier_breakdown.get("kb_enhanced", 0) > metrics.total_decisions * 0.4:
            assessment["observations"].append("Good KB utilization - framework learning effectively")
        
        # KB confidence assessment
        if metrics.avg_kb_confidence and metrics.avg_kb_confidence > 0.7:
            assessment["observations"].append(f"High KB confidence ({metrics.avg_kb_confidence:.2f}) - reliable knowledge base")
        elif metrics.avg_kb_confidence and metrics.avg_kb_confidence < 0.5:
            assessment["observations"].append(f"Low KB confidence ({metrics.avg_kb_confidence:.2f}) - knowledge base needs improvement")
            assessment["recommendations"].append("Update knowledge base with recent incident data")
        
        # Performance assessment  
        avg_time = metrics.performance_stats.get("avg_execution_time", 0)
        if avg_time > 10:
            assessment["observations"].append(f"Slow decision processing ({avg_time:.1f}s average)")
            assessment["recommendations"].append("Optimize knowledge base queries and tool performance")
        
        return assessment
    
    def _generate_detailed_analysis(self, metrics: DecisionMetrics, days_back: int) -> Dict[str, Any]:
        """Generate detailed analysis section for report"""
        return {
            "tier_analysis": {
                "tier_1_safety": {
                    "usage_count": metrics.tier_breakdown.get("safety_net", 0),
                    "description": "Non-negotiable safety rules (critical severity, critical keywords)",
                    "effectiveness": "Preventing missed critical alerts"
                },
                "tier_2_knowledge": {
                    "usage_count": metrics.tier_breakdown.get("kb_enhanced", 0),
                    "description": "High-confidence KB analysis (≥0.8 confidence, ≤90 days, ≥2 incidents)",
                    "avg_confidence": f"{metrics.avg_kb_confidence:.2f}" if metrics.avg_kb_confidence else "N/A"
                },
                "tier_3_policy": {
                    "usage_count": metrics.tier_breakdown.get("policy_fallback", 0),
                    "description": "Traditional policy rules with safety-first defaults",
                    "effectiveness": "Reliable fallback mechanism"
                }
            },
            "recommendations_for_improvement": self._generate_improvement_recommendations(metrics)
        }
    
    def _generate_improvement_recommendations(self, metrics: DecisionMetrics) -> List[str]:
        """Generate recommendations for framework improvement"""
        recommendations = []
        
        if metrics.total_decisions < 10:
            recommendations.append("Insufficient decision data - monitor for at least 50 decisions for meaningful analysis")
        
        if metrics.safety_override_rate > 30:
            recommendations.append("Very high safety override rate - review alert sources and implement better filtering")
        
        kb_tier_usage = metrics.tier_breakdown.get("kb_enhanced", 0)
        total = metrics.total_decisions
        
        if total > 0 and kb_tier_usage / total < 0.2:
            recommendations.append("Low KB tier usage - consider updating knowledge base data or relaxing confidence requirements")
        
        if metrics.avg_kb_confidence and metrics.avg_kb_confidence < 0.6:
            recommendations.append("Low average KB confidence - refresh knowledge base with recent incident data")
        
        performance_time = metrics.performance_stats.get("avg_execution_time", 0)
        if performance_time > 5:
            recommendations.append("Decision processing is slow - optimize KB queries and tool performance")
        
        return recommendations

# Global audit logger instance
audit_logger = DecisionAuditLogger()

@tool("LogDecisionAudit")
def log_decision_audit(incident_number: str, decision_result: str, alert_data: str, 
                      policy_result: str, ai_analysis: Optional[str] = None,
                      execution_time_seconds: float = 0.0) -> str:
    """
    Log a comprehensive decision audit entry for analysis and reporting.
    
    This tool captures detailed information about each tiered escalation decision
    to support framework optimization and stakeholder reporting.
    
    Args:
        incident_number: The incident number
        decision_result: JSON string with tiered decision result
        alert_data: JSON string with alert data
        policy_result: JSON string with policy result
        ai_analysis: Optional AI analysis text
        execution_time_seconds: Decision processing time
        
    Returns:
        JSON string with audit logging status
    """
    try:
        # Parse inputs
        decision_data = json.loads(decision_result) if isinstance(decision_result, str) else decision_result
        alert_dict = json.loads(alert_data) if isinstance(alert_data, str) else alert_data
        policy_dict = json.loads(policy_result) if isinstance(policy_result, str) else policy_result
        
        # Log the decision
        audit_logger.log_decision(
            incident_number=incident_number,
            decision_result=decision_data,
            alert_data=alert_dict,
            policy_result=policy_dict,
            ai_analysis=ai_analysis,
            execution_time_seconds=execution_time_seconds
        )
        
        return json.dumps({
            "status": "success",
            "message": f"Decision audit logged for incident {incident_number}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error logging decision audit: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Failed to log audit: {str(e)}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

@tool("GetDecisionMetrics")
def get_decision_metrics(days_back: int = 7) -> str:
    """
    Get decision metrics and analysis for the tiered framework.
    
    Args:
        days_back: Number of days to analyze (default: 7)
        
    Returns:
        JSON string with comprehensive decision metrics
    """
    try:
        metrics = audit_logger.get_decision_metrics(days_back)
        return json.dumps(asdict(metrics), indent=2, default=str)
        
    except Exception as e:
        logger.error(f"Error getting decision metrics: {e}")
        return json.dumps({
            "error": str(e),
            "status": "error"
        })

@tool("GenerateAuditReport")
def generate_audit_report(days_back: int = 7, include_details: bool = True) -> str:
    """
    Generate comprehensive audit report for tiered escalation decisions.
    
    Args:
        days_back: Number of days to include in report (default: 7)
        include_details: Include detailed analysis (default: True)
        
    Returns:
        JSON string with comprehensive audit report
    """
    try:
        report = audit_logger.generate_audit_report(days_back, include_details)
        return json.dumps(report, indent=2, default=str)
        
    except Exception as e:
        logger.error(f"Error generating audit report: {e}")
        return json.dumps({
            "error": str(e),
            "status": "error",
            "report_metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "status": "error"
            }
        })

if __name__ == "__main__":
    # Test the audit logger
    test_alert = {
        "incident_number": "TEST123",
        "title": "Test Alert",
        "severity": "warning",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    test_decision = {
        "escalate": True,
        "tier": "safety_net",
        "confidence": "high",
        "reason": "Test decision",
        "safety_override": True
    }
    
    test_policy = {"eligible": True, "reason": "Test policy"}
    
    audit_logger.log_decision("TEST123", test_decision, test_alert, test_policy, "Test AI analysis", 1.5)
    
    metrics = audit_logger.get_decision_metrics(1)
    print(json.dumps(asdict(metrics), indent=2, default=str))
    
    report = audit_logger.generate_audit_report(1, True)
    print(json.dumps(report, indent=2, default=str))