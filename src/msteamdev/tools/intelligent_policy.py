# Intelligent Policy Engine - Context-Aware Escalation Rules
# Replaces rigid day-based rules with intelligent, business-aware escalation logic

import json
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from dataclasses import dataclass
from crewai.tools import tool

logger = logging.getLogger(__name__)

class BusinessImpact(Enum):
    """Business impact levels"""
    CRITICAL = "critical"      # Revenue/customer-affecting
    HIGH = "high"             # Service degradation  
    MEDIUM = "medium"         # Performance impact
    LOW = "low"              # Informational

class ServiceTier(Enum):
    """Service tier classifications"""
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"

class AlertUrgency(Enum):
    """Alert urgency levels"""
    IMMEDIATE = "immediate"    # 0-1 hours
    URGENT = "urgent"         # 1-4 hours
    NORMAL = "normal"         # 4-24 hours  
    LOW = "low"              # 24+ hours

@dataclass
class EscalationContext:
    """Rich context for escalation decisions"""
    # Alert properties
    severity_from_title: str          # Extracted from title (CRITICAL/WARNING)
    severity_declared: str            # Declared severity field
    metric_type: str                  # CPU, Memory, Disk, Network, etc.
    service_tier: ServiceTier         # Production, Staging, etc.
    business_impact: BusinessImpact   # Actual business impact assessment
    
    # Timing context
    is_business_hours: bool
    is_weekend: bool
    hour_of_day: int
    
    # Pattern context
    alert_frequency: int              # How often this alert fires
    trend_direction: str             # increasing, stable, decreasing
    related_incidents: int           # Count of related ongoing incidents
    
    # Business context
    maintenance_window: bool
    customer_impact_reported: bool
    sla_breach_risk: bool

