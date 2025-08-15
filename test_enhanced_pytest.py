#!/usr/bin/env python3
"""
Pytest-based Enhanced Tools Integration Tests
Run with: pytest test_enhanced_pytest.py -v
"""

import pytest
import sys
import os
import json
import time
from datetime import datetime, timezone

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import required modules with pytest fixtures handling
pytest_plugins = []

@pytest.fixture(scope="session")
def suppress_warnings():
    """Suppress warnings during testing."""
    import logging
    logging.getLogger().setLevel(logging.ERROR)
    # Suppress specific warnings
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning, module="pdpyras")

@pytest.fixture(scope="session")
def enhanced_tools():
    """Import enhanced tools or skip tests if not available."""
    try:
        from msteamdev.tools.enhanced_tools import (
            read_alert_log_enhanced,
            get_matching_alerts_enhanced,
            check_escalation_eligibility_enhanced,
            get_alert_trends,
            get_system_health as enhanced_get_system_health,
            tool_metrics
        )
        # Return the tool objects themselves - CrewAI tools can be called directly
        return {
            'read_alert_log_enhanced': read_alert_log_enhanced,
            'get_matching_alerts_enhanced': get_matching_alerts_enhanced,
            'check_escalation_eligibility_enhanced': check_escalation_eligibility_enhanced,
            'get_alert_trends': get_alert_trends,
            'enhanced_get_system_health': enhanced_get_system_health,
            'tool_metrics': tool_metrics
        }
    except ImportError as e:
        pytest.skip(f"Enhanced tools not available: {e}")

@pytest.fixture(scope="session")
def crew():
    """Import crew enhanced or return None if not available."""
    try:
        from msteamdev.crew import (
            get_mcp_tools, 
            load_agents, 
            get_system_health,
            start_alert_pipeline
        )
        return {
            'get_mcp_tools': get_mcp_tools,
            'load_agents': load_agents,
            'get_system_health': get_system_health,
            'start_alert_pipeline': start_alert_pipeline
        }
    except ImportError:
        return None

@pytest.fixture
def test_alert():
    """Create a test alert for pipeline testing."""
    return {
        "incident_number": "TEST_ENHANCED_123",
        "title": "Enhanced Tools Test Alert",
        "severity": "critical", 
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "metric": "Test Metric",
        "status": "resolved",  # Use resolved to prevent actual escalation
        "from_email": "test@example.com"
    }

class TestEnhancedToolsDirect:
    """Test enhanced tools directly without dependencies."""
    
    def test_read_alert_log_enhanced(self, enhanced_tools, suppress_warnings):
        """Test ReadAlertLogEnhanced function."""
        # Use run method to execute the tool
        result = enhanced_tools['read_alert_log_enhanced']._run(limit=5, severity_filter="critical")
        assert isinstance(result, str)
        assert len(result) > 0
        # Should return valid JSON or error message
        try:
            json.loads(result)
        except json.JSONDecodeError:
            # If it's not valid JSON, it should be an error message
            assert "Error" in result
    
    def test_get_alert_trends(self, enhanced_tools, suppress_warnings):
        """Test GetAlertTrends function."""
        trends = enhanced_tools['get_alert_trends']._run(hours=24)
        assert isinstance(trends, str)
        
        try:
            trends_data = json.loads(trends)
            assert 'time_period_hours' in trends_data
            assert trends_data['time_period_hours'] == 24
            assert 'total_alerts' in trends_data
            assert isinstance(trends_data['total_alerts'], int)
        except json.JSONDecodeError:
            # If it's not valid JSON, it should be an error message
            assert "Error" in trends
    
    def test_check_escalation_eligibility_enhanced(self, enhanced_tools, suppress_warnings):
        """Test CheckEscalationEligibility function."""
        eligibility = enhanced_tools['check_escalation_eligibility_enhanced']._run(
            incident_number="TEST123",
            severity="critical",
            title="Test Alert", 
            timestamp="2025-01-13T10:00:00Z",
            status="triggered"
        )
        
        assert isinstance(eligibility, str)
        try:
            eligibility_data = json.loads(eligibility)
            
            # Check required fields in response
            required_fields = ['eligible', 'reason', 'incident_number', 'severity']
            for field in required_fields:
                assert field in eligibility_data
        except json.JSONDecodeError:
            # If it's not valid JSON, it should be an error message
            assert "Error" in eligibility
    
    def test_enhanced_get_system_health(self, enhanced_tools, suppress_warnings):
        """Test Enhanced GetSystemHealth function."""
        health = enhanced_tools['enhanced_get_system_health']._run()
        assert isinstance(health, str)
        
        try:
            health_data = json.loads(health)
            assert 'timestamp' in health_data
            assert 'redis_status' in health_data
        except json.JSONDecodeError:
            # If it's not valid JSON, it should be an error message
            assert "Error" in health
    
    def test_tool_metrics_tracking(self, enhanced_tools, suppress_warnings):
        """Test that tool metrics are properly tracked."""
        # Get initial stats
        initial_stats = enhanced_tools['tool_metrics'].get_stats()
        
        # Trigger a tool call
        enhanced_tools['read_alert_log_enhanced']._run(limit=1)
        
        # Check updated stats
        updated_stats = enhanced_tools['tool_metrics'].get_stats()
        assert isinstance(updated_stats, dict)
        
        # Should have recorded the call
        if 'ReadAlertLogEnhanced' in updated_stats:
            stats = updated_stats['ReadAlertLogEnhanced']
            assert 'calls' in stats
            assert 'success_rate' in stats
            assert stats['calls'] > 0

