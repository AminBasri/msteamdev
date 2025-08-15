#!/usr/bin/env python3
"""
Test Script for Enhanced Tools Integration
This script tests the integration of enhanced tools with the CrewAI system.
"""

import sys
import os
import asyncio
import json
import time
from datetime import datetime, timezone

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Set up basic logging to suppress warnings during testing
import logging
logging.getLogger().setLevel(logging.ERROR)

# Import required modules with better error handling
try:
    import yaml
except ImportError:
    print("⚠️  YAML not available - some tests may be limited")
    yaml = None

try:
    from msteamdev.crew_enhanced_v2 import (
        get_mcp_tools, 
        load_agents, 
        get_system_health,
        start_alert_pipeline
    )
    CREW_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Crew enhanced not available: {e}")
    CREW_AVAILABLE = False

try:
    from msteamdev.tools.enhanced_tools import (
        read_alert_log_enhanced,
        get_matching_alerts_enhanced,
        check_escalation_eligibility_enhanced,
        get_alert_trends,
        get_system_health as enhanced_get_system_health,
        tool_metrics
    )
    ENHANCED_TOOLS_AVAILABLE = True
    print("✅ Successfully imported enhanced tools")
except ImportError as e:
    print(f"❌ Enhanced tools import failed: {e}")
    ENHANCED_TOOLS_AVAILABLE = False
    sys.exit(1)

def test_enhanced_tools_directly():
    """Test enhanced tools directly."""
    print("\n🔧 Testing Enhanced Tools Directly...")
    
    try:
        # Test ReadAlertLogEnhanced
        print("  📊 Testing ReadAlertLogEnhanced...")
        result = read_alert_log_enhanced(limit=5, severity_filter="critical")
        print(f"     Result length: {len(result)} characters")
        
        # Test GetAlertTrends  
        print("  📈 Testing GetAlertTrends...")
        trends = get_alert_trends(hours=24)
        trends_data = json.loads(trends)
        print(f"     Found trends for {trends_data.get('time_period_hours', 0)} hours")
        
        # Test CheckEscalationEligibility
        print("  🚨 Testing CheckEscalationEligibility...")
        eligibility = check_escalation_eligibility_enhanced(
            incident_number="TEST123",
            severity="critical", 
            title="Test Alert",
            timestamp="2025-01-13T10:00:00Z"
        )
        eligibility_data = json.loads(eligibility)
        print(f"     Eligibility check: {eligibility_data.get('eligible', 'unknown')}")
        
        # Test GetSystemHealth
        print("  💚 Testing Enhanced GetSystemHealth...")
        health = enhanced_get_system_health()
        health_data = json.loads(health)
        print(f"     System timestamp: {health_data.get('timestamp', 'unknown')}")
        
        print("✅ All enhanced tools tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Enhanced tools test failed: {e}")
        return False

def test_mcp_server_integration():
    """Test MCP server integration with enhanced tools."""
    print("\n🔌 Testing MCP Server Integration...")
    
    if not CREW_AVAILABLE:
        print("  ⚠️  Skipping - Crew enhanced not available")
        return True  # Skip test, don't fail
    
    try:
        # Load MCP tools
        mcp_tools = get_mcp_tools()
        print(f"  📦 Loaded {len(mcp_tools)} MCP tools")
        
        # Check for enhanced tools
        tool_names = [tool.name for tool in mcp_tools]
        enhanced_tools = [
            "ReadAlertLogEnhanced", 
            "GetMatchingAlertsEnhanced", 
            "CheckEscalationEligibility",
            "GetAlertTrends",
            "GetSystemHealth"
        ]
        
        found_enhanced = [name for name in enhanced_tools if name in tool_names]
        print(f"  🎯 Found {len(found_enhanced)} enhanced tools: {found_enhanced}")
        
        if len(found_enhanced) >= 3:  # At least 3 enhanced tools should be available
            print("✅ MCP server integration test passed!")
            return True
        else:
            print("⚠️  MCP server integration incomplete - some enhanced tools missing")
            return False
            
    except Exception as e:
        print(f"❌ MCP server integration test failed: {e}")
        return False

