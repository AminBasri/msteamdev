#!/usr/bin/env python3
"""
Test script for the Weekly Report System

This script demonstrates how the weekly report system works by:
1. Running a daily report to generate sample data
2. Generating a weekly report from the stored data
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from datetime import datetime
import arrow
from msteamdev.daily_report import run
from msteamdev.weekly_report_generator import generate_weekly_report_for_date_range
from msteamdev.daily_metrics_storage import daily_storage

def test_weekly_report_system():
    """Test the complete weekly report system."""
    
    print("=" * 80)
    print("TESTING WEEKLY REPORT SYSTEM")
    print("=" * 80)
    
    # Test date range (using the same date as our test data)
    test_date = datetime(2025, 10, 24, 7, 0, 0)
    shift_start = test_date
    shift_end = datetime(2025, 10, 24, 16, 0, 0)
    
    print(f"\n1. GENERATING DAILY REPORT FOR TEST DATA")
    print("-" * 50)
    print(f"   Date: {test_date.strftime('%Y-%m-%d')}")
    print(f"   Shift: Morning (7:00 - 16:00)")
    
    try:
        # Run daily report to generate metrics
        print("   Running daily report...")
        run('morning', shift_start, shift_end)
        print("   ✓ Daily report completed")
        
        # Check if metrics were saved
        date_str = test_date.strftime('%Y-%m-%d')
        saved_metrics = daily_storage.load_daily_metrics(date_str, 'morning')
        
        if saved_metrics:
            print(f"   ✓ Daily metrics saved successfully")
            print(f"     - Total alerts: {saved_metrics.total_alerts}")
            print(f"     - SLA compliance: {saved_metrics.sla_compliance:.1f}%")
            print(f"     - MTTR: {saved_metrics.mttr_minutes:.1f}m")
        else:
            print("   ⚠ Daily metrics not found - this is expected for first run")
            
    except Exception as e:
        print(f"   ✗ Daily report failed: {e}")
        return
    
    print(f"\n2. CHECKING AVAILABLE METRICS DATA")
    print("-" * 50)
    
    available_dates = daily_storage.list_available_dates()
    if available_dates:
        print(f"   Available dates with metrics: {len(available_dates)}")
        for date in available_dates[-5:]:  # Show last 5 dates
            print(f"     - {date}")
    else:
        print("   No metrics data available yet")
        print("   Note: You need to run daily reports for several days to see weekly aggregation")
    
    print(f"\n3. GENERATING WEEKLY REPORT")
    print("-" * 50)
    
    # Generate weekly report for the test week
    week_start = "2025-10-21"  # Monday
    week_end = "2025-10-27"    # Sunday
    
    print(f"   Week: {week_start} to {week_end}")
    
    try:
        generate_weekly_report_for_date_range(week_start, week_end)
        print("   ✓ Weekly report generated successfully")
    except Exception as e:
        print(f"   ✗ Weekly report failed: {e}")
    
    print(f"\n4. SYSTEM OVERVIEW")
    print("-" * 50)
    print("   The weekly report system works as follows:")
    print("   1. Daily reports automatically save metrics to JSON files")
    print("   2. Weekly reports aggregate data from multiple daily metrics")
    print("   3. Detailed analysis includes trends and recommendations")
    print("   4. Data is stored in: data/daily_metrics/ directory")
    
    print(f"\n5. USAGE EXAMPLES")
    print("-" * 50)
    print("   Generate daily report:")
    print("     python -m src.msteamdev.daily_report --shift morning")
    print("")
    print("   Generate weekly report for last week:")
    print("     python -m src.msteamdev.weekly_report_generator --last-week")
    print("")
    print("   Generate weekly report for specific dates:")
    print("     python -m src.msteamdev.weekly_report_generator --start 2025-10-21 --end 2025-10-27")
    
    print("\n" + "=" * 80)
    print("WEEKLY REPORT SYSTEM TEST COMPLETED")
    print("=" * 80)

def simulate_multiple_days():
    """Simulate running daily reports for multiple days to test weekly aggregation."""
    
    print("\n" + "=" * 80)
    print("SIMULATING MULTIPLE DAYS FOR WEEKLY AGGREGATION")
    print("=" * 80)
    
    # Simulate a week of data (Monday to Sunday)
    base_date = datetime(2025, 10, 21, 7, 0, 0)  # Monday
    
    for day_offset in range(7):  # 7 days
        current_date = base_date.replace(day=base_date.day + day_offset)
        shift_start = current_date
        shift_end = current_date.replace(hour=16, minute=0, second=0)
        
        print(f"\nDay {day_offset + 1}: {current_date.strftime('%Y-%m-%d')} ({current_date.strftime('%A')})")
        print("-" * 40)
        
        try:
            # Run morning shift
            run('morning', shift_start, shift_end)
            
            # Check if metrics were saved
            date_str = current_date.strftime('%Y-%m-%d')
            saved_metrics = daily_storage.load_daily_metrics(date_str, 'morning')
            
            if saved_metrics:
                print(f"   ✓ Morning shift: {saved_metrics.total_alerts} alerts, {saved_metrics.sla_compliance:.1f}% SLA")
            else:
                print(f"   ⚠ Morning shift: No metrics saved")
                
        except Exception as e:
            print(f"   ✗ Morning shift failed: {e}")
    
    print(f"\nNow generating weekly report for the simulated week...")
    print("-" * 50)
    
    try:
        generate_weekly_report_for_date_range("2025-10-21", "2025-10-27")
    except Exception as e:
        print(f"Weekly report failed: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test weekly report system')
    parser.add_argument('--simulate', action='store_true', help='Simulate multiple days')
    parser.add_argument('--test', action='store_true', help='Run basic test')
    
    args = parser.parse_args()
    
    if args.simulate:
        simulate_multiple_days()
    elif args.test:
        test_weekly_report_system()
    else:
        # Default: run basic test
        test_weekly_report_system()
