import os
import re
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import json

# Directory where logs are stored
LOG_DIR = '/home/crewai/msteamuat/log/'


def parse_crew_log(log_path):
    data = []
    if not os.path.exists(log_path):
        return pd.DataFrame(data)

    with open(log_path, 'r') as f:
        for line in f:
            # Example: 2025-07-29 14:47:51,374 - INFO - CrewAI pipeline for incident 237 finished in 199.08 seconds.
            match_finish = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - CrewAI pipeline for incident (\d+) finished in ([\d.]+) seconds\.',
                line
            )
            if match_finish:
                timestamp_str, incident_id, duration = match_finish.groups()
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'incident_id': int(incident_id),
                    'duration': float(duration),
                    'log_type': 'crew_pipeline_finish'
                })

            # Example: 2025-07-25 16:03:07,819 - INFO - Raw acknowledgment task result for incident 227: {"status": "success", "message": "Acknowledged"}
            match_ack_result = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - Raw acknowledgment task result for incident (\d+): (.*)',
                line
            )
            if match_ack_result:
                timestamp_str, incident_id, result_json_str = match_ack_result.groups()
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'incident_id': int(incident_id),
                    'result': result_json_str,
                    'log_type': 'crew_ack_result'
                })

            # Example: 2025-07-25 16:03:07,819 - INFO - 🤖 Crew execution completed with result: {"status": "escalated", "message": "Email sent to BAU successfully"}
            match_crew_result = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - 🤖 Crew execution completed with result: (.*)',
                line
            )
            if match_crew_result:
                timestamp_str, result_json_str = match_crew_result.groups()
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'result': result_json_str,
                    'log_type': 'crew_final_result'
                })

    return pd.DataFrame(data)


def parse_mcp_server_log(log_path):
    data = []
    if not os.path.exists(log_path):
        return pd.DataFrame(data)

    with open(log_path, 'r') as f:
        for line in f:
            # Example: 2025-07-25 16:03:07,819 - INFO - Fetching status for incident number: 227, Status: triggered
            match_get_status = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - Fetching status for incident number: (\d+), Status: (.*)',
                line
            )
            if match_get_status:
                timestamp_str, incident_id, status = match_get_status.groups()
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'incident_id': int(incident_id),
                    'status': status,
                    'log_type': 'mcp_get_status'
                })

            # Example: 2025-07-25 16:03:26,223 - INFO - AcknowledgeIncident args received: {'incident_number': '227', 'from_email': 'noc@infopro.com.my'}
            match_ack_args = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - AcknowledgeIncident args received: (.*)',
                line
            )
            if match_ack_args:
                timestamp_str, args_str = match_ack_args.groups()
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'args': args_str,
                    'log_type': 'mcp_ack_args'
                })

            # Example: 2025-07-25 16:03:27,932 - INFO - Incident 227 acknowledged successfully
            match_ack_success = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - Incident (\d+) acknowledged successfully',
                line
            )
            if match_ack_success:
                timestamp_str, incident_id = match_ack_success.groups()
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'incident_id': int(incident_id),
                    'log_type': 'mcp_ack_success'
                })

    return pd.DataFrame(data)


