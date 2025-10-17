
# src/msteamdev/tools/otobo_server.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import requests
import logging
from datetime import datetime
from typing import Optional, Dict, Any

# --- Configuration & Logging ---

app = FastAPI(title="Otobo MCP Server (Generic Interface)")
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Environment Variables based on otoboapi.txt ---
OTOBO_BASE_URL = os.getenv("OTOBO_BASE_URL", "http://10.10.6.163")
OTOBO_WEBSERVICE_PATH = os.getenv("OTOBO_WEBSERVICE_PATH", "/otobo/nph-genericinterface.pl/Webservice/")
OTOBO_WEBSERVICE_NAME = os.getenv("OTOBO_WEBSERVICE_NAME", "crewai")
OTOBO_USER_LOGIN = os.getenv("OTOBO_USER_LOGIN", "crewai")
OTOBO_PASSWORD = os.getenv("OTOBO_PASSWORD", "MyFirstPwd12")

# Ticket Defaults
OTOBO_DEFAULT_QUEUE = os.getenv("OTOBO_DEFAULT_QUEUE", "Managed_Service")
OTOBO_DEFAULT_TYPE = os.getenv("OTOBO_DEFAULT_TYPE", "Incident")
OTOBO_DEFAULT_PRIORITY = os.getenv("OTOBO_DEFAULT_PRIORITY", "4 high")
OTOBO_DEFAULT_OWNER = os.getenv("OTOBO_DEFAULT_OWNER", "noc")
OTOBO_DEFAULT_CUSTOMER_USER = os.getenv("OTOBO_DEFAULT_CUSTOMER_USER", "rfc")


# --- Otobo API Client Logic (Refactored for Generic Interface) ---

class OtoboGenericClient:
    """A client for Otobo's Generic Interface, matching the user's example."""
    def __init__(self, base_url: str, webservice_path: str, webservice_name: str, user_login: str, password: str):
        if not all([base_url, webservice_path, webservice_name, user_login, password]):
            raise ValueError("All Otobo Generic Interface parameters must be set.")
        self.base_url = base_url.rstrip('/')
        self.webservice_path = webservice_path
        self.webservice_name = webservice_name
        self.user_login = user_login
        self.password = password
        self.session = requests.Session()

    def _make_request(self, operation: str, payload: dict) -> dict:
        """Helper to construct and send requests to the Generic Interface."""
        endpoint = f"{self.base_url}{self.webservice_path}{self.webservice_name}/{operation}"
        try:
            logger.info(f"Sending request to Otobo endpoint: {endpoint}")
            logger.debug(f"Request payload: {payload}")
            response = self.session.post(endpoint, json=payload, timeout=20)
            response.raise_for_status()
            
            response_data = response.json()
            if "Error" in response_data:
                error_msg = response_data["Error"].get("ErrorMessage", "Unknown Otobo error")
                logger.error(f"Otobo API returned an error: {error_msg}")
                raise HTTPException(status_code=400, detail=f"Otobo Error: {error_msg}")

            logger.info(f"Successfully executed Otobo operation '{operation}'.")
            return response_data
        except requests.RequestException as e:
            logger.error(f"Error communicating with Otobo Generic Interface: {e}")
            raise HTTPException(status_code=502, detail=f"Failed to communicate with Otobo API: {e}")

    def create_ticket(self, title: str, body: str, subject: Optional[str] = None) -> dict:
        """Creates a new ticket in Otobo using the specified format."""
        payload = {
            "UserLogin": self.user_login,
            "Password": self.password,
            "Ticket": {
                "Title": title,
                "Queue": OTOBO_DEFAULT_QUEUE,
                "Lock": "unlock",
                "Type": OTOBO_DEFAULT_TYPE,
                "State": "new",
                "Priority": OTOBO_DEFAULT_PRIORITY,
                "Owner": OTOBO_DEFAULT_OWNER,
                "CustomerUser": OTOBO_DEFAULT_CUSTOMER_USER
            },
            "Article": {
                "Subject": subject or title,
                "Body": body,
                "ContentType": "text/plain; charset=utf8"
            }
        }
        return self._make_request("create", payload)

    def update_ticket(self, ticket_id: str, article_body: str, article_subject: Optional[str] = None, ticket_properties: Optional[Dict[str, Any]] = None) -> dict:
        """Updates an existing ticket and adds an article."""
        payload = {
            "UserLogin": self.user_login,
            "Password": self.password,
            "TicketID": ticket_id,
            "Ticket": {
                "State": "in progress"
            },
            "Article": {
                "Subject": article_subject or f"Update for ticket",
                "Body": article_body,
                "ContentType": "text/plain; charset=utf8"
            }
        }
        if ticket_properties: # Only add Ticket key if properties are provided
            payload["Ticket"] = ticket_properties
        return self._make_request("update", payload)

    def resolve_ticket(self, ticket_id: str, article_body: str, article_subject: Optional[str] = "Ticket Resolved") -> dict:
        """Resolves a ticket by setting its state to 'closed successful' and adding a final article."""
        payload = {
            "UserLogin": self.user_login,
            "Password": self.password,
            "TicketID": ticket_id,
            "Ticket": {
                "State": "closed successful"
            },
            "Article": {
                "Subject": article_subject,
                "Body": article_body,
                "ContentType": "text/plain; charset=utf8"
            }
        }
        return self._make_request("resolved", payload)


