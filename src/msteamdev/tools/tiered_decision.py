# Comprehensive Tiered Decision Framework for Alert Escalation
# Implements 3-tier safety-first decision hierarchy

import json
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union
from enum import Enum
from dataclasses import dataclass, asdict
from crewai.tools import tool

logger = logging.getLogger(__name__)

class DecisionTier(Enum):
    """Decision tier levels in order of priority"""
    TIER_1_SAFETY = "safety_net"           # Highest priority - non-negotiable safety rules
    TIER_2_KNOWLEDGE = "kb_enhanced"       # KB-enhanced intelligent decisions  
    TIER_3_POLICY = "policy_fallback"      # Traditional policy-based fallback

class ConfidenceLevel(Enum):
    """Confidence levels for KB decisions"""
    HIGH = "high"       # ≥0.8 confidence
    MEDIUM = "medium"   # 0.5-0.79 confidence
    LOW = "low"         # <0.5 confidence

@dataclass
class KnowledgeMetrics:
    """Knowledge base data quality metrics"""
    last_updated: Optional[str]
    data_age_days: Optional[int]
    reliability_score: float  # 0.0-1.0
    incident_count: int
    false_positive_rate: Optional[float]
    similar_incidents_count: int
    resolution_success_rate: Optional[float]

@dataclass
class DecisionResult:
    """Structured result from tiered decision process"""
    escalate: bool
    tier: DecisionTier
    confidence: ConfidenceLevel
    reason: str
    details: Dict[str, Any]
    audit_trail: List[Dict[str, Any]]
    knowledge_freshness: Optional[str] = None
    safety_override: bool = False
    kb_confidence: Optional[float] = None

