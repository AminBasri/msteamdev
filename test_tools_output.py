import asyncio
import logging
from src.msteamdev.tools.enhanced_tools import get_system_health, read_alert_log_enhanced

# Configure basic logging to see output
logging.basicConfig(level=logging.DEBUG)

async def main():
    """
    An async function to demonstrate calling an enhanced tool.
    """
    print("--- Demonstrating 'get_system_health' tool ---")
    
    # This tool provides a snapshot of the system's health, including tool metrics.
    # Initially, the metrics will be empty.
    health_status_before = get_system_health()
    print("Initial System Health:")
    print(health_status_before)
    
    print("\n--- Calling another tool ('read_alert_log_enhanced') to generate metrics ---")
    # We call another tool to see the metrics tracking in action.
    # The @with_tool_metrics decorator will capture this call.
    read_alert_log_enhanced(limit=10, severity_filter="critical")
    
    print("\n--- Calling 'get_system_health' again to see updated metrics ---")
    # Now, the health status should include metrics for the tool we just called.
    health_status_after = get_system_health()
    print("Updated System Health:")
    print(health_status_after)

if __name__ == "__main__":
    # Running the async main function
    asyncio.run(main())