@pytest.mark.skipif("crew is None", reason="Crew enhanced not available")
class TestMCPServerIntegration:
    """Test MCP server integration with enhanced tools."""
    
    def test_mcp_tools_loading(self, crew, suppress_warnings):
        """Test that MCP tools can be loaded."""
        if crew is None:
            pytest.skip("Crew enhanced not available")
            
        mcp_tools = crew['get_mcp_tools']()
        assert isinstance(mcp_tools, list)
        assert len(mcp_tools) > 0
        
        # Check that tools have names
        for tool in mcp_tools:
            assert hasattr(tool, 'name')
    
    def test_enhanced_tools_in_mcp(self, crew, suppress_warnings):
        """Test that enhanced tools are available via MCP."""
        if crew is None:
            pytest.skip("Crew enhanced not available")
            
        mcp_tools = crew['get_mcp_tools']()
        tool_names = [tool.name for tool in mcp_tools]
        
        # Check for enhanced tools
        enhanced_tools = [
            "ReadAlertLogEnhanced",
            "GetMatchingAlertsEnhanced", 
            "CheckEscalationEligibility",
            "GetAlertTrends",
            "GetSystemHealth"
        ]
        
        found_enhanced = [name for name in enhanced_tools if name in tool_names]
        assert len(found_enhanced) >= 3, f"Expected at least 3 enhanced tools, found: {found_enhanced}"

@pytest.mark.skipif("crew is None", reason="Crew enhanced not available") 
class TestAgentIntegration:
    """Test agent tool assignment and integration."""
    
    def test_agent_loading(self, crew, suppress_warnings):
        """Test that agents can be loaded with tools."""
        if crew is None:
            pytest.skip("Crew enhanced not available")
            
        mcp_tools = crew['get_mcp_tools']()
        agents = crew['load_agents'](mcp_tools)
        
        assert isinstance(agents, dict)
        assert len(agents) > 0
    
    def test_escalation_checker_tools(self, crew, suppress_warnings):
        """Test that escalation_checker gets enhanced tools."""
        if crew is None:
            pytest.skip("Crew enhanced not available")
            
        mcp_tools = crew['get_mcp_tools']()
        agents = crew['load_agents'](mcp_tools)
        
        if 'escalation_checker' in agents:
            checker = agents['escalation_checker']
            assert hasattr(checker, 'tools')
            assert len(checker.tools) > 0
            
            tool_names = [tool.name for tool in checker.tools]
            # Should have some enhanced tools
            enhanced_count = sum(1 for name in tool_names 
                               if 'Enhanced' in name or 
                               name in ['CheckEscalationEligibility', 'GetAlertTrends', 'GetSystemHealth'])
            assert enhanced_count > 0, f"escalation_checker should have enhanced tools, got: {tool_names}"

class TestSystemHealth:
    """Test system health integration."""
    
    def test_system_health_structure(self, crew, suppress_warnings):
        """Test system health report structure."""
        if crew is None:
            pytest.skip("Crew enhanced not available")
            
        health_report = crew['get_system_health']()
        
        # Check basic structure
        required_keys = ['timestamp', 'processing_stats', 'environment']
        for key in required_keys:
            assert key in health_report, f"Missing required key: {key}"
        
        assert isinstance(health_report['processing_stats'], dict)
        assert isinstance(health_report['environment'], dict)
    
    def test_enhanced_tools_metrics_integration(self, crew, enhanced_tools, suppress_warnings):
        """Test that enhanced tools metrics are integrated in system health."""
        if crew is None:
            pytest.skip("Crew enhanced not available")
            
        # Trigger some tool usage first
        enhanced_tools['read_alert_log_enhanced']._run(limit=1)
        
        health_report = crew['get_system_health']()
        
        # Should have enhanced tools metrics
        if 'enhanced_tools_metrics' in health_report:
            if health_report['enhanced_tools_metrics'] != 'unavailable':
                assert isinstance(health_report['enhanced_tools_metrics'], dict)

@pytest.mark.skipif("crew is None", reason="Crew enhanced not available")
class TestPipelineIntegration:
    """Test pipeline integration with enhanced tools."""
    
    def test_pipeline_startup(self, crew, test_alert, suppress_warnings):
        """Test that pipeline can be started with enhanced tools."""
        if crew is None:
            pytest.skip("Crew enhanced not available")
            
        result = crew['start_alert_pipeline'](test_alert)
        
        assert isinstance(result, dict)
        assert 'status' in result
        assert result['status'] == 'processing_started'
        
        # Wait a moment for background processing
        time.sleep(1)

class TestToolCompatibility:
    """Test compatibility and error handling."""
    
    def test_function_docstrings(self, enhanced_tools):
        """Test that all enhanced tools have proper docstrings."""
        functions_to_check = [
            'read_alert_log_enhanced',
            'get_matching_alerts_enhanced', 
            'check_escalation_eligibility_enhanced',
            'get_alert_trends',
            'enhanced_get_system_health'
        ]
        
        for func_name in functions_to_check:
            # Check that the tool has a description
            tool = enhanced_tools[func_name]
            assert hasattr(tool, 'description'), f"{func_name} missing description"
            assert tool.description is not None, f"{func_name} has no description"
            assert len(tool.description.strip()) > 0, f"{func_name} has empty description"
    
    def test_error_handling(self, enhanced_tools, suppress_warnings):
        """Test error handling in enhanced tools."""
        # Test with invalid parameters - should not crash
        result = enhanced_tools['check_escalation_eligibility_enhanced']._run(
            incident_number="INVALID",
            severity="invalid_severity",
            title="",
            timestamp="invalid_timestamp",
            status="triggered"
        )
        # Should return error message, not crash
        assert isinstance(result, str)
        assert "Error" in result

# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "skipif: conditionally skip tests"
    )

# Run specific test groups
if __name__ == "__main__":
    # Run with verbose output and show local variables on failure
    pytest.main([__file__, "-v", "--tb=short", "-x"])
