import pytest
import asyncio
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
import json
import os
import time

# Import the FastAPI app and Redis client functions
from msteamdev.webhook_receiver import app
from msteamdev.tools.redis_client import cache_get, cache_set, cache_delete, get_redis_client

# Set up environment variables for testing
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "6379"
os.environ["OTOBO_SERVER_URL"] = "http://mock-otobo:7007"
os.environ["ESCALATION_DELAY_MINUTES"] = "0" # For faster testing
os.environ["ACKNOWLEDGMENT_DELAY_MINUTES"] = "0" # For faster testing

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest.fixture(scope="function", autouse=True)
async def clear_redis_cache():
    """Fixture to clear Redis cache before each test."""
    redis_client = get_redis_client()
    if redis_client:
        redis_client.flushdb()
    yield
    if redis_client:
        redis_client.flushdb()

@pytest.fixture
async def client():
    """Async test client for the FastAPI app."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
def mock_otobo_create_ticket_success():
    """Mocks the Otobo /create_ticket endpoint to always succeed."""
    with patch("requests.post") as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ticket_data": {"TicketID": "12345", "TicketNumber": "OTRS-12345"}}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        yield mock_post

@pytest.fixture
def mock_otobo_update_ticket_success():
    """Mocks the Otobo /update_ticket endpoint to always succeed."""
    with patch("requests.post") as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        yield mock_post

@pytest.fixture
def mock_start_alert_pipeline():
    """Mocks the start_alert_pipeline to prevent actual crewAI execution during webhook tests."""
    with patch("msteamdev.webhook_receiver.start_alert_pipeline", new_callable=AsyncMock) as mock_pipeline:
        mock_pipeline.return_value = {"status": "mocked_processing_started"}
        yield mock_pipeline

class TestWebhookConcurrency:
    async def test_concurrent_triggered_alerts_otobo_race_condition(
        self, client, mock_otobo_create_ticket_success, mock_start_alert_pipeline
    ):
        incident_number = "INC001"
        alert_payload = {
            "event": {
                "event_type": "incident.triggered",
                "data": {
                    "id": "P12345",
                    "incident_number": incident_number,
                    "title": "Test Alert",
                    "severity": "critical",
                    "status": "triggered",
                    "timestamp": "2025-10-16T10:00:00Z",
                    "from_email": "test@example.com"
                }
            }
        }

        # Simulate multiple concurrent webhook calls
        num_concurrent_calls = 5
        tasks = [
            client.post("/pagerduty", content=json.dumps(alert_payload), headers={"Content-Type": "application/json"})
            for _ in range(num_concurrent_calls)
        ]
        responses = await asyncio.gather(*tasks)

        # Assert that only one Otobo ticket creation request was made
        # The mock_otobo_create_ticket_success fixture patches requests.post globally.
        # We need to check how many times it was called with the /create_ticket URL.
        create_ticket_calls = [
            call for call in mock_otobo_create_ticket_success.call_args_list
            if f"{os.getenv('OTOBO_SERVER_URL')}/create_ticket" in call.args[0]
        ]
        assert len(create_ticket_calls) == 1, "Only one Otobo ticket should be created"

        # Assert that the Redis cache contains the ticket ID
        ticket_id = cache_get(f"otobo_ticket:{incident_number}")
        assert ticket_id == "12345", "Otobo ticket ID should be cached"

        # Assert that start_alert_pipeline was called once
        assert mock_start_alert_pipeline.call_count == 1, "start_alert_pipeline should be called once"

        # Check responses
        for response in responses:
            assert response.status_code == 200
            response_json = response.json()
            assert response_json["status"] in ["received", "processing_started"] # The first one will be "received", subsequent ones might be "processing_started" from the mock
