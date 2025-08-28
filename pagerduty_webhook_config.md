# PagerDuty Webhook v3 Configuration

## **Key Webhook Events for NOC Notes**

### **Primary Event: `incident.annotated`**
This is the **KEY EVENT** that triggers when NOC adds notes to incidents.

### **Required Webhook Configuration**

#### **1. Event Types to Enable**
```json
{
  "webhook": {
    "endpoint_url": "https://your-server.com/webhook",
    "type": "webhook_v3",
    "event_types": [
      "incident.triggered",    // When alerts first come in
      "incident.annotated",    // 🎯 CRITICAL: When NOC adds notes
      "incident.acknowledged", // When someone acknowledges
      "incident.resolved",     // When incident is resolved
      "incident.reopened"      // If incident reopens
    ]
  }
}
```

#### **2. PagerDuty API Configuration Steps**

**Step 1: Create Webhook Extension**
```bash
curl -X POST "https://api.pagerduty.com/extensions" \
  -H "Accept: application/vnd.pagerduty+json;version=2" \
  -H "Authorization: Token token=YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "extension": {
      "name": "CrewAI Knowledge System",
      "endpoint_url": "https://your-server.com/webhook",
      "extension_schema": {
        "id": "PJ88MKS",
        "type": "extension_schema_reference"
      },
      "extension_objects": [
        {
          "id": "YOUR_SERVICE_ID",
          "type": "service_reference"
        }
      ]
    }
  }'
```

**Step 2: Enable Webhook v3 Events**
In PagerDuty UI:
1. Go to **Integrations → Generic Webhooks**
2. Create new webhook or edit existing
3. Set **Webhook URL**: `https://your-server.com/webhook`
4. **Event Types** - Enable these:
   - ✅ `incident.triggered`
   - ✅ `incident.annotated` ← **MOST IMPORTANT**
   - ✅ `incident.acknowledged`
   - ✅ `incident.resolved`

## **Webhook v3 Event Structure**

### **incident.annotated Event** (When NOC adds notes)
```json
{
  "event": {
    "id": "01234567-89ab-cdef-0123-456789abcdef",
    "event_type": "incident.annotated",
    "resource_type": "incident",
    "occurred_at": "2024-01-15T12:00:00Z",
    "agent": {
      "html_url": "https://example.pagerduty.com/users/P123ABC",
      "id": "P123ABC",
      "self": "https://api.pagerduty.com/users/P123ABC",
      "summary": "NOC Engineer",
      "type": "user_reference"
    },
    "data": {
      "id": "P1DTXQR",
      "type": "incident",
      "self": "https://api.pagerduty.com/incidents/P1DTXQR",
      "html_url": "https://example.pagerduty.com/incidents/P1DTXQR",
      "incident_number": 12345,
      "title": "High CPU Usage on web-server-01",
      "description": "CPU usage has exceeded 90% for more than 5 minutes",
      "status": "triggered",
      "service": {
        "id": "P1DTXSR",
        "type": "service_reference",
        "summary": "Web Service"
      },
      "urgency": "high",
      "priority": {
        "id": "P53ZZH5",
        "type": "priority_reference", 
        "summary": "P2"
      },
      "created_at": "2024-01-15T11:45:00Z",
      "notes": [
        {
          "id": "P1NOTE1",
          "content": "Root cause: Weekly batch job causing CPU spike. Customer confirms this is expected processing until Friday.",
          "created_at": "2024-01-15T12:00:00Z",
          "user": {
            "id": "P123ABC",
            "type": "user_reference",
            "summary": "NOC Engineer"
          }
        }
      ]
    }
  }
}
```

### **incident.triggered Event** (Initial alerts)
```json
{
  "event": {
    "event_type": "incident.triggered",
    "data": {
      "id": "P1DTXQR",
      "incident_number": 12345,
      "title": "High CPU Usage on web-server-01",
      "status": "triggered",
      "urgency": "high",
      "service": {
        "summary": "Web Service"
      },
      "created_at": "2024-01-15T11:45:00Z"
    }
  }
}
```

## **Testing Webhook Configuration**

### **Test 1: Verify webhook is receiving events**
```bash
# Check your webhook logs
tail -f /var/log/your-app.log | grep "Received webhook"
```

### **Test 2: Trigger an annotation event**
1. Go to PagerDuty incident
2. Add a note: "Test note - root cause: testing webhook"
3. Check if your webhook receives `incident.annotated` event

### **Test 3: Validate knowledge storage**
```bash
# Check if knowledge is being stored
cat /home/crewai/msteamdev/knowledge/incident_knowledge.json | jq .
```

## **Webhook Security**

### **Option 1: Webhook Signature Verification**
```python
import hmac
import hashlib

def verify_webhook_signature(payload: str, signature: str, secret: str) -> bool:
    """Verify PagerDuty webhook signature"""
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(f"v1={expected_signature}", signature)

@app.post("/webhook")
async def pagerduty_webhook_v3(request: Request):
    """Secure webhook with signature verification"""
    body = await request.body()
    signature = request.headers.get("X-PagerDuty-Signature")
    
    if not verify_webhook_signature(body.decode(), signature, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    webhook_data = json.loads(body)
    # ... rest of webhook processing
```

### **Option 2: IP Allowlist**
```python
PAGERDUTY_IPS = [
    "54.175.103.27",
    "54.175.103.28", 
    "54.175.242.40",
    "54.89.99.203"
]

@app.middleware("http")
async def verify_pagerduty_ip(request: Request, call_next):
    if request.url.path == "/webhook":
        client_ip = request.client.host
        if client_ip not in PAGERDUTY_IPS:
            raise HTTPException(status_code=403, detail="Forbidden")
    
    response = await call_next(request)
    return response
```

## **Knowledge Folder Structure**

Your CrewAI knowledge folder will look like:
```
/home/crewai/msteamdev/knowledge/
├── incident_knowledge.json      # Individual incident details
├── alert_patterns.json          # Service-level patterns  
├── business_context.json        # Business rules and context
└── resolved_incidents.json      # Historical resolutions
```

### **incident_knowledge.json Structure**
```json
{
  "12345": {
    "incident_number": "12345",
    "title": "High CPU Usage on web-server-01",
    "service": "Web Service", 
    "urgency": "high",
    "notes": [
      {
        "content": "Root cause: Weekly batch job...",
        "created_by": "NOC Engineer",
        "created_at": "2024-01-15T12:00:00Z"
      }
    ],
    "knowledge_updates": [
      {
        "type": "root_cause", 
        "content": "Weekly batch job causing CPU spike"
      }
    ],
    "summary": {
      "root_cause": "Weekly batch job causing CPU spike",
      "planned_maintenance": true,
      "false_positive": false
    }
  }
}
```

## **Deployment Checklist**

### **✅ PagerDuty Configuration**
- [ ] Webhook created with correct endpoint
- [ ] `incident.annotated` event enabled
- [ ] Test webhook receives events
- [ ] Webhook signature/IP security configured

### **✅ Server Configuration**  
- [ ] Webhook endpoint deployed
- [ ] CrewAI knowledge folder created
- [ ] File permissions correct
- [ ] Logging configured

### **✅ Testing**
- [ ] Add test note in PagerDuty
- [ ] Verify webhook receives `incident.annotated`
- [ ] Check knowledge files are created
- [ ] Verify AI agents can read knowledge

### **✅ NOC Training**
- [ ] Show team how to add structured notes
- [ ] Explain keyword patterns
- [ ] Demo knowledge accumulation

**Once configured, every note your NOC team adds in PagerDuty will automatically enhance your AI's intelligence!**