# --- API Models ---

class CreateTicketRequest(BaseModel):
    title: str
    body: str
    subject: Optional[str] = None

class UpdateTicketRequest(BaseModel):
    ticket_id: str
    body: str
    subject: Optional[str] = None
    ticket_properties: Optional[Dict[str, Any]] = None

class ResolveTicketRequest(BaseModel):
    ticket_id: str
    body: str
    subject: Optional[str] = "Incident Resolved"


# --- FastAPI Endpoints ---

@app.on_event("startup")
def startup_event():
    logger.info("Starting Otobo MCP Server (Generic Interface)...")
    if not all([OTOBO_BASE_URL, OTOBO_USER_LOGIN, OTOBO_PASSWORD]):
        logger.critical("Otobo environment variables (OTOBO_BASE_URL, OTOBO_USER_LOGIN, OTOBO_PASSWORD) must be set.")
    else:
        logger.info("Otobo server configured.")

def get_client():
    """Helper function to instantiate the client."""
    return OtoboGenericClient(
        base_url=OTOBO_BASE_URL,
        webservice_path=OTOBO_WEBSERVICE_PATH,
        webservice_name=OTOBO_WEBSERVICE_NAME,
        user_login=OTOBO_USER_LOGIN,
        password=OTOBO_PASSWORD
    )

@app.post("/create_ticket")
async def handle_create_ticket(request: CreateTicketRequest):
    client = get_client()
    ticket_data = client.create_ticket(title=request.title, body=request.body, subject=request.subject)
    return {"status": "success", "ticket_data": ticket_data}

@app.post("/update_ticket")
async def handle_update_ticket(request: UpdateTicketRequest):
    client = get_client()
    update_data = client.update_ticket(
        ticket_id=request.ticket_id,
        article_body=request.body,
        article_subject=request.subject,
        ticket_properties=request.ticket_properties
    )
    return {"status": "success", "update_data": update_data}

@app.post("/resolve_ticket")
async def handle_resolve_ticket(request: ResolveTicketRequest):
    client = get_client()
    resolve_data = client.resolve_ticket(
        ticket_id=request.ticket_id,
        article_body=request.body,
        article_subject=request.subject
    )
    return {"status": "success", "resolve_data": resolve_data}

@app.get("/health")
async def health_check():
    return {"name": "otobo-mcp-server-generic", "status": "healthy", "timestamp": datetime.utcnow().isoformat()}