def parse_redis_client_log(log_path):
    data = []
    if not os.path.exists(log_path):
        return pd.DataFrame(data)

    with open(log_path, 'r') as f:
        for line in f:
            # Example: 2025-07-25 16:03:26,223 - DEBUG - Cache GET: key='incident:227' (HIT)
            match_cache_get = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - DEBUG - Cache GET: key=\'(.+?)\' \((HIT|MISS)\)',
                line
            )
            if match_cache_get:
                timestamp_str, key, hit_miss = match_cache_get.groups()
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'key': key,
                    'hit_miss': hit_miss,
                    'log_type': 'redis_cache_get'
                })

            # Example: 2025-07-25 16:03:07,819 - DEBUG - Cache SET: key='incident:227', ttl=300s
            match_cache_set = re.search(
                r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - DEBUG - Cache SET: key='(.+?)', ttl=(\d+)s",
                line
            )
            if match_cache_set:
                timestamp_str, key, ttl = match_cache_set.groups()
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'key': key,
                    'ttl': int(ttl),
                    'log_type': 'redis_cache_set'
                })

            # Example: 2025-07-25 16:03:27,932 - DEBUG - Cache DELETE: key='incident:227'
            match_cache_delete = re.search(
                r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - DEBUG - Cache DELETE: key='(.+?)'",
                line
            )
            if match_cache_delete:
                timestamp_str, key = match_cache_delete.groups()
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'key': key,
                    'log_type': 'redis_cache_delete'
                })

            # Example: 2025-07-25 16:03:27,932 - DEBUG - Redis SET ADD: set='scheduled_escalations', member='227'
            match_set_add = re.search(
                r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - DEBUG - Redis SET ADD: set='(.+?)', member='(.+?)'",
                line
            )
            if match_set_add:
                timestamp_str, set_name, member = match_set_add.groups()
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'set_name': set_name,
                    'member': member,
                    'log_type': 'redis_set_add'
                })

            # Example: 2025-07-25 16:03:27,932 - DEBUG - Redis SET REMOVE: set='scheduled_escalations', member='227'
            match_set_remove = re.search(
                r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - DEBUG - Redis SET REMOVE: set='(.+?)', member='(.+?)'",
                line
            )
            if match_set_remove:
                timestamp_str, set_name, member = match_set_remove.groups()
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'set_name': set_name,
                    'member': member,
                    'log_type': 'redis_set_remove'
                })

            # Example: 2025-07-25 16:03:26,223 - DEBUG - Redis SET IS_MEMBER: set='scheduled_escalations', member='227', result=True
            match_set_ismember = re.search(
                r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - DEBUG - Redis SET IS_MEMBER: set='(.+?)', member='(.+?)', result=(True|False)",
                line
            )
            if match_set_ismember:
                timestamp_str, set_name, member, result = match_set_ismember.groups()
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'set_name': set_name,
                    'member': member,
                    'result': result == 'True',
                    'log_type': 'redis_set_ismember'
                })

    return pd.DataFrame(data)


def parse_notify_log(log_path):
    data = []
    if not os.path.exists(log_path):
        return pd.DataFrame(data)

    with open(log_path, 'r') as f:
        for line in f:
            # Example: 2025-07-25 16:03:27,932 - INFO - Email notification sent successfully to 1 recipients
            match_email_sent = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - Email notification sent successfully to (\d+) recipients',
                line
            )
            if match_email_sent:
                timestamp_str, recipients_count = match_email_sent.groups()
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'recipients_count': int(recipients_count),
                    'log_type': 'notify_email_sent'
                })

            # Example: 2025-07-25 16:03:27,932 - INFO - Rocket.Chat webhook message sent successfully
            match_rc_sent = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - Rocket.Chat webhook message sent successfully',
                line
            )
            if match_rc_sent:
                timestamp_str = match_rc_sent.group(1)
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'log_type': 'notify_rocketchat_sent'
                })

            # Example: 2025-07-25 16:03:27,932 - ERROR - Failed to send notifications: Some error
            match_notify_error = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ERROR - Failed to send notifications: (.*)',
                line
            )
            if match_notify_error:
                timestamp_str, error_msg = match_notify_error.groups()
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'error_message': error_msg,
                    'log_type': 'notify_error'
                })

    return pd.DataFrame(data)


def parse_llm_log(log_path):
    data = []
    if not os.path.exists(log_path):
        return pd.DataFrame(data)

    with open(log_path, 'r') as f:
        for line in f:
            # Example: 2025-07-25 16:03:07,819 - INFO - Initializing LLM with config: model=ollama/mistral-small3.2:latest, base_url=http://10.10.6.8:11434, temperature=0.7
            match_llm_init = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - Initializing LLM with config: model=(.+?), base_url=(.+?), temperature=([\d.]+)',
                line
            )
            if match_llm_init:
                timestamp_str, model, base_url, temperature = match_llm_init.groups()
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'model': model,
                    'base_url': base_url,
                    'temperature': float(temperature),
                    'log_type': 'llm_init'
                })

    return pd.DataFrame(data)