class IntelligentPolicyEngine:
    """
    Intelligent, context-aware escalation policy engine that replaces rigid day-based rules.
    
    Features:
    - Business impact assessment
    - Service tier awareness  
    - Time-sensitive escalation
    - Pattern-based intelligence
    - SLA and maintenance window considerations
    - Dynamic thresholds based on context
    """
    
    # Critical keywords that indicate high business impact
    CRITICAL_BUSINESS_KEYWORDS = [
        # Service availability
        'down', 'outage', 'unavailable', 'offline', 'failed', 'failure',
        'crashed', 'unreachable', 'timeout', 'connection refused',
        
        # Performance degradation
        'slow', 'degraded', 'latency', 'response time', 'bottleneck',
        
        # Data integrity
        'data loss', 'corruption', 'backup failed', 'sync failed',
        
        # Security
        'security', 'breach', 'unauthorized', 'intrusion', 'malware',
        
        # Business functions
        'payment', 'checkout', 'login', 'authentication', 'database',
        'api', 'service', 'application'
    ]
    
    # High-impact metrics that need faster escalation
    HIGH_IMPACT_METRICS = ['database', 'api', 'payment', 'login', 'checkout']
    
    # Production environment indicators
    PRODUCTION_INDICATORS = ['prod', 'production', 'live', 'prd']
    
    def __init__(self):
        self.escalation_history = []
        
    def assess_escalation_eligibility(self, alert: Dict[str, Any]) -> Tuple[bool, str, EscalationContext]:
        """
        Assess escalation eligibility using intelligent, context-aware rules
        
        Args:
            alert: Alert data dictionary
            
        Returns:
            Tuple of (should_escalate, detailed_reason, context)
        """
        try:
            # Build rich escalation context
            context = self._build_escalation_context(alert)
            
            # Apply intelligent escalation logic
            should_escalate, reason = self._evaluate_intelligent_rules(alert, context)
            
            logger.info(f"Intelligent policy decision for {alert.get('incident_number')}: {should_escalate}")
            logger.debug(f"Context: impact={context.business_impact.value}, tier={context.service_tier.value}, "
                        f"urgency={self._calculate_urgency(context).value}")
            
            return should_escalate, reason, context
            
        except Exception as e:
            logger.error(f"Error in intelligent policy assessment: {e}")
            # Fallback to safe escalation
            return True, f"FALLBACK ESCALATION: Policy error - {str(e)}", self._create_fallback_context()
    
    def _build_escalation_context(self, alert: Dict[str, Any]) -> EscalationContext:
        """Build comprehensive context for escalation decision"""
        
        title = alert.get('title', '').lower()
        severity = alert.get('severity', 'unknown').lower()
        timestamp_str = alert.get('timestamp', '')
        
        # Extract severity from title (common pattern: "[CRITICAL]" or "[WARNING]")
        severity_from_title = self._extract_severity_from_title(alert.get('title', ''))
        
        # Determine metric type
        metric_type = self._extract_metric_type(title)
        
        # Assess service tier
        service_tier = self._assess_service_tier(title)
        
        # Calculate business impact
        business_impact = self._assess_business_impact(alert, severity_from_title, metric_type, service_tier)
        
        # Time context
        dt = self._parse_timestamp(timestamp_str)
        is_business_hours = self._is_business_hours(dt)
        is_weekend = dt.weekday() >= 5 if dt else False
        hour_of_day = dt.hour if dt else 12
        
        # Pattern context (simplified for now - could be enhanced with ML)
        alert_frequency = self._estimate_alert_frequency(alert)
        trend_direction = self._analyze_trend_direction(alert)
        related_incidents = self._count_related_incidents(alert)
        
        # Business context
        maintenance_window = self._is_maintenance_window(dt, title)
        customer_impact_reported = self._has_customer_impact_reported(alert)
        sla_breach_risk = self._assess_sla_breach_risk(business_impact, dt)
        
        return EscalationContext(
            severity_from_title=severity_from_title,
            severity_declared=severity,
            metric_type=metric_type,
            service_tier=service_tier,
            business_impact=business_impact,
            is_business_hours=is_business_hours,
            is_weekend=is_weekend,
            hour_of_day=hour_of_day,
            alert_frequency=alert_frequency,
            trend_direction=trend_direction,
            related_incidents=related_incidents,
            maintenance_window=maintenance_window,
            customer_impact_reported=customer_impact_reported,
            sla_breach_risk=sla_breach_risk
        )
    
    def _evaluate_intelligent_rules(self, alert: Dict, context: EscalationContext) -> Tuple[bool, str]:
        """Apply intelligent escalation rules based on context"""
        
        reasons = []
        escalate = False
        urgency = self._calculate_urgency(context)
        
        # Rule 1: Critical business impact - immediate escalation
        if context.business_impact == BusinessImpact.CRITICAL:
            escalate = True
            reasons.append(f"🔴 CRITICAL BUSINESS IMPACT: {context.business_impact.value} impact detected")
        
        # Rule 2: Production + High severity - fast escalation
        if context.service_tier == ServiceTier.PRODUCTION and context.severity_from_title in ['critical', 'high']:
            escalate = True
            reasons.append(f"🔴 PRODUCTION CRITICAL: {context.severity_from_title} severity in production")
        
        # Rule 3: SLA breach risk - immediate escalation
        if context.sla_breach_risk:
            escalate = True
            reasons.append("🔴 SLA BREACH RISK: Alert may cause SLA violation")
        
        # Rule 4: Customer impact reported - escalate quickly
        if context.customer_impact_reported:
            escalate = True
            reasons.append("🔴 CUSTOMER IMPACT: Customer impact has been reported")
        
        # Rule 5: High-impact metrics need faster attention
        if context.metric_type in self.HIGH_IMPACT_METRICS:
            if urgency in [AlertUrgency.IMMEDIATE, AlertUrgency.URGENT]:
                escalate = True
                reasons.append(f"🟠 HIGH-IMPACT METRIC: {context.metric_type} requires urgent attention")
        
        # Rule 6: Multiple related incidents suggest escalating issue  
        if context.related_incidents >= 3:
            escalate = True
            reasons.append(f"🟠 INCIDENT PATTERN: {context.related_incidents} related incidents suggest escalating issue")
        
        # Rule 7: After-hours critical issues need immediate attention
        if not context.is_business_hours and context.business_impact in [BusinessImpact.CRITICAL, BusinessImpact.HIGH]:
            escalate = True
            reasons.append(f"🟠 AFTER-HOURS CRITICAL: {context.business_impact.value} impact outside business hours")
        
        # Rule 8: Maintenance window suppression (unless critical)
        if context.maintenance_window and context.business_impact not in [BusinessImpact.CRITICAL]:
            escalate = False
            reasons = [f"🟢 MAINTENANCE SUPPRESSION: Alert during maintenance window ({context.business_impact.value} impact)"]
        
        # Rule 9: Trend-based escalation
        if context.trend_direction == "increasing" and context.business_impact >= BusinessImpact.MEDIUM:
            escalate = True
            reasons.append("🟠 ESCALATING TREND: Alert frequency is increasing")
        
        # Rule 10: Intelligent recent escalation check (context-aware)
        recent_escalation_check = self._check_intelligent_recent_escalations(alert, context)
        if recent_escalation_check:
            escalate = False
            reasons = [recent_escalation_check]
        
        # Rule 11: Default business hours vs after-hours logic
        if not escalate:
            if context.is_business_hours:
                # During business hours, be more conservative
                if urgency <= AlertUrgency.NORMAL:
                    escalate = False
                    reasons.append(f"🟢 BUSINESS HOURS SUPPRESSION: {urgency.value} urgency during business hours")
                else:
                    escalate = True
                    reasons.append(f"🟠 BUSINESS HOURS ESCALATION: {urgency.value} urgency requires attention")
            else:
                # After hours, only escalate urgent/critical
                if urgency in [AlertUrgency.IMMEDIATE, AlertUrgency.URGENT]:
                    escalate = True
                    reasons.append(f"🟠 AFTER-HOURS ESCALATION: {urgency.value} urgency needs immediate attention")
                else:
                    escalate = False
                    reasons.append(f"🟢 AFTER-HOURS SUPPRESSION: {urgency.value} urgency can wait until business hours")
        
        # Format comprehensive reason
        reason_text = self._format_escalation_reason(alert, context, escalate, reasons, urgency)
        
        return escalate, reason_text
    
    def _extract_severity_from_title(self, title: str) -> str:
        """Extract severity from alert title (handles [CRITICAL], [WARNING] patterns)"""
        if not title:
            return "unknown"
            
        title_upper = title.upper()
        
        # Look for severity keywords in brackets or standalone
        if re.search(r'\[?CRITICAL\]?|\[?CRIT\]?', title_upper):
            return "critical"
        elif re.search(r'\[?WARNING\]?|\[?WARN\]?', title_upper):
            return "warning"
        elif re.search(r'\[?HIGH\]?', title_upper):
            return "high"
        elif re.search(r'\[?MEDIUM\]?|\[?MED\]?', title_upper):
            return "medium"
        elif re.search(r'\[?LOW\]?', title_upper):
            return "low"
        elif re.search(r'\[?INFO\]?|\[?INFORMATION\]?', title_upper):
            return "info"
        else:
            return "unknown"
    
    def _extract_metric_type(self, title: str) -> str:
        """Extract metric type from alert title"""
        title_lower = title.lower()
        
        patterns = [
            (r'\b(database|db|mysql|postgres|mongodb|redis)\b', 'database'),
            (r'\b(payment|checkout|billing|transaction)\b', 'payment'),
            (r'\b(login|auth|authentication|sso)\b', 'login'),
            (r'\b(api|endpoint|service|microservice)\b', 'api'),
            (r'\b(cpu|processor)\b', 'cpu'),
            (r'\b(memory|mem|ram)\b', 'memory'),
            (r'\b(disk|storage|drive)\b', 'disk'),
            (r'\b(network|bandwidth|traffic)\b', 'network'),
            (r'\b(latency|response|delay)\b', 'latency'),
            (r'\b(load|loading)\b', 'load'),
        ]
        
        for pattern, metric_type in patterns:
            if re.search(pattern, title_lower):
                return metric_type
                
        return "system"
    
    def _assess_service_tier(self, title: str) -> ServiceTier:
        """Assess service tier from alert title"""
        title_lower = title.lower()
        
        if any(prod_indicator in title_lower for prod_indicator in self.PRODUCTION_INDICATORS):
            return ServiceTier.PRODUCTION
        elif any(stage_indicator in title_lower for stage_indicator in ['staging', 'stage', 'stg']):
            return ServiceTier.STAGING
        elif any(dev_indicator in title_lower for dev_indicator in ['dev', 'development', 'test']):
            return ServiceTier.DEVELOPMENT
        else:
            # Default to production for safety if unclear
            return ServiceTier.PRODUCTION
    
    def _assess_business_impact(self, alert: Dict, severity_from_title: str, 
                              metric_type: str, service_tier: ServiceTier) -> BusinessImpact:
        """Assess actual business impact based on multiple factors"""
        
        title = alert.get('title', '').lower()
        
        # Critical business keywords override everything
        if any(keyword in title for keyword in self.CRITICAL_BUSINESS_KEYWORDS):
            return BusinessImpact.CRITICAL
        
        # High-impact metrics in production
        if metric_type in self.HIGH_IMPACT_METRICS and service_tier == ServiceTier.PRODUCTION:
            if severity_from_title in ['critical', 'high']:
                return BusinessImpact.CRITICAL
            else:
                return BusinessImpact.HIGH
        
        # Severity-based impact (but consider service tier)
        if severity_from_title == 'critical':
            return BusinessImpact.CRITICAL if service_tier == ServiceTier.PRODUCTION else BusinessImpact.HIGH
        elif severity_from_title in ['high', 'warning']:
            return BusinessImpact.HIGH if service_tier == ServiceTier.PRODUCTION else BusinessImpact.MEDIUM
        elif severity_from_title == 'medium':
            return BusinessImpact.MEDIUM
        else:
            return BusinessImpact.LOW
    
    def _calculate_urgency(self, context: EscalationContext) -> AlertUrgency:
        """Calculate alert urgency based on context"""
        
        # Critical business impact = immediate
        if context.business_impact == BusinessImpact.CRITICAL:
            return AlertUrgency.IMMEDIATE
        
        # Production + high impact + business hours = urgent
        if (context.service_tier == ServiceTier.PRODUCTION and 
            context.business_impact == BusinessImpact.HIGH and
            context.is_business_hours):
            return AlertUrgency.URGENT
        
        # SLA breach risk = immediate
        if context.sla_breach_risk:
            return AlertUrgency.IMMEDIATE
        
        # Customer impact = urgent
        if context.customer_impact_reported:
            return AlertUrgency.URGENT
        
        # After-hours + high impact = urgent
        if not context.is_business_hours and context.business_impact == BusinessImpact.HIGH:
            return AlertUrgency.URGENT
        
        # High-impact metrics = urgent
        if context.metric_type in self.HIGH_IMPACT_METRICS:
            return AlertUrgency.URGENT
        
        # Default based on business impact
        if context.business_impact == BusinessImpact.HIGH:
            return AlertUrgency.NORMAL
        elif context.business_impact == BusinessImpact.MEDIUM:
            return AlertUrgency.NORMAL
        else:
            return AlertUrgency.LOW
    
    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """Parse timestamp string to datetime object"""
        try:
            if timestamp_str:
                return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except Exception as e:
            logger.warning(f"Error parsing timestamp {timestamp_str}: {e}")
        return None
    
    def _is_business_hours(self, dt: Optional[datetime]) -> bool:
        """Check if timestamp falls in business hours (9 AM - 6 PM Singapore time)"""
        if not dt:
            return True  # Default to business hours if unknown
            
        try:
            # Convert to Singapore time (UTC+8)
            singapore_dt = dt.replace(tzinfo=timezone.utc) + timedelta(hours=8)
            hour = singapore_dt.hour
            weekday = singapore_dt.weekday()
            
            # Business hours: 9 AM - 6 PM on weekdays
            return 9 <= hour < 18 and weekday < 5
        except Exception:
            return True  # Default to business hours if error
    
    def _estimate_alert_frequency(self, alert: Dict) -> int:
        """Estimate alert frequency (simplified implementation)"""
        # In a real implementation, this would analyze historical data
        # For now, return a placeholder
        return 1
    
    def _analyze_trend_direction(self, alert: Dict) -> str:
        """Analyze trend direction of similar alerts"""
        # Simplified implementation - would analyze historical patterns
        return "stable"
    
    def _count_related_incidents(self, alert: Dict) -> int:
        """Count related ongoing incidents"""
        # Simplified implementation - would query active incidents
        return 0
    
    def _is_maintenance_window(self, dt: Optional[datetime], title: str) -> bool:
        """Check if alert occurs during maintenance window"""
        if not dt:
            return False
            
        # Check for maintenance keywords
        maintenance_keywords = ['maintenance', 'scheduled', 'planned', 'deployment', 'upgrade']
        title_lower = title.lower()
        
        if any(keyword in title_lower for keyword in maintenance_keywords):
            return True
            
        # Could add scheduled maintenance window logic here
        return False
    
    def _has_customer_impact_reported(self, alert: Dict) -> bool:
        """Check if customer impact has been reported"""
        # Would integrate with customer feedback systems
        return False
    
    def _assess_sla_breach_risk(self, business_impact: BusinessImpact, dt: Optional[datetime]) -> bool:
        """Assess if alert poses SLA breach risk"""
        # Critical impact during business hours poses SLA risk
        if not dt:
            return business_impact == BusinessImpact.CRITICAL
            
        is_bh = self._is_business_hours(dt)
        return business_impact == BusinessImpact.CRITICAL and is_bh
    
    def _check_intelligent_recent_escalations(self, alert: Dict, context: EscalationContext) -> Optional[str]:
        """Intelligent recent escalation check based on context"""
        try:
            from msteamdev.tools.alert_store import load_escalation_log_sync
            
            escalations = load_escalation_log_sync()
            alert_title = alert.get('title', '')
            current_time = self._parse_timestamp(alert.get('timestamp', ''))
            
            if not current_time:
                return None
            
            # Context-aware cooldown periods
            if context.business_impact == BusinessImpact.CRITICAL:
                cooldown_hours = 2  # Very short cooldown for critical issues
            elif context.business_impact == BusinessImpact.HIGH:
                cooldown_hours = 8 if context.is_business_hours else 4
            elif context.business_impact == BusinessImpact.MEDIUM:
                cooldown_hours = 24 if context.is_business_hours else 12
            else:
                cooldown_hours = 48  # Longer cooldown for low impact
            
            # Check for recent escalations
            cutoff_time = current_time - timedelta(hours=cooldown_hours)
            
            recent_escalations = []
            for escalation in escalations:
                if (escalation.get('title') == alert_title and
                    escalation.get('escalated', False)):
                    
                    try:
                        esc_time = datetime.fromisoformat(escalation['timestamp'].replace('Z', '+00:00'))
                        if esc_time >= cutoff_time:
                            recent_escalations.append(escalation)
                    except:
                        continue
            
            if recent_escalations:
                return (f"🟢 INTELLIGENT SUPPRESSION: Recent escalation within {cooldown_hours}h "
                       f"cooldown ({context.business_impact.value} impact)")
            
            return None
            
        except Exception as e:
            logger.warning(f"Error checking recent escalations: {e}")
            return None
    
    def _format_escalation_reason(self, alert: Dict, context: EscalationContext, 
                                 escalate: bool, reasons: List[str], urgency: AlertUrgency) -> str:
        """Format comprehensive escalation reason"""
        
        symbol = "🔺" if escalate else "🟢"
        action = "ESCALATION APPROVED" if escalate else "ESCALATION SUPPRESSED"
        
        reason = f"{symbol} {action}:\n"
        reason += f"- Title: {alert.get('title')}\n"
        reason += f"- Severity: {context.severity_declared} (detected: {context.severity_from_title})\n"
        reason += f"- Incident: {alert.get('incident_number')}\n"
        reason += f"- Timestamp: {alert.get('timestamp')}\n"
        reason += f"- Business Impact: {context.business_impact.value}\n"
        reason += f"- Service Tier: {context.service_tier.value}\n"
        reason += f"- Metric Type: {context.metric_type}\n"
        reason += f"- Urgency: {urgency.value}\n"
        reason += f"- Business Hours: {'Yes' if context.is_business_hours else 'No'}\n"
        reason += f"- Weekend: {'Yes' if context.is_weekend else 'No'}\n"
        
        if context.maintenance_window:
            reason += f"- Maintenance Window: Active\n"
        
        if context.sla_breach_risk:
            reason += f"- SLA Risk: HIGH\n"
        
        reason += f"\nIntelligent Policy Reasoning:\n"
        for r in reasons:
            reason += f"  {r}\n"
        
        reason += f"\nDecision: {'ESCALATE' if escalate else 'SUPPRESS'}"
        
        return reason
    
    def _create_fallback_context(self) -> EscalationContext:
        """Create fallback context for error scenarios"""
        return EscalationContext(
            severity_from_title="unknown",
            severity_declared="unknown", 
            metric_type="system",
            service_tier=ServiceTier.PRODUCTION,
            business_impact=BusinessImpact.CRITICAL,  # Err on side of caution
            is_business_hours=True,
            is_weekend=False,
            hour_of_day=12,
            alert_frequency=1,
            trend_direction="stable",
            related_incidents=0,
            maintenance_window=False,
            customer_impact_reported=False,
            sla_breach_risk=True  # Err on side of caution
        )

