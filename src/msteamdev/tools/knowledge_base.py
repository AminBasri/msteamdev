# src/msteamdev/tools/knowledge_base.py

import json
import os
from datetime import datetime, timezone
from crewai.tools import tool
from typing import Dict, List, Optional
import re
from collections import defaultdict
import logging

# Get the knowledge base path from webhook_receiver configuration
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
KNOWLEDGE_BASE_DIR = os.path.join(BASE_DIR, "..", "..", "knowledge")
INCIDENT_KNOWLEDGE_FILE = os.path.join(KNOWLEDGE_BASE_DIR, "incident_knowledge.json")
PATTERNS_KNOWLEDGE_FILE = os.path.join(KNOWLEDGE_BASE_DIR, "alert_patterns.json")

logger = logging.getLogger(__name__)

def load_incident_knowledge() -> Dict:
    """Load incident knowledge base"""
    try:
        if os.path.exists(INCIDENT_KNOWLEDGE_FILE):
            with open(INCIDENT_KNOWLEDGE_FILE, "r") as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading incident knowledge: {e}")
        return {}

def load_pattern_knowledge() -> Dict:
    """Load pattern knowledge base"""
    try:
        if os.path.exists(PATTERNS_KNOWLEDGE_FILE):
            with open(PATTERNS_KNOWLEDGE_FILE, "r") as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading pattern knowledge: {e}")
        return {}

def similarity_score(text1: str, text2: str) -> float:
    """Calculate similarity between two alert titles"""
    if not text1 or not text2:
        return 0.0
    
    text1_lower = text1.lower()
    text2_lower = text2.lower()
    
    # Exact match
    if text1_lower == text2_lower:
        return 1.0
    
    # Check for common keywords
    words1 = set(re.findall(r'\b\w+\b', text1_lower))
    words2 = set(re.findall(r'\b\w+\b', text2_lower))
    
    if not words1 or not words2:
        return 0.0
    
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    
    return len(intersection) / len(union)

@tool("GetIncidentKnowledge")
def get_incident_knowledge(incident_number: str) -> str:
    """
    Get comprehensive knowledge about a specific incident including customer feedback,
    root causes, resolution methods, and business context.
    
    Args:
        incident_number: The incident number to get knowledge for
    
    Returns:
        JSON string with complete incident knowledge
    """
    try:
        knowledge = load_incident_knowledge()
        incident_data = knowledge.get(str(incident_number), {})
        
        if not incident_data:
            return json.dumps({
                "status": "not_found",
                "message": f"No knowledge found for incident {incident_number}",
                "similar_incidents": []
            }, indent=2)
        
        # Format the knowledge for AI consumption
        formatted_knowledge = {
            "incident_number": incident_number,
            "basic_info": {
                "title": incident_data.get("title", ""),
                "severity": incident_data.get("severity", ""),
                "metric": incident_data.get("metric", ""),
                "created_at": incident_data.get("created_at", ""),
                "last_updated": incident_data.get("last_updated", "")
            },
            "summary": incident_data.get("summary", {}),
            "customer_feedback": {
                "notes_count": len(incident_data.get("notes", [])),
                "recent_notes": incident_data.get("notes", [])[-3:] if incident_data.get("notes") else [],
                "knowledge_updates_count": len(incident_data.get("knowledge_updates", [])),
                "key_insights": [update for update in incident_data.get("knowledge_updates", []) 
                               if update.get("type") in ["root_cause", "resolution", "customer_feedback"]]
            },
            "learned_info": {
                "root_cause": incident_data.get("summary", {}).get("root_cause"),
                "resolution_method": incident_data.get("summary", {}).get("resolution_method"),
                "false_positive": incident_data.get("summary", {}).get("false_positive", False),
                "planned_maintenance": incident_data.get("summary", {}).get("planned_maintenance", False),
                "business_impact": incident_data.get("summary", {}).get("business_impact"),
                "customer_response": incident_data.get("summary", {}).get("customer_response", False)
            }
        }
        
        return json.dumps(formatted_knowledge, indent=2)
        
    except Exception as e:
        logger.error(f"Error getting incident knowledge for {incident_number}: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Error retrieving knowledge: {str(e)}"
        }, indent=2)