def parse_webhook_receiver_log(log_path):
    data = []
    if not os.path.exists(log_path):
        return pd.DataFrame(data)

    with open(log_path, 'r') as f:
        for line in f:
            # Example: 2025-07-25 16:03:07,819 - INFO - Received webhook payload: { ... }
            match_received = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - Received webhook payload:',
                line
            )
            if match_received:
                timestamp_str = match_received.group(1)
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'log_type': 'webhook_received'
                })

            # Example: 2025-07-25 16:03:07,819 - INFO - Processed alert: { ... }
            match_processed = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - Processed alert:',
                line
            )
            if match_processed:
                timestamp_str = match_processed.group(1)
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'log_type': 'webhook_processed_alert'
                })

            # Example: 2025-07-25 16:03:07,819 - ERROR - Payload parsing error: ...
            match_error = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ERROR - (Payload parsing error|Processing error):',
                line
            )
            if match_error:
                timestamp_str, error_type = match_error.groups()
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'error_type': error_type,
                    'log_type': 'webhook_error'
                })

    return pd.DataFrame(data)


def parse_report_log(log_path):
    data = []
    if not os.path.exists(log_path):
        return pd.DataFrame(data)

    with open(log_path, 'r') as f:
        for line in f:
            # Example: 2025-07-25 16:03:07,819 - INFO - Starting morning shift report generation
            match_report_start = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - Starting (\w+) shift report generation',
                line
            )
            if match_report_start:
                timestamp_str, shift_type = match_report_start.groups()
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'shift_type': shift_type,
                    'log_type': 'report_generation_start'
                })

            # Example: 2025-07-25 16:03:07,819 - INFO - Kicking off AI crew for shift report
            match_crew_kickoff = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - Kicking off AI crew for shift report',
                line
            )
            if match_crew_kickoff:
                timestamp_str = match_crew_kickoff.group(1)
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'log_type': 'report_crew_kickoff'
                })

            # Example: 2025-07-25 16:03:07,819 - INFO - Shift report emailed to noramin@infopro.com.my
            match_email_sent = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - Shift report emailed to ',
                line
            )
            if match_email_sent:
                timestamp_str = match_email_sent.group(1)
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'log_type': 'report_email_sent'
                })

            # Example: 2025-07-25 16:03:07,819 - INFO - Report sent - Subject: ...
            match_report_sent = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - INFO - Report sent - Subject:',
                line
            )
            if match_report_sent:
                timestamp_str = match_report_sent.group(1)
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'log_type': 'report_sent_summary'
                })

            # Example: 2025-07-25 16:03:07,819 - ERROR - Report generation or notification failed: ...
            match_error = re.search(
                r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ERROR - Report generation or notification failed:',
                line
            )
            if match_error:
                timestamp_str = match_error.group(1)
                data.append({
                    'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f'),
                    'log_type': 'report_error'
                })

    return pd.DataFrame(data)