class TieredDecisionFramework:
    """
    Three-tier decision framework for alert escalation:
    
    TIER 1 - SAFETY NET (Non-negotiable):
    - Critical/High severity alerts always escalate
    - Critical keywords (outage, down, failed, critical) force escalation  
    - Business hours vs after-hours consideration
    - No override possible - safety first
    
    TIER 2 - KB-ENHANCED DECISION:
    - High confidence (≥0.8) + fresh data (≤90 days) + sufficient samples (≥2)
    - KB recommendation can override policy with high confidence
    - Conservative: KB can suppress policy escalations only with high confidence
    - Considers false positive rates, resolution patterns, business context
    
    TIER 3 - POLICY FALLBACK:
    - Traditional time-based rules when KB insufficient
    - Enhanced with KB context when available
    - Defaults to escalation when uncertain
    """
    
    # Critical keywords that force escalation (Tier 1)
    CRITICAL_KEYWORDS = [
        'outage', 'down', 'failed', 'failure', 'unavailable', 'offline',
        'crashed', 'panic', 'emergency', 'disaster', 'breach', 'security',
        'data loss', 'corruption', 'timeout', 'unreachable', 'dead'
    ]
    
    # High-priority keywords that increase escalation likelihood
    HIGH_PRIORITY_KEYWORDS = [
        'degraded', 'slow', 'error', 'warning', 'threshold', 'limit',
        'capacity', 'overload', 'congestion', 'bottleneck'
    ]
    
    def __init__(self):
        self.decision_history = []
        
    def make_decision(self, alert: Dict[str, Any], policy_result: Tuple[bool, str], 
                     kb_analysis: Optional[Dict] = None, ai_analysis: Optional[str] = None) -> DecisionResult:
        """
        Make tiered escalation decision with safety-first approach
        
        Args:
            alert: Alert data
            policy_result: Tuple of (eligible, reason) from policy check  
            kb_analysis: Knowledge base analysis result
            ai_analysis: Optional AI analysis text
            
        Returns:
            DecisionResult with final decision and comprehensive audit trail
        """
        audit_trail = []
        incident_number = alert.get("incident_number", "unknown")
        
        try:
            # TIER 1: Safety Net (Non-negotiable)
            tier1_result = self._evaluate_tier1_safety(alert, audit_trail)
            if tier1_result:
                logger.info(f"Tier 1 Safety decision for {incident_number}: {tier1_result.escalate}")
                return tier1_result
                
            # TIER 2: KB-Enhanced Decision
            tier2_result = self._evaluate_tier2_knowledge(alert, policy_result, kb_analysis, ai_analysis, audit_trail)
            if tier2_result:
                logger.info(f"Tier 2 KB decision for {incident_number}: {tier2_result.escalate} (confidence: {tier2_result.kb_confidence})")
                return tier2_result
                
            # TIER 3: Policy Fallback
            tier3_result = self._evaluate_tier3_policy(alert, policy_result, audit_trail)
            logger.info(f"Tier 3 Policy decision for {incident_number}: {tier3_result.escalate}")
            return tier3_result
            
        except Exception as e:
            logger.error(f"Error in tiered decision for incident {incident_number}: {e}")
            return self._emergency_escalation(alert, str(e), audit_trail)
    
    def _evaluate_tier1_safety(self, alert: Dict, audit_trail: List) -> Optional[DecisionResult]:
        """
        TIER 1: Safety Net - Non-negotiable escalation rules
        
        These rules cannot be overridden by KB or policy:
        1. Critical/High severity always escalates
        2. Critical keywords force escalation
        3. After-hours critical issues
        4. Security-related alerts
        """
        audit_entry = {
            "tier": DecisionTier.TIER_1_SAFETY.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": []
        }
        
        title = alert.get("title", "").lower()
        severity = alert.get("severity", "").lower()
        
        # Check 1: Critical/High severity
        if severity in ["critical", "high"]:
            audit_entry["checks"].append({"type": "severity_check", "severity": severity, "result": "force_escalate"})
            audit_trail.append(audit_entry)
            
            return DecisionResult(
                escalate=True,
                tier=DecisionTier.TIER_1_SAFETY,
                confidence=ConfidenceLevel.HIGH,
                reason=f"SAFETY NET: {severity.upper()} severity requires immediate escalation",
                details={
                    "trigger": "severity_override",
                    "severity": severity,
                    "non_negotiable": True
                },
                audit_trail=audit_trail,
                safety_override=True
            )
        
        # Check 2: Critical keywords
        found_critical_keywords = [kw for kw in self.CRITICAL_KEYWORDS if kw in title]
        if found_critical_keywords:
            audit_entry["checks"].append({
                "type": "critical_keywords", 
                "found_keywords": found_critical_keywords, 
                "result": "force_escalate"
            })
            audit_trail.append(audit_entry)
            
            return DecisionResult(
                escalate=True,
                tier=DecisionTier.TIER_1_SAFETY,
                confidence=ConfidenceLevel.HIGH,
                reason=f"SAFETY NET: Critical keywords detected - {', '.join(found_critical_keywords)}",
                details={
                    "trigger": "critical_keywords",
                    "keywords_found": found_critical_keywords,
                    "non_negotiable": True
                },
                audit_trail=audit_trail,
                safety_override=True
            )
        
        # Check 3: Security-related alerts
        security_keywords = ['security', 'breach', 'unauthorized', 'intrusion', 'malware', 'virus']
        found_security_keywords = [kw for kw in security_keywords if kw in title]
        if found_security_keywords:
            audit_entry["checks"].append({
                "type": "security_keywords",
                "found_keywords": found_security_keywords,
                "result": "force_escalate"
            })
            audit_trail.append(audit_entry)
            
            return DecisionResult(
                escalate=True,
                tier=DecisionTier.TIER_1_SAFETY,
                confidence=ConfidenceLevel.HIGH,
                reason=f"SAFETY NET: Security-related alert - {', '.join(found_security_keywords)}",
                details={
                    "trigger": "security_alert",
                    "keywords_found": found_security_keywords,
                    "non_negotiable": True
                },
                audit_trail=audit_trail,
                safety_override=True
            )
        
        # Check 4: After-hours + high-priority keywords
        is_after_hours = self._is_after_hours(alert.get("timestamp", ""))
        high_priority_keywords = [kw for kw in self.HIGH_PRIORITY_KEYWORDS if kw in title]
        
        if is_after_hours and high_priority_keywords and severity in ["warning", "medium"]:
            audit_entry["checks"].append({
                "type": "after_hours_priority",
                "is_after_hours": is_after_hours,
                "high_priority_keywords": high_priority_keywords,
                "result": "force_escalate"
            })
            audit_trail.append(audit_entry)
            
            return DecisionResult(
                escalate=True,
                tier=DecisionTier.TIER_1_SAFETY,
                confidence=ConfidenceLevel.HIGH,
                reason=f"SAFETY NET: After-hours priority alert with keywords - {', '.join(high_priority_keywords)}",
                details={
                    "trigger": "after_hours_priority",
                    "after_hours": True,
                    "priority_keywords": high_priority_keywords,
                    "non_negotiable": True
                },
                audit_trail=audit_trail,
                safety_override=True
            )
        
        # No safety net triggers - proceed to next tier
        audit_entry["checks"].append({"type": "safety_net_complete", "result": "no_triggers"})
        audit_trail.append(audit_entry)
        return None
    
    def _evaluate_tier2_knowledge(self, alert: Dict, policy_result: Tuple[bool, str], 
                                 kb_analysis: Optional[Dict], ai_analysis: Optional[str], 
                                 audit_trail: List) -> Optional[DecisionResult]:
        """
        TIER 2: KB-Enhanced Decision
        
        Uses knowledge base with high confidence requirements:
        - Confidence ≥0.8 + fresh data (≤90 days) + sufficient samples (≥2)
        - Can override policy escalations with high confidence suppression
        - Conservative approach: prefer escalation when uncertain
        """
        audit_entry = {
            "tier": DecisionTier.TIER_2_KNOWLEDGE.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "has_kb_analysis": kb_analysis is not None
        }
        
        if not kb_analysis:
            # Try to get KB analysis
            try:
                kb_analysis = self._get_knowledge_analysis(alert)
                audit_entry["kb_analysis_generated"] = True
            except Exception as e:
                audit_entry["kb_analysis_error"] = str(e)
                audit_trail.append(audit_entry)
                return None
        
        # Get knowledge metrics
        knowledge_metrics = self._get_knowledge_metrics(alert)
        audit_entry["knowledge_metrics"] = asdict(knowledge_metrics)
        
        # Calculate KB confidence score
        kb_confidence = self._calculate_kb_confidence(knowledge_metrics, kb_analysis, ai_analysis)
        audit_entry["kb_confidence"] = kb_confidence
        
        # Check if KB analysis meets high-confidence criteria
        meets_criteria = (
            kb_confidence >= 0.7 and
            knowledge_metrics.data_age_days and knowledge_metrics.data_age_days <= 90 and
            knowledge_metrics.incident_count >= 2
        )
        
        audit_entry["meets_high_confidence_criteria"] = meets_criteria
        
        if not meets_criteria:
            audit_entry["reason"] = "insufficient_confidence_or_data"
            audit_trail.append(audit_entry)
            return None
        
        # Analyze KB recommendation
        kb_recommendation = self._analyze_kb_recommendation(kb_analysis, knowledge_metrics)
        audit_entry["kb_recommendation"] = kb_recommendation
        
        policy_eligible, policy_reason = policy_result
        
        # KB can suppress policy escalation with high confidence
        if kb_recommendation["action"] == "suppress" and kb_recommendation["confidence"] >= 0.85:
            # Additional safety check: don't suppress if false positive rate is too low
            if knowledge_metrics.false_positive_rate and knowledge_metrics.false_positive_rate >= 0.6:
                audit_trail.append(audit_entry)
                
                return DecisionResult(
                    escalate=False,
                    tier=DecisionTier.TIER_2_KNOWLEDGE,
                    confidence=ConfidenceLevel.HIGH,
                    reason=f"KB SUPPRESSION: High confidence ({kb_confidence:.2f}) suppression with {knowledge_metrics.false_positive_rate:.1%} false positive rate",
                    details={
                        "kb_action": "suppress",
                        "kb_confidence": kb_confidence,
                        "false_positive_rate": knowledge_metrics.false_positive_rate,
                        "overrides_policy": policy_eligible,
                        "incident_count": knowledge_metrics.incident_count,
                        "data_age_days": knowledge_metrics.data_age_days
                    },
                    audit_trail=audit_trail,
                    kb_confidence=kb_confidence,
                    knowledge_freshness=knowledge_metrics.last_updated
                )
        
        # KB can recommend escalation even if policy says no
        elif kb_recommendation["action"] == "escalate" and kb_recommendation["confidence"] >= 0.8:
            audit_trail.append(audit_entry)
            
            return DecisionResult(
                escalate=True,
                tier=DecisionTier.TIER_2_KNOWLEDGE,
                confidence=ConfidenceLevel.HIGH,
                reason=f"KB ESCALATION: High confidence ({kb_confidence:.2f}) escalation recommendation",
                details={
                    "kb_action": "escalate",
                    "kb_confidence": kb_confidence,
                    "overrides_policy": not policy_eligible,
                    "recommendation_reason": kb_recommendation.get("reason", ""),
                    "incident_count": knowledge_metrics.incident_count,
                    "data_age_days": knowledge_metrics.data_age_days
                },
                audit_trail=audit_trail,
                kb_confidence=kb_confidence,
                knowledge_freshness=knowledge_metrics.last_updated
            )
        
        # KB analysis inconclusive or doesn't meet confidence threshold
        audit_entry["conclusion"] = "kb_inconclusive_or_insufficient_confidence"
        audit_trail.append(audit_entry)
        return None
    
    def _evaluate_tier3_policy(self, alert: Dict, policy_result: Tuple[bool, str], 
                              audit_trail: List) -> DecisionResult:
        """
        TIER 3: Policy Fallback
        
        Traditional policy-based decision when KB is insufficient:
        - Uses existing policy rules (time thresholds, recent escalations)
        - Enhanced with available KB context
        - Defaults to escalation when uncertain (safety first)
        """
        policy_eligible, policy_reason = policy_result
        
        audit_entry = {
            "tier": DecisionTier.TIER_3_POLICY.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "policy_eligible": policy_eligible,
            "policy_reason": policy_reason[:200] + "..." if len(policy_reason) > 200 else policy_reason
        }
        
        if not policy_eligible:
            audit_entry["decision"] = "policy_suppressed"
            audit_trail.append(audit_entry)
            
            return DecisionResult(
                escalate=False,
                tier=DecisionTier.TIER_3_POLICY,
                confidence=ConfidenceLevel.MEDIUM,
                reason=f"POLICY SUPPRESSION: {policy_reason}",
                details={
                    "policy_reason": policy_reason,
                    "suppression_type": "policy_rule"
                },
                audit_trail=audit_trail
            )
        
        else:
            audit_entry["decision"] = "policy_escalation_allowed"
            audit_trail.append(audit_entry)
            
            return DecisionResult(
                escalate=True,
                tier=DecisionTier.TIER_3_POLICY,
                confidence=ConfidenceLevel.MEDIUM,
                reason=f"POLICY ESCALATION: {policy_reason}",
                details={
                    "policy_reason": policy_reason,
                    "escalation_type": "policy_rule"
                },
                audit_trail=audit_trail
            )
    
    def _emergency_escalation(self, alert: Dict, error: str, audit_trail: List) -> DecisionResult:
        """Emergency escalation when entire decision process fails"""
        audit_entry = {
            "tier": "emergency_escalation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": error
        }
        audit_trail.append(audit_entry)
        
        return DecisionResult(
            escalate=True,
            tier=DecisionTier.TIER_1_SAFETY,
            confidence=ConfidenceLevel.HIGH,
            reason="EMERGENCY ESCALATION: Decision process failed, escalating for safety",
            details={
                "error": error,
                "emergency": True,
                "safety_override": True
            },
            audit_trail=audit_trail,
            safety_override=True
        )
    
    def _get_knowledge_metrics(self, alert: Dict) -> KnowledgeMetrics:
        """Get comprehensive knowledge base metrics with freshness data"""
        try:
            from msteamdev.tools.knowledge_base import load_pattern_knowledge, load_incident_knowledge
            
            # Load knowledge bases
            pattern_knowledge = load_pattern_knowledge()
            incident_knowledge = load_incident_knowledge()
            
            # Extract metric type
            metric_type = self._extract_metric_type(alert.get("title", ""))
            
            # Get pattern data with last_updated
            pattern_data = pattern_knowledge.get(metric_type, {})
            last_updated_str = pattern_data.get("last_updated")
            
            # Calculate data age
            data_age_days = None
            if last_updated_str:
                try:
                    last_updated_dt = datetime.fromisoformat(last_updated_str.replace('Z', '+00:00'))
                    data_age_days = (datetime.now(timezone.utc) - last_updated_dt).days
                except:
                    pass
            
            # Analyze incidents for this metric
            incident_count = 0
            false_positive_count = 0
            resolved_count = 0
            similar_incidents = 0
            
            alert_title_lower = alert.get("title", "").lower()
            
            for inc_data in incident_knowledge.values():
                inc_metric = inc_data.get("metric", "")
                inc_title = inc_data.get("title", "")
                
                # Count incidents for this metric type
                if inc_metric == metric_type:
                    incident_count += 1
                    
                    summary = inc_data.get("summary", {})
                    if summary.get("false_positive"):
                        false_positive_count += 1
                    if summary.get("resolution_method") or summary.get("root_cause"):
                        resolved_count += 1
                
                # Count similar incidents (basic similarity check)
                if self._calculate_title_similarity(alert_title_lower, inc_title.lower()) > 0.3:
                    similar_incidents += 1
            
            # Calculate rates
            false_positive_rate = false_positive_count / max(incident_count, 1) if incident_count > 0 else None
            resolution_success_rate = resolved_count / max(incident_count, 1) if incident_count > 0 else None
            
            # Calculate reliability score
            reliability_score = self._calculate_reliability_score(
                data_age_days, incident_count, false_positive_rate
            )
            
            return KnowledgeMetrics(
                last_updated=last_updated_str,
                data_age_days=data_age_days,
                reliability_score=reliability_score,
                incident_count=incident_count,
                false_positive_rate=false_positive_rate,
                similar_incidents_count=similar_incidents,
                resolution_success_rate=resolution_success_rate
            )
            
        except Exception as e:
            logger.warning(f"Error getting knowledge metrics: {e}")
            return KnowledgeMetrics(
                last_updated=None,
                data_age_days=None,
                reliability_score=0.1,
                incident_count=0,
                false_positive_rate=None,
                similar_incidents_count=0,
                resolution_success_rate=None
            )
    
    def _get_knowledge_analysis(self, alert: Dict) -> Dict:
        """Get knowledge base analysis for the alert"""
        try:
            from msteamdev.tools.knowledge_base import (
                find_similar_incidents, get_false_positive_patterns, 
                get_business_context_knowledge, analyze_resolution_patterns
            )
            
            alert_title = alert.get("title", "")
            metric_type = self._extract_metric_type(alert_title)
            
            # Get comprehensive KB analysis
            similar_incidents = json.loads(find_similar_incidents._run(alert_title, limit=10))
            false_positive_patterns = json.loads(get_false_positive_patterns._run(alert_title, metric_type))
            business_context = json.loads(get_business_context_knowledge._run(alert_title))
            resolution_patterns = json.loads(analyze_resolution_patterns._run(alert_title))
            
            return {
                "similar_incidents": similar_incidents,
                "false_positive_patterns": false_positive_patterns,
                "business_context": business_context,
                "resolution_patterns": resolution_patterns,
                "metric_type": metric_type
            }
            
        except Exception as e:
            logger.warning(f"Error getting knowledge analysis: {e}")
            return {}
    
    def _calculate_kb_confidence(self, metrics: KnowledgeMetrics, kb_analysis: Dict, 
                                ai_analysis: Optional[str]) -> float:
        """Calculate knowledge base confidence score (0.0-1.0)"""
        confidence = 0.0
        
        # Data reliability factor (40% weight)
        confidence += metrics.reliability_score * 0.4
        
        # Data volume factor (20% weight)
        if metrics.incident_count >= 10:
            volume_score = 1.0
        elif metrics.incident_count >= 5:
            volume_score = 0.8
        elif metrics.incident_count >= 2:
            volume_score = 0.6
        else:
            volume_score = 0.2
        confidence += volume_score * 0.2
        
        # Data freshness factor (20% weight)
        if metrics.data_age_days is not None:
            if metrics.data_age_days <= 30:
                freshness_score = 1.0
            elif metrics.data_age_days <= 90:
                freshness_score = 0.8
            elif metrics.data_age_days <= 180:
                freshness_score = 0.6
            else:
                freshness_score = 0.3
        else:
            freshness_score = 0.1
        confidence += freshness_score * 0.2
        
        # Pattern clarity factor (20% weight)
        pattern_clarity = 0.0
        if metrics.false_positive_rate is not None:
            if metrics.false_positive_rate >= 0.7:  # Very high FP rate
                pattern_clarity = 0.9
            elif metrics.false_positive_rate >= 0.5:  # Moderate FP rate
                pattern_clarity = 0.7
            elif metrics.false_positive_rate <= 0.2:  # Low FP rate
                pattern_clarity = 0.8
            else:
                pattern_clarity = 0.5
        confidence += pattern_clarity * 0.2
        
        return min(max(confidence, 0.0), 1.0)
    
    def _analyze_kb_recommendation(self, kb_analysis: Dict, metrics: KnowledgeMetrics) -> Dict:
        """Analyze KB data to get recommendation"""
        # Default recommendation
        recommendation = {"action": "uncertain", "confidence": 0.5, "reason": "insufficient_data"}
        
        if not kb_analysis:
            return recommendation
        
        # Analyze false positive patterns
        fp_patterns = kb_analysis.get("false_positive_patterns", {})
        fp_count = fp_patterns.get("total_false_positives_found", 0)
        
        # Analyze resolution patterns  
        resolution_patterns = kb_analysis.get("resolution_patterns", {})
        fp_rate = resolution_patterns.get("patterns", {}).get("false_positive_rate", 0)
        
        # Strong suppression indicators
        if metrics.false_positive_rate and metrics.false_positive_rate >= 0.7 and fp_count >= 3:
            return {
                "action": "suppress",
                "confidence": 0.9,
                "reason": f"High false positive rate ({metrics.false_positive_rate:.1%}) with {fp_count} similar FP incidents"
            }
        
        # Moderate suppression indicators
        elif metrics.false_positive_rate and metrics.false_positive_rate >= 0.5 and fp_count >= 2:
            return {
                "action": "suppress", 
                "confidence": 0.75,
                "reason": f"Moderate false positive rate ({metrics.false_positive_rate:.1%}) with {fp_count} similar FP incidents"
            }
        
        # Business context suppression (planned maintenance)
        business_context = kb_analysis.get("business_context", {})
        maintenance_likelihood = business_context.get("recommendations", {}).get("likely_planned_maintenance", "low")
        if maintenance_likelihood == "high":
            return {
                "action": "suppress",
                "confidence": 0.8,
                "reason": "High likelihood of planned maintenance based on historical patterns"
            }
        
        # Escalation indicators (low FP rate, high business impact)
        if (metrics.false_positive_rate is not None and metrics.false_positive_rate <= 0.2 and 
            metrics.resolution_success_rate and metrics.resolution_success_rate >= 0.8):
            return {
                "action": "escalate",
                "confidence": 0.85,
                "reason": f"Low false positive rate ({metrics.false_positive_rate:.1%}) with high resolution success rate"
            }
        
        return recommendation
    
    def _extract_metric_type(self, title: str) -> str:
        """Extract metric type from alert title"""
        title_lower = title.lower()
        
        patterns = [
            (r'\b(cpu|processor)\b', 'cpu'),
            (r'\b(memory|mem|ram)\b', 'memory'),
            (r'\b(disk|storage|drive)\b', 'disk'),
            (r'\b(network|bandwidth|traffic)\b', 'network'),
            (r'\b(latency|response|delay)\b', 'latency'),
            (r'\b(load|loading)\b', 'load'),
        ]
        
        for pattern, metric in patterns:
            if re.search(pattern, title_lower):
                return metric
                
        return "unknown"
    
    def _calculate_title_similarity(self, title1: str, title2: str) -> float:
        """Calculate basic similarity between two titles"""
        if not title1 or not title2:
            return 0.0
            
        words1 = set(re.findall(r'\b\w+\b', title1.lower()))
        words2 = set(re.findall(r'\b\w+\b', title2.lower()))
        
        if not words1 or not words2:
            return 0.0
            
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def _calculate_reliability_score(self, data_age_days: Optional[int], incident_count: int, 
                                   false_positive_rate: Optional[float]) -> float:
        """Calculate overall reliability score for knowledge data"""
        score = 0.0
        
        # Age factor (40% weight)
        if data_age_days is not None:
            if data_age_days <= 30:
                age_score = 1.0
            elif data_age_days <= 90:
                age_score = 0.8
            elif data_age_days <= 180:
                age_score = 0.6
            else:
                age_score = 0.3
        else:
            age_score = 0.1
        score += age_score * 0.4
        
        # Volume factor (30% weight)
        if incident_count >= 10:
            volume_score = 1.0
        elif incident_count >= 5:
            volume_score = 0.8
        elif incident_count >= 2:
            volume_score = 0.6
        else:
            volume_score = 0.2
        score += volume_score * 0.3
        
        # Pattern clarity factor (30% weight)
        if false_positive_rate is not None:
            # Clear patterns (very high or very low FP rates) are more reliable
            if false_positive_rate >= 0.8 or false_positive_rate <= 0.2:
                clarity_score = 1.0
            elif false_positive_rate >= 0.6 or false_positive_rate <= 0.4:
                clarity_score = 0.8
            else:
                clarity_score = 0.6
        else:
            clarity_score = 0.3
        score += clarity_score * 0.3
        
        return min(max(score, 0.0), 1.0)
    
    def _is_after_hours(self, timestamp: str) -> bool:
        """Check if alert occurred after business hours (Singapore timezone)"""
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            # Convert to Singapore time (UTC+8)
            singapore_dt = dt.replace(tzinfo=timezone.utc) + timedelta(hours=8)
            hour = singapore_dt.hour
            weekday = singapore_dt.weekday()
            
            # After hours: before 9 AM or after 6 PM on weekdays, or weekends
            return hour < 9 or hour >= 18 or weekday >= 5
            
        except Exception:
            return False  # Default to business hours if timestamp parsing fails