@tool("FindSimilarIncidents")
def find_similar_incidents(alert_title: str, severity: str = None, metric: str = None, limit: int = 5) -> str:
    """
    Find similar incidents based on alert title, severity and metric, with their resolutions and outcomes.
    
    Args:
        alert_title: The alert title to find similar incidents for
        severity: Optional severity filter (critical, warning, etc.)
        metric: Optional metric filter (e.g., cpu, memory)
        limit: Maximum number of similar incidents to return
    
    Returns:
        JSON string with similar incidents and their knowledge
    """
    try:
        knowledge = load_incident_knowledge()
        similar_incidents = []
        
        for incident_num, incident_data in knowledge.items():
            incident_title = incident_data.get("title", "")
            incident_severity = incident_data.get("severity", "").lower()
            incident_metric = incident_data.get("metric", "").lower()

            # Filter by metric if provided
            if metric and incident_metric != metric.lower():
                continue

            # Calculate similarity
            sim_score = similarity_score(alert_title, incident_title)
            
            # Filter by similarity threshold and optional severity
            if sim_score > 0.3:  # 30% similarity threshold
                if severity is None or incident_severity == severity.lower():
                    similar_incidents.append({
                        "incident_number": incident_num,
                        "title": incident_title,
                        "severity": incident_data.get("severity", ""),
                        "similarity_score": sim_score,
                        "summary": incident_data.get("summary", {}),
                        "created_at": incident_data.get("created_at", ""),
                        "last_updated": incident_data.get("last_updated", ""),
                        "knowledge_highlights": {
                            "has_root_cause": bool(incident_data.get("summary", {}).get("root_cause")),
                            "has_resolution": bool(incident_data.get("summary", {}).get("resolution_method")),
                            "false_positive": incident_data.get("summary", {}).get("false_positive", False),
                            "planned_maintenance": incident_data.get("summary", {}).get("planned_maintenance", False),
                            "customer_feedback": incident_data.get("summary", {}).get("customer_response", False)
                        }
                    })
        
        # Sort by similarity score
        similar_incidents.sort(key=lambda x: x["similarity_score"], reverse=True)
        
        result = {
            "query": {
                "alert_title": alert_title,
                "severity_filter": severity,
                "metric_filter": metric,
                "limit": limit
            },
            "total_found": len(similar_incidents),
            "incidents": similar_incidents[:limit],
            "patterns_detected": _analyze_incident_patterns(similar_incidents[:limit])
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Error finding similar incidents: {e}")
        return json.dumps({
            "status": "error", 
            "message": f"Error finding similar incidents: {str(e)}"
        }, indent=2)

@tool("AnalyzeResolutionPatterns") 
def analyze_resolution_patterns(alert_title: str, severity: str = None, metric: str = None) -> str:
    """
    Analyze how similar alerts were actually resolved in the past.
    
    Args:
        alert_title: The alert title to analyze patterns for
        severity: Optional severity filter
        metric: Optional metric filter
    
    Returns:
        JSON string with resolution analysis and recommendations
    """
    try:
        knowledge = load_incident_knowledge()
        pattern_knowledge = load_pattern_knowledge()
        
        # Find similar incidents with resolutions
        resolved_incidents = []
        false_positives = []
        planned_maintenance = []
        
        for incident_num, incident_data in knowledge.items():
            incident_title = incident_data.get("title", "")
            incident_severity = incident_data.get("severity", "").lower()
            incident_metric = incident_data.get("metric", "").lower()
            summary = incident_data.get("summary", {})

            # Filter by metric if provided
            if metric and incident_metric != metric.lower():
                continue
            
            # Check similarity
            sim_score = similarity_score(alert_title, incident_title)
            if sim_score > 0.3:
                if severity is None or incident_severity == severity.lower():
                    incident_info = {
                        "incident_number": incident_num,
                        "title": incident_title,
                        "similarity_score": sim_score,
                        "summary": summary
                    }
                    
                    if summary.get("false_positive"):
                        false_positives.append(incident_info)
                    elif summary.get("planned_maintenance"):
                        planned_maintenance.append(incident_info)
                    elif summary.get("resolution_method") or summary.get("root_cause"):
                        resolved_incidents.append(incident_info)
        
        # Analyze patterns from pattern knowledge base
        metric_patterns = {}
        extracted_metric = metric or _extract_metric_from_title(alert_title)
        if extracted_metric in pattern_knowledge:
            metric_patterns = pattern_knowledge[extracted_metric]
        
        # Generate recommendations
        recommendations = _generate_resolution_recommendations(
            resolved_incidents, false_positives, planned_maintenance, metric_patterns
        )
        
        result = {
            "analysis": {
                "alert_title": alert_title,
                "extracted_metric": extracted_metric,
                "total_similar_incidents": len(resolved_incidents) + len(false_positives) + len(planned_maintenance)
            },
            "patterns": {
                "resolved_incidents": len(resolved_incidents),
                "false_positives": len(false_positives),
                "planned_maintenance": len(planned_maintenance),
                "false_positive_rate": len(false_positives) / max(1, len(resolved_incidents) + len(false_positives)) * 100
            },
            "resolution_methods": _extract_resolution_methods(resolved_incidents),
            "common_root_causes": _extract_root_causes(resolved_incidents),
            "recommendations": recommendations,
            "detailed_incidents": {
                "resolved": resolved_incidents[:3],  # Top 3 most similar
                "false_positives": false_positives[:3],
                "planned_maintenance": planned_maintenance[:3]
            }
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Error analyzing resolution patterns: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Error analyzing patterns: {str(e)}"
        }, indent=2)

