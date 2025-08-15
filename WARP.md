# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

**msteamdev** is an intelligent IT alert management system powered by CrewAI that automates PagerDuty incident processing. It uses multi-agent AI collaboration to analyze, acknowledge, and escalate alerts while generating comprehensive shift reports.

### Key Capabilities
- **Automated PagerDuty Integration**: Receives webhooks, automatically acknowledges incidents, and manages status updates
- **AI-Driven Escalation Decisions**: Uses specialized agents to analyze alert patterns and make intelligent escalation choices
- **Multi-Channel Notifications**: Sends alerts via email and Rocket.Chat with actionable insights
- **Performance Monitoring**: Tracks processing metrics and system health via Redis caching layer
- **Daily/Weekly Reporting**: Generates detailed shift reports with escalation analysis

## Architecture Overview

### Core Components

**Webhook Receiver** (`webhook_receiver.py`)
- FastAPI application listening for PagerDuty webhooks
- Entry point that triggers the alert processing pipeline
- Logs all incoming alerts to structured JSON format

**CrewAI Engine** (`crew.py`)
- Multi-agent orchestration system with specialized roles:
  - `escalation_checker`: Analyzes alerts and decides on escalation
  - `communicator`: Crafts professional notification messages  
  - `action_recommender`: Generates technical remediation steps
  - `pagerduty_manager`: Handles API interactions with PagerDuty
  - `reporter`: Creates shift reports and trend analysis

**Model Context Protocol (MCP) Server** (`tools/mcp_server.py`)
- Provides structured interface between AI agents and PagerDuty API
- Redis-cached layer for performance optimization
- Handles incident status checks and acknowledgments

**Enhanced Tools System** (`tools/enhanced_tools.py`)
- Advanced analytics tools with metrics tracking
- Trend analysis and pattern recognition
- System health monitoring capabilities

**Notification System** (`tools/notify.py`)
- Multi-channel alert delivery (email + Rocket.Chat)
- Template-based message formatting
- Error handling and retry logic

**Alert Store** (`tools/alert_store.py`)
- JSON-based persistent storage for all alerts
- Escalation eligibility checking against business rules
- Historical analysis and pattern matching

### Data Flow
1. **Ingestion**: PagerDuty → Webhook → Alert Store
2. **Processing**: Background thread → Agent analysis → Escalation decision
3. **Action**: Auto-acknowledge + Notification (if escalated)
4. **Reporting**: Scheduled shift reports via dedicated agents

## Development Commands

### Environment Setup
```bash
# Install UV package manager (if not already installed)
pip install uv

# Install project dependencies
crewai install
# OR manually with:
uv sync

# Set up environment variables
cp .env.example .env  # Configure PagerDuty API keys, SMTP, etc.
```

### Core Development Tasks

**Run the main application**
```bash
# Start webhook receiver (production)
uvicorn src.msteamdev.webhook_receiver:app --host 0.0.0.0 --port 8000

# Start MCP server (required for agent tools)
python src/msteamdev/tools/mcp_server.py

# Run crew pipeline directly (testing)
crewai run
# OR using project scripts:
python -m msteamdev.main run
```

**Testing**
```bash
# Run enhanced integration tests
python test_enhanced_integration.py

# Run pytest-based tests
pytest test_enhanced_pytest.py -v

# Test single components
python src/msteamdev/tools/test-notify.py
python src/msteamdev/daily_report.py --shift morning
```

**Generate Reports**
```bash
# Generate shift reports
python src/msteamdev/daily_report.py --shift morning
python src/msteamdev/daily_report.py --shift evening
python src/msteamdev/daily_report.py --shift weekly
```

**Development Scripts**
```bash
# Available via pyproject.toml scripts:
msteam          # Run main application
run_crew        # Execute crew pipeline
train           # Train crew models
replay          # Replay previous executions
test            # Run tests
```

### Configuration Management

**Agent Configuration** (`src/msteamdev/config/agents_enhanced.yaml`)
- Defines AI agent roles, goals, and capabilities
- Tool assignment for each agent type
- LLM configuration and memory settings

**Task Definitions** (`src/msteamdev/config/tasks_enhanced.yaml`)
- Structured task templates for each agent
- Expected output formats and validation
- Context passing between agents

**Key Environment Variables**
- `PAGERDUTY_API_TOKEN`: PagerDuty API access
- `OPENAI_API_KEY`: LLM provider credentials
- `MCP_SERVER_URL`: Internal tool server endpoint (default: localhost:6006)
- `ESCALATION_DELAY_MINUTES`: Wait time before escalation analysis (default: 3)
- `ACKNOWLEDGMENT_DELAY_MINUTES`: Auto-ack delay (default: 1)
- `SMTP_*`: Email notification configuration
- `ROCKETCHAT_WEBHOOK_*`: Rocket.Chat integration

## Working with the Codebase

### Adding New Agents
1. Define agent in `agents_enhanced.yaml` with role, goal, and backstory
2. Create corresponding task templates in `tasks_enhanced.yaml`
3. Update `load_agents()` in `crew.py` to assign appropriate tools
4. Add agent to relevant pipelines

### Creating New Tools
1. Extend `tools/enhanced_tools.py` or create new tool modules
2. Register tools in MCP server (`tools/mcp_server.py`) if needed
3. Update agent configurations to include new tools
4. Add tool testing to integration test suites

### Modifying Alert Processing Logic
- Core pipeline: `crew.py:run_escalation_pipeline()`
- Escalation rules: `tools/alert_store.py:check_escalation_eligibility()`
- Notification logic: `tools/notify.py`
- Performance tracking: Automatic via `CrewPerformanceMonitor`

### Performance Monitoring
- System health endpoint: `crew.py:get_system_health()`
- Tool metrics: Automatic tracking via `enhanced_tools.py`
- Redis caching: Configured in `tools/redis_client.py`
- Log analysis: Structured logging to `log/` directory

### Database Schema
The system uses file-based JSON storage:
- `alert_log.json`: All incoming alerts (append-only)
- `escalation_log.json`: Escalation decisions and outcomes
- Redis: Transient caching and deduplication

## Troubleshooting

**Common Issues**
- MCP server connection failures → Check server startup and port availability
- Agent tool access errors → Verify tool registration in `load_agents()`
- PagerDuty API timeouts → Check network connectivity and API token validity
- Redis connection issues → Ensure Redis server is running for caching

**Test-Specific Issues**
- `TypeError: object str can't be used in 'await' expression` → Use tool `._run()` method instead of awaiting
- `RuntimeWarning: coroutine was never awaited` → Mixed async/sync function calls, ensure proper event loop handling
- `Event loop is closed` errors → Redis client issues in test environment, restart test session
- JSON decode errors in tests → Tools return error strings when underlying services unavailable

**Production Issues**
- `Event loop is closed` in Redis operations → Background threads trying to use closed loop, restart service
- `cache_set() got unexpected keyword argument 'ttl'` → Use `ttl_seconds` parameter instead
- `pdpyras deprecation warnings` → Migrate to `pagerduty` library per migration guide

**Performance Optimization**
- Agent caching is enabled (5-minute cache timeout)
- Redis caching reduces PagerDuty API calls
- Background processing prevents webhook blocking
- Metrics tracking identifies bottlenecks

**Log Locations**
- `log/crew.log`: Main application logs
- `log/mcp_server.log`: Tool server logs  
- `log/report.log`: Reporting system logs
- Console output: Tee'd to both stdout and log files