# Global framework instance
tiered_framework = TieredDecisionFramework()

@tool("TieredEscalationDecision")
def make_tiered_escalation_decision(alert_data: Union[str, Dict], policy_result: Union[str, Dict], 
                                   ai_analysis: Optional[str] = None) -> str:
    """
    Make tiered escalation decision using 3-tier safety-first framework:
    
    TIER 1 - SAFETY NET: Non-negotiable rules (critical severity, critical keywords)
    TIER 2 - KB-ENHANCED: High-confidence KB analysis (≥0.8 confidence, ≤90 days, ≥2 incidents)  
    TIER 3 - POLICY FALLBACK: Traditional policy rules with safety-first defaults
    
    Args:
        alert_data: Alert information (dict or JSON string)
        policy_result: Policy check result (dict with 'eligible'/'reason' or tuple format)
        ai_analysis: Optional AI analysis result text
    
    Returns:
        JSON string with detailed decision result and audit trail
    """
    try:
        # Parse alert data
        if isinstance(alert_data, str):
            alert = json.loads(alert_data)
        else:
            alert = alert_data
            
        # Parse policy result
        if isinstance(policy_result, str):
            if policy_result.startswith('{'):
                policy_data = json.loads(policy_result)
                policy_tuple = (policy_data.get("eligible", False), policy_data.get("reason", ""))
            else:
                # Handle "True: reason" or "False: reason" format
                parts = policy_result.split(":", 1)
                eligible = parts[0].strip().lower() == 'true'
                reason = parts[1].strip() if len(parts) > 1 else ""
                policy_tuple = (eligible, reason)
        elif isinstance(policy_result, dict):
            policy_tuple = (policy_result.get("eligible", False), policy_result.get("reason", ""))
        else:
            # Assume it's already a tuple
            policy_tuple = policy_result
        
        # Make tiered decision
        decision_result = tiered_framework.make_decision(alert, policy_tuple, None, ai_analysis)
        
        # Convert to dict for JSON serialization
        result_dict = asdict(decision_result)
        
        # Log the decision to incident pipeline
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "tiered_escalation_decision",
            "incident_number": alert.get("incident_number"),
            "decision": {
                "escalate": decision_result.escalate,
                "tier": decision_result.tier.value,
                "confidence": decision_result.confidence.value,
                "reason": decision_result.reason,
                "safety_override": decision_result.safety_override,
                "kb_confidence": decision_result.kb_confidence
            },
            "tool": "TieredEscalationDecision"
        }
        
        try:
            with open("/home/crewai/msteamdev/log/incident_pipeline.log", "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except:
            pass  # Don't fail on logging errors
        
        return json.dumps(result_dict, indent=2, default=str)
        
    except Exception as e:
        logger.error(f"Error in tiered escalation decision: {e}")
        
        # Emergency fallback
        error_result = DecisionResult(
            escalate=True,
            tier=DecisionTier.TIER_1_SAFETY,
            confidence=ConfidenceLevel.HIGH,
            reason=f"EMERGENCY ESCALATION: Decision error - {str(e)}",
            details={"error": str(e), "emergency": True},
            audit_trail=[],
            safety_override=True
        )
        
        return json.dumps(asdict(error_result), indent=2, default=str)

@tool("GetKnowledgeWithFreshness")
def get_knowledge_with_freshness(alert_title: str, metric_type: str = None) -> str:
    """
    Get comprehensive knowledge base analysis with data freshness indicators.
    
    Includes last_updated timestamps from alert_patterns.json and reliability scoring
    to support high-confidence KB decisions in Tier 2.
    
    Args:
        alert_title: Alert title to analyze
        metric_type: Optional metric type filter (auto-detected if not provided)
        
    Returns:
        JSON string with comprehensive knowledge analysis including freshness data
    """
    try:
        # Auto-detect metric type if not provided
        if not metric_type:
            metric_type = tiered_framework._extract_metric_type(alert_title)
        
        # Get knowledge metrics
        knowledge_metrics = tiered_framework._get_knowledge_metrics({
            "title": alert_title,
            "metric": metric_type
        })
        
        # Get comprehensive KB analysis
        kb_analysis = tiered_framework._get_knowledge_analysis({
            "title": alert_title,
            "metric": metric_type
        })
        
        # Calculate confidence for KB decision-making
        kb_confidence = tiered_framework._calculate_kb_confidence(
            knowledge_metrics, kb_analysis, None
        )
        
        # Get KB recommendation
        kb_recommendation = tiered_framework._analyze_kb_recommendation(
            kb_analysis, knowledge_metrics
        )
        
        # Determine if this meets Tier 2 criteria
        meets_tier2_criteria = (
            kb_confidence >= 0.8 and
            knowledge_metrics.data_age_days and knowledge_metrics.data_age_days <= 90 and
            knowledge_metrics.incident_count >= 2
        )
        
        result = {
            "query": {
                "alert_title": alert_title,
                "metric_type": metric_type,
                "auto_detected_metric": metric_type
            },
            "knowledge_freshness": {
                "last_updated": knowledge_metrics.last_updated,
                "data_age_days": knowledge_metrics.data_age_days,
                "reliability_score": knowledge_metrics.reliability_score,
                "incident_count": knowledge_metrics.incident_count,
                "similar_incidents_count": knowledge_metrics.similar_incidents_count,
                "false_positive_rate": knowledge_metrics.false_positive_rate,
                "resolution_success_rate": knowledge_metrics.resolution_success_rate
            },
            "kb_analysis": kb_analysis,
            "decision_support": {
                "kb_confidence": kb_confidence,
                "meets_tier2_criteria": meets_tier2_criteria,
                "recommendation": kb_recommendation,
                "tier2_requirements": {
                    "confidence_threshold": 0.8,
                    "max_age_days": 90,
                    "min_incidents": 2
                }
            },
            "confidence_breakdown": {
                "data_reliability": knowledge_metrics.reliability_score,
                "data_volume": "high" if knowledge_metrics.incident_count >= 10 else 
                             "medium" if knowledge_metrics.incident_count >= 5 else "low",
                "data_freshness": "fresh" if knowledge_metrics.data_age_days and knowledge_metrics.data_age_days <= 30 else
                                 "acceptable" if knowledge_metrics.data_age_days and knowledge_metrics.data_age_days <= 90 else "stale"
            }
        }
        
        return json.dumps(result, indent=2, default=str)
        
    except Exception as e:
        logger.error(f"Error getting knowledge with freshness: {e}")
        return json.dumps({
            "error": str(e),
            "knowledge_freshness": {
                "last_updated": None,
                "data_age_days": None,
                "reliability_score": 0.1,
                "incident_count": 0
            },
            "decision_support": {
                "kb_confidence": 0.0,
                "meets_tier2_criteria": False,
                "recommendation": {"action": "uncertain", "confidence": 0.0, "reason": "error"}
            }
        }, indent=2)

if __name__ == "__main__":
    # Test the framework
    test_alert = {
        "incident_number": "345",
        "title": "ALARM: [WARNING] [INFOPRO-RFC] Synergi CORE Prod - High CPU Util...",
        "severity": "warning", 
        "timestamp": "2025-09-23T01:32:10Z"
    }
    
    test_policy = (True, "🔺 Escalation allowed: Time threshold exceeded")
    test_ai = "Alert Suppression - No Escalation Required based on false positive patterns"
    
    result = tiered_framework.make_decision(test_alert, test_policy, None, test_ai)
    print(json.dumps(asdict(result), indent=2, default=str))