@tool("GetFalsePositivePatterns")
def get_false_positive_patterns(alert_title: str = None, metric: str = None) -> str:
    """
    Get known false positive patterns to help identify alerts that don't need escalation.
    
    Args:
        alert_title: Optional specific alert title to check
        metric: Optional metric type to get patterns for
    
    Returns:
        JSON string with false positive patterns and indicators
    """
    try:
        knowledge = load_incident_knowledge()
        pattern_knowledge = load_pattern_knowledge()
        
        false_positive_incidents = []
        
        # Collect all false positive incidents
        for incident_num, incident_data in knowledge.items():
            summary = incident_data.get("summary", {})
            if summary.get("false_positive"):
                incident_info = {
                    "incident_number": incident_num,
                    "title": incident_data.get("title", ""),
                    "metric": incident_data.get("metric", ""),
                    "severity": incident_data.get("severity", ""),
                    "reason": summary.get("root_cause", ""),
                    "notes": [note.get("content", "")[:100] + "..." if len(note.get("content", "")) > 100 
                             else note.get("content", "") 
                             for note in incident_data.get("notes", [])[-2:]]  # Last 2 notes
                }
                
                # If filtering by alert title or metric
                if metric and incident_info["metric"].lower() != metric.lower():
                    continue

                if alert_title:
                    if similarity_score(alert_title, incident_info["title"]) > 0.3:
                        false_positive_incidents.append(incident_info)
                else:
                    false_positive_incidents.append(incident_info)

        # Get pattern-based false positive indicators
        pattern_indicators = {}
        if metric and metric in pattern_knowledge:
            pattern_indicators = {
                "false_positive_indicators": pattern_knowledge[metric].get("false_positive_indicators", []),
                "common_false_positive_phrases": pattern_knowledge[metric].get("false_positive_indicators", [])[:5]
            }
        
        result = {
            "query": {
                "alert_title": alert_title,
                "metric": metric
            },
            "total_false_positives_found": len(false_positive_incidents),
            "pattern_indicators": pattern_indicators,
            "recent_false_positives": false_positive_incidents[:10],  # Most recent 10
            "common_false_positive_reasons": _extract_false_positive_reasons(false_positive_incidents),
            "recommendations": {
                "suppress_if": _generate_suppression_rules(false_positive_incidents),
                "investigate_further_if": _generate_investigation_rules(false_positive_incidents)
            }
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Error getting false positive patterns: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Error retrieving false positive patterns: {str(e)}"
        }, indent=2)

