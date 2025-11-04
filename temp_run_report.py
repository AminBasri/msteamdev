from datetime import datetime, timezone
import arrow
import os
import sys
import tempfile
import shutil

# Add the project root to Python path
sys.path.append('/home/crewai/msteamdev')

# Create a temporary copy of the daily_report.py file
original_file = '/home/crewai/msteamdev/src/msteamdev/daily_report.py'
temp_file = os.path.join(tempfile.gettempdir(), 'daily_report_temp.py')
shutil.copy2(original_file, temp_file)

# Read the file content
with open(temp_file, 'r') as f:
    content = f.read()

# Replace the problematic format call with the correct variable name
content = content.replace("'p2_kpi_compliance_display'", "'p2_kpi_compliance'")

# Write the modified content back
with open(temp_file, 'w') as f:
    f.write(content)

# Set required environment variables
os.environ['LOCAL_TZ_NAME'] = 'Asia/Kuala_Lumpur'
os.environ['GEMINI_API_KEY'] = 'your-api-key'
os.environ['SMTP_HOST'] = 'smtp.example.com'
os.environ['SMTP_PORT'] = '587'
os.environ['SMTP_USERNAME'] = 'noc@example.com'
os.environ['SMTP_PASSWORD'] = 'password'
os.environ['REPORT_EMAIL'] = 'noc-reports@example.com'

# Convert date to datetime objects
date_str = "2025-10-24"
shift_start = datetime.strptime(f"{date_str} 07:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
shift_end = datetime.strptime(f"{date_str} 16:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

# Import the temporary module and run
import importlib.util
spec = importlib.util.spec_from_file_location("daily_report_temp", temp_file)
daily_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(daily_report)

daily_report.run(shift_type="morning", shift_start=shift_start, shift_end=shift_end)

# Clean up
os.remove(temp_file)