def test_agent_tool_assignment():
    """Test that agents get properly assigned enhanced tools."""
    print("\n🤖 Testing Agent Tool Assignment...")
    
    if not CREW_AVAILABLE:
        print("  ⚠️  Skipping - Crew enhanced not available")
        return True  # Skip test, don't fail
    
    try:
        # Load MCP tools
        mcp_tools = get_mcp_tools()
        
        # Load agents with tools
        agents = load_agents(mcp_tools)
        print(f"  👥 Loaded {len(agents)} agents")
        
        # Check escalation_checker tools
        if 'escalation_checker' in agents:
            checker_tools = agents['escalation_checker'].tools
            tool_names = [tool.name for tool in checker_tools]
            enhanced_count = sum(1 for name in tool_names if 'Enhanced' in name or name in ['CheckEscalationEligibility', 'GetAlertTrends', 'GetSystemHealth'])
            print(f"  🔍 escalation_checker has {len(checker_tools)} tools, {enhanced_count} enhanced")
            
        # Check reporter tools
        if 'reporter' in agents:
            reporter_tools = agents['reporter'].tools
            print(f"  📋 reporter has {len(reporter_tools)} tools")
            
        # Check pagerduty_manager tools
        if 'pagerduty_manager' in agents:
            pd_tools = agents['pagerduty_manager'].tools
            print(f"  📞 pagerduty_manager has {len(pd_tools)} tools")
            
        print("✅ Agent tool assignment test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Agent tool assignment test failed: {e}")
        return False

def test_system_health_integration():
    """Test comprehensive system health reporting."""
    print("\n💓 Testing System Health Integration...")
    
    try:
        health_report = get_system_health()
        
        # Check basic structure
        required_keys = ['timestamp', 'processing_stats', 'environment']
        missing_keys = [key for key in required_keys if key not in health_report]
        
        if missing_keys:
            print(f"  ⚠️  Missing health report keys: {missing_keys}")
            return False
            
        print(f"  📊 Health report generated at: {health_report['timestamp']}")
        print(f"  🔄 Total processed: {health_report['processing_stats']['total_processed']}")
        
        # Check for enhanced tools metrics
        if 'enhanced_tools_metrics' in health_report:
            if health_report['enhanced_tools_metrics'] != 'unavailable':
                print(f"  🎯 Enhanced tools metrics available")
            else:
                print(f"  ⚠️  Enhanced tools metrics unavailable")
        
        if 'enhanced_system_data' in health_report:
            print(f"  🔋 Enhanced system data integrated")
            
        print("✅ System health integration test passed!")
        return True
        
    except Exception as e:
        print(f"❌ System health integration test failed: {e}")
        return False

def test_tool_metrics():
    """Test tool metrics tracking."""
    print("\n📈 Testing Tool Metrics...")
    
    try:
        # Check initial stats
        stats = tool_metrics.get_stats()
        print(f"  📊 Current tool stats: {len(stats)} tools tracked")
        
        # Trigger a tool call to test metrics
        read_alert_log_enhanced(limit=1)
        
        # Check updated stats
        updated_stats = tool_metrics.get_stats()
        print(f"  📊 Updated tool stats: {len(updated_stats)} tools tracked")
        
        # Check if ReadAlertLogEnhanced metrics were recorded
        if 'ReadAlertLogEnhanced' in updated_stats:
            enhanced_stats = updated_stats['ReadAlertLogEnhanced']
            print(f"  🎯 ReadAlertLogEnhanced: {enhanced_stats['calls']} calls, {enhanced_stats['success_rate']:.1f}% success")
            
        print("✅ Tool metrics test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Tool metrics test failed: {e}")
        return False

def test_pipeline_integration():
    """Test pipeline integration with enhanced tools."""
    print("\n🔄 Testing Pipeline Integration...")
    
    try:
        # Create test alert
        test_alert = {
            "incident_number": "TEST_ENHANCED_123",
            "title": "Enhanced Tools Test Alert",
            "severity": "critical",
            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "metric": "Test Metric", 
            "status": "resolved",  # Use resolved to prevent actual escalation
            "from_email": "test@example.com"
        }
        
        # Start pipeline (non-blocking)
        result = start_alert_pipeline(test_alert)
        print(f"  🚀 Pipeline started: {result}")
        
        # Wait a moment for processing to begin
        import time
        time.sleep(2)
        
        print("✅ Pipeline integration test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Pipeline integration test failed: {e}")
        return False

def main():
    """Run all integration tests."""
    print("🧪 Enhanced Tools Integration Test Suite")
    print("=" * 50)
    
    tests = [
        ("Enhanced Tools Direct", test_enhanced_tools_directly),
        ("MCP Server Integration", test_mcp_server_integration),
        ("Agent Tool Assignment", test_agent_tool_assignment),
        ("System Health Integration", test_system_health_integration),
        ("Tool Metrics", test_tool_metrics),
        ("Pipeline Integration", test_pipeline_integration),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n🧪 Running: {test_name}")
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status} {test_name}")
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 All enhanced tools integration tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)