@tool("GetBusinessContextKnowledge")
def get_business_context_knowledge(alert_title: str = None, metric: str = None) -> str:
    """
    Get business context knowledge about alerts including maintenance windows,
    customer impact patterns, and business-critical vs non-critical classifications.
    
    Args:
        alert_title: Optional alert title to get specific business context for
        metric: Optional metric filter
    
    Returns:
        JSON string with business context knowledge
    """
    try:
        knowledge = load_incident_knowledge()
        
        business_contexts = []
        maintenance_patterns = []
        customer_impact_data = []
        
        for incident_num, incident_data in knowledge.items():
            summary = incident_data.get("summary", {})
            incident_metric = incident_data.get("metric", "").lower()

            # Filter by metric if provided
            if metric and incident_metric != metric.lower():
                continue

            # Check if this incident has business context
            has_business_context = any([
                summary.get("planned_maintenance"),
                summary.get("business_impact"),
                summary.get("customer_response")
            ])
            
            if has_business_context:
                incident_context = {
                    "incident_number": incident_num,
                    "title": incident_data.get("title", ""),
                    "metric": incident_data.get("metric", ""),
                    "severity": incident_data.get("severity", ""),
                    "business_context": {
                        "planned_maintenance": summary.get("planned_maintenance", False),
                        "business_impact": summary.get("business_impact"),
                        "customer_response": summary.get("customer_response", False)
                    },
                    "notes": [note.get("content", "") for note in incident_data.get("notes", [])]
                }
                
                # Categorize by type
                if summary.get("planned_maintenance"):
                    maintenance_patterns.append(incident_context)
                if summary.get("customer_response"):
                    customer_impact_data.append(incident_context)
                
                # If filtering by alert title
                if alert_title is None or similarity_score(alert_title, incident_data.get("title", "")) > 0.3:
                    business_contexts.append(incident_context)
        
        result = {
            "query": {
                "alert_title": alert_title,
                "metric_filter": metric,
                "filtered": alert_title is not None
            },
            "business_context_incidents": business_contexts[:10],  # Top 10 most relevant
            "patterns": {
                "maintenance_windows": _analyze_maintenance_patterns(maintenance_patterns),
                "customer_impact_indicators": _analyze_customer_impact(customer_impact_data),
                "business_critical_indicators": _identify_business_critical_patterns(business_contexts)
            },
            "recommendations": {
                "likely_planned_maintenance": _detect_maintenance_likelihood(alert_title, maintenance_patterns),
                "expected_customer_impact": _predict_customer_impact(alert_title, customer_impact_data),
                "escalation_priority": _determine_business_priority(alert_title, business_contexts)
            }
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Error getting business context knowledge: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Error retrieving business context: {str(e)}"
        }, indent=2)

# Helper functions for analysis
def _analyze_incident_patterns(incidents: List[Dict]) -> Dict:
    """Analyze patterns in a list of incidents"""
    if not incidents:
        return {}
    
    patterns = {
        "false_positive_count": sum(1 for i in incidents if i.get("knowledge_highlights", {}).get("false_positive")),
        "planned_maintenance_count": sum(1 for i in incidents if i.get("knowledge_highlights", {}).get("planned_maintenance")),
        "resolved_count": sum(1 for i in incidents if i.get("knowledge_highlights", {}).get("has_resolution")),
        "most_common_severity": max(set([i.get("severity", "") for i in incidents]), 
                                  key=[i.get("severity", "") for i in incidents].count) if incidents else ""
    }
    
    return patterns

def _extract_metric_from_title(title: str) -> str:
    """Extract metric type from alert title"""
    patterns = [
        (r'\b(cpu|processor)\b', 'cpu'),
        (r'\b(memory|ram|mem)\b', 'memory'),
        (r'\b(disk|storage|drive)\b', 'disk'),
        (r'\b(network|bandwidth|traffic)\b', 'network'),
        (r'\b(database|db|mysql|postgres)\b', 'database'),
        (r'\b(apache|nginx|http|web)\b', 'web_server'),
        (r'\b(load|latency|response)\b', 'performance')
    ]
    
    title_lower = title.lower()
    for pattern, metric in patterns:
        if re.search(pattern, title_lower):
            return metric
    
    return "unknown"

def _generate_resolution_recommendations(resolved_incidents, false_positives, planned_maintenance, metric_patterns):
    """Generate recommendations based on incident patterns"""
    recommendations = []
    
    total_incidents = len(resolved_incidents) + len(false_positives) + len(planned_maintenance)
    
    if total_incidents == 0:
        return ["No historical data available - proceed with standard escalation process"]
    
    false_positive_rate = len(false_positives) / total_incidents * 100
    maintenance_rate = len(planned_maintenance) / total_incidents * 100
    
    if false_positive_rate > 50:
        recommendations.append(f"HIGH FALSE POSITIVE RATE ({false_positive_rate:.1f}%) - Consider suppressing similar alerts")
    
    if maintenance_rate > 30:
        recommendations.append(f"OFTEN PLANNED MAINTENANCE ({maintenance_rate:.1f}%) - Verify if this is scheduled work")
    
    if len(resolved_incidents) > 0:
        common_resolutions = _extract_resolution_methods(resolved_incidents)
        if common_resolutions:
            recommendations.append(f"Common resolution methods: {', '.join(list(common_resolutions.keys())[:3])}")
    
    return recommendations

def _extract_resolution_methods(incidents):
    """Extract common resolution methods from incidents"""
    methods = defaultdict(int)
    for incident in incidents:
        method = incident.get("summary", {}).get("resolution_method")
        if method:
            methods[method] += 1
    return dict(methods)

def _extract_root_causes(incidents):
    """Extract common root causes from incidents"""
    causes = defaultdict(int)
    for incident in incidents:
        cause = incident.get("summary", {}).get("root_cause")
        if cause:
            causes[cause] += 1
    return dict(causes)

def _extract_false_positive_reasons(incidents):
    """Extract common reasons for false positives"""
    reasons = defaultdict(int)
    for incident in incidents:
        reason = incident.get("reason")
        if reason:
            reasons[reason] += 1
    return dict(reasons)

def _generate_suppression_rules(incidents):
    """Generate rules for when to suppress alerts"""
    if not incidents:
        return []
    
    rules = []
    # Analyze patterns in false positive incidents
    common_phrases = defaultdict(int)
    
    for incident in incidents:
        for note in incident.get("notes", []):
            if "false" in note.lower() or "no issue" in note.lower():
                # Extract key phrases
                words = note.lower().split()
                for i in range(len(words) - 1):
                    phrase = f"{words[i]} {words[i+1]}"
                    common_phrases[phrase] += 1
    
    # Convert to suppression rules
    for phrase, count in sorted(common_phrases.items(), key=lambda x: x[1], reverse=True)[:3]:
        if count > 1:
            rules.append(f"Alert mentions '{phrase}'")
    
    return rules

def _generate_investigation_rules(incidents):
    """Generate rules for when to investigate further"""
    if not incidents:
        return ["Always investigate if no historical pattern matches"]
    
    return [
        "Alert severity is 'critical' regardless of false positive history",
        "Alert occurs outside normal business hours",
        "Multiple similar alerts trigger within short timeframe"
    ]

def _analyze_maintenance_patterns(maintenance_incidents):
    """Analyze patterns in maintenance incidents"""
    if not maintenance_incidents:
        return {}
    
    # Analyze timing patterns, common maintenance types, etc.
    patterns = {
        "total_maintenance_incidents": len(maintenance_incidents),
        "common_maintenance_indicators": ["planned", "batch job", "deployment", "scheduled"],
        "typical_duration": "varies"  # Would need more data to calculate
    }
    
    return patterns

def _analyze_customer_impact(customer_incidents):
    """Analyze customer impact patterns"""
    if not customer_incidents:
        return {}
    
    patterns = {
        "total_customer_impact_incidents": len(customer_incidents),
        "common_impact_indicators": ["service down", "performance degraded", "login issues"],
        "escalation_recommended": True
    }
    
    return patterns

def _identify_business_critical_patterns(business_contexts):
    """Identify business critical alert patterns"""
    if not business_contexts:
        return {}
    
    critical_keywords = ["payment", "login", "database", "service", "critical"]
    critical_count = sum(1 for ctx in business_contexts 
                        if any(keyword in ctx.get("title", "").lower() for keyword in critical_keywords))
    
    return {
        "business_critical_incidents": critical_count,
        "critical_keywords": critical_keywords,
        "criticality_rate": critical_count / max(1, len(business_contexts)) * 100
    }

def _detect_maintenance_likelihood(alert_title, maintenance_patterns):
    """Detect likelihood that current alert is maintenance"""
    if not alert_title or not maintenance_patterns:
        return "unknown"
    
    maintenance_keywords = ["batch", "scheduled", "planned", "deployment", "backup", "maintenance"]
    title_lower = alert_title.lower()
    
    matches = sum(1 for keyword in maintenance_keywords if keyword in title_lower)
    
    if matches >= 2:
        return "high"
    elif matches == 1:
        return "medium"
    else:
        return "low"

def _predict_customer_impact(alert_title, customer_impact_data):
    """Predict customer impact based on historical data"""
    if not alert_title or not customer_impact_data:
        return "unknown"
    
    impact_keywords = ["service", "login", "payment", "database", "api", "web"]
    title_lower = alert_title.lower()
    
    matches = sum(1 for keyword in impact_keywords if keyword in title_lower)
    
    if matches >= 2:
        return "high"
    elif matches == 1:
        return "medium"
    else:
        return "low"

def _determine_business_priority(alert_title, business_contexts):
    """Determine business priority for escalation"""
    if not alert_title:
        return "standard"
    
    high_priority_keywords = ["critical", "payment", "login", "database down", "service unavailable"]
    title_lower = alert_title.lower()
    
    if any(keyword in title_lower for keyword in high_priority_keywords):
        return "high"
    else:
        return "standard"