def generate_dashboard():
    all_data = []

    log_files = {
        'crew.log': parse_crew_log,
        'mcp_server.log': parse_mcp_server_log,
        'redis_client.log': parse_redis_client_log,
        'notify.log': parse_notify_log,
        'llm.log': parse_llm_log,
        'webhook_receiver.log': parse_webhook_receiver_log,
        'report.log': parse_report_log,
    }

    for log_file, parser in log_files.items():
        log_path = os.path.join(LOG_DIR, log_file)
        df = parser(log_path)
        if not df.empty:
            all_data.append(df)

    if not all_data:
        print("No log data found to generate dashboard.")
        return

    combined_df = pd.concat(all_data, ignore_index=True)
    combined_df = combined_df.sort_values(by='timestamp').reset_index(drop=True)

    # --- Create Dashboard ---
    fig = make_subplots(
        rows=6, cols=2,
        specs=[
            [{"colspan": 2}, None],           # row 1: full-width histogram
            [{"type": "domain"}, {"type": "xy"}],  # row 2: pie + bar
            [{"type": "domain"}, {"type": "xy"}],  # row 3: pie + bar
            [{"type": "xy"}, {"type": "xy"}],      # row 4: two bars
            [{"type": "xy"}, {"type": "xy"}],      # row 5: two bars
            [{"type": "xy"}, {"type": "domain"}]   # row 6: bar + indicator
        ],
        subplot_titles=(
            "CrewAI Pipeline Duration Distribution",
            "Redis Cache Hit/Miss Ratio", "Redis Cache Operations",
            "Incident Outcomes", "Notification Status",
            "MCP Server Tool Calls", "Webhook Receiver Activity",
            "Report Generation Activity", "LLM Initializations"
        )
    )

    # 1. Pipeline Duration
    durations = combined_df[combined_df['log_type'] == 'crew_pipeline_finish']['duration']
    if len(durations) > 0:
        fig.add_trace(go.Histogram(x=durations, name="Duration"), row=1, col=1)
        fig.update_xaxes(title_text="Duration (s)", row=1, col=1)
        fig.update_yaxes(title_text="Count", row=1, col=1)

    # 2. Cache Hit/Miss
    cache_gets = combined_df[combined_df['log_type'] == 'redis_cache_get']
    if not cache_gets.empty:
        counts = cache_gets['hit_miss'].value_counts()
        fig.add_trace(go.Pie(labels=counts.index, values=counts.values), row=2, col=1)

    # 3. Redis Ops
    redis_ops = combined_df[combined_df['log_type'].str.startswith('redis_')]
    if not redis_ops.empty:
        counts = redis_ops['log_type'].value_counts()
        fig.add_trace(go.Bar(x=counts.index, y=counts.values), row=2, col=2)
        fig.update_xaxes(title_text="Operation", row=2, col=2)
        fig.update_yaxes(title_text="Count", row=2, col=2)

    # 4. Incident Outcomes
    results = combined_df[combined_df['log_type'] == 'crew_final_result']
    if not results.empty:
        statuses = []
        for res_str in results['result']:
            try:
                status = json.loads(res_str).get('status', 'unknown')
            except:
                status = 'parse_error'
            statuses.append(status)
        counts = pd.Series(statuses).value_counts()
        fig.add_trace(go.Pie(labels=counts.index, values=counts.values), row=3, col=1)

    # 5. Notifications
    notifies = combined_df[combined_df['log_type'].str.startswith('notify_')]
    if not notifies.empty:
        counts = notifies['log_type'].value_counts()
        fig.add_trace(go.Bar(x=counts.index, y=counts.values), row=3, col=2)
        fig.update_xaxes(title_text="Type", row=3, col=2)
        fig.update_yaxes(title_text="Count", row=3, col=2)

    # 6. MCP Calls
    mcp = combined_df[combined_df['log_type'].str.startswith('mcp_')]
    if not mcp.empty:
        counts = mcp['log_type'].value_counts()
        fig.add_trace(go.Bar(x=counts.index, y=counts.values), row=4, col=1)
        fig.update_xaxes(title_text="Call Type", row=4, col=1)
        fig.update_yaxes(title_text="Count", row=4, col=1)

    # 7. Webhook Activity
    webhook = combined_df[combined_df['log_type'].str.startswith('webhook_')]
    if not webhook.empty:
        counts = webhook['log_type'].value_counts()
        fig.add_trace(go.Bar(x=counts.index, y=counts.values), row=4, col=2)
        fig.update_xaxes(title_text="Event Type", row=4, col=2)
        fig.update_yaxes(title_text="Count", row=4, col=2)

    # 8. Report Activity
    report = combined_df[combined_df['log_type'].str.startswith('report_')]
    if not report.empty:
        counts = report['log_type'].value_counts()
        fig.add_trace(go.Bar(x=counts.index, y=counts.values), row=5, col=1)
        fig.update_xaxes(title_text="Event Type", row=5, col=1)
        fig.update_yaxes(title_text="Count", row=5, col=1)

    # 9. LLM Initializations
    llm = combined_df[combined_df['log_type'] == 'llm_init']
    if not llm.empty:
        fig.add_trace(go.Indicator(
            mode="number",
            value=len(llm),
            title={"text": "LLM Inits"}
        ), row=6, col=2)

    fig.update_layout(
        title_text="CrewAI Performance Dashboard",
        height=1800,
        showlegend=False
    )

    output_path = os.path.join(os.path.dirname(__file__), 'crewai_performance_dashboard.html')
    fig.write_html(output_path)
    print(f"Dashboard generated successfully at: {output_path}")
    print("Open this file in your browser to view.")


if __name__ == "__main__":
    try:
        import pandas as pd
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        print("Install required packages: pip install pandas plotly")
        exit(1)

    generate_dashboard()