# Global policy engine instance
intelligent_policy = IntelligentPolicyEngine()

@tool("IntelligentEscalationPolicy")
def intelligent_escalation_policy(alert_data: str) -> str:
    """
    Apply intelligent, context-aware escalation policy that replaces rigid day-based rules.
    
    This policy engine considers:
    - Business impact assessment from alert content
    - Service tier (production/staging/dev) identification
    - Time-sensitive escalation (business hours vs after-hours)
    - Maintenance window awareness
    - SLA breach risk assessment
    - Dynamic cooldown periods based on impact level
    
    Args:
        alert_data: JSON string with alert information
        
    Returns:
        JSON string with escalation decision, detailed reasoning, and context
    """
    try:
        # Parse alert data
        if isinstance(alert_data, str):
            alert = json.loads(alert_data)
        else:
            alert = alert_data
        
        # Apply intelligent policy
        should_escalate, reason, context = intelligent_policy.assess_escalation_eligibility(alert)
        
        # Format result
        result = {
            "eligible": should_escalate,
            "reason": reason,
            "policy_type": "intelligent_context_aware",
            "context": {
                "business_impact": context.business_impact.value,
                "service_tier": context.service_tier.value,
                "metric_type": context.metric_type,
                "urgency": intelligent_policy._calculate_urgency(context).value,
                "is_business_hours": context.is_business_hours,
                "is_weekend": context.is_weekend,
                "maintenance_window": context.maintenance_window,
                "sla_breach_risk": context.sla_breach_risk,
                "severity_detected": context.severity_from_title,
                "severity_declared": context.severity_declared
            },
            "intelligent_features": {
                "severity_extraction": f"Detected '{context.severity_from_title}' from title",
                "business_impact_assessment": f"Assessed as {context.business_impact.value} impact",
                "service_tier_detection": f"Identified as {context.service_tier.value} environment",
                "dynamic_cooldown": "Context-aware cooldown periods",
                "maintenance_awareness": "Maintenance window detection",
                "sla_risk_assessment": "SLA breach risk evaluation"
            }
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Error in intelligent escalation policy: {e}")
        
        # Fallback to safe escalation
        error_result = {
            "eligible": True,
            "reason": f"FALLBACK ESCALATION: Policy engine error - {str(e)}",
            "policy_type": "emergency_fallback",
            "error": str(e)
        }
        
        return json.dumps(error_result, indent=2)

if __name__ == "__main__":
    # Test the intelligent policy
    test_alerts = [
        {
            "incident_number": "TEST001",
            "title": "ALARM: [CRITICAL] [INFOPRO-RFC] Payment Service Prod - Database Connection Failed",
            "severity": "critical",
            "timestamp": "2025-09-23T14:30:00Z",
            "status": "triggered"
        },
        {
            "incident_number": "TEST002", 
            "title": "ALARM: [WARNING] [DEV] Test Environment - High CPU Utilization",
            "severity": "warning",
            "timestamp": "2025-09-23T02:30:00Z",
            "status": "triggered"
        },
        {
            "incident_number": "TEST003",
            "title": "ALARM: [WARNING] [PROD] Scheduled Maintenance - Disk Cleanup",
            "severity": "warning", 
            "timestamp": "2025-09-23T14:30:00Z",
            "status": "triggered"
        }
    ]
    
    for alert in test_alerts:
        print(f"\n=== Testing Alert: {alert['title'][:50]}... ===")
        result = intelligent_escalation_policy(json.dumps(alert))
        result_data = json.loads(result)
        print(f"Decision: {'ESCALATE' if result_data['eligible'] else 'SUPPRESS'}")
        print(f"Business Impact: {result_data['context']['business_impact']}")
        print(f"Service Tier: {result_data['context']['service_tier']}")
        print(f"Urgency: {result_data['context']['urgency']}")
        print("="*60)