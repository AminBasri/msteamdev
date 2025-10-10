# Otobo Ticket Flow Integration with PagerDuty and CrewAI

## Overview

This document defines the **ticket flow and state transitions** between **PagerDuty**, **CrewAI**, and **Otobo**.  
It ensures consistent ticket management, proper synchronization of alerts, and clear handling of escalation and resolution cases.

---

## 1. Objective

To automate ticket lifecycle management in **Otobo** based on events received from **PagerDuty** and analysis results from **CrewAI**, maintaining real-time state alignment and preventing premature closure or duplication.

---

## 2. Otobo Available States

| Name | Type | Description |
|------|------|-------------|
| new | new | Newly created ticket |
| open | open | Active open tickets |
| in progress | open | Ticket under investigation or escalation |
| pending auto close+ | pending auto | Waiting for auto-close (positive outcome) |
| pending auto close- | pending auto | Waiting for auto-close (negative outcome) |
| pending reminder | pending reminder | Waiting for NOC or user input |
| closed successful | closed | Ticket closed successfully |
| closed unsuccessful | closed | Ticket closed unsuccessfully |
| closed with workaround | closed | Ticket closed with workaround |
| merged | merged | Ticket merged with another |
| removed | removed | Customer removed |

---

## 3. Integration Flow

### **Step 1: Alert Triggered in PagerDuty**
- **Event:** New alert created in PagerDuty.
- **Action:**  
  - Create a new ticket in Otobo.
  - **Otobo State:** `new`
  - **Comment:** “New alert received from PagerDuty (Incident ID: <ID>).”
- **Rule:**  
  - If an existing ticket for the same PD Incident ID exists and is not closed, do **not** create a new ticket.

---

### **Step 2: Alert Acknowledged in PagerDuty**
- **Event:** PD incident acknowledged.
- **Action:**  
  - Update existing Otobo ticket.
  - **State:** `in progress`
  - **Comment:** “Alert acknowledged in PagerDuty by <user>.”
- **Rule:**  
  - Only transition to `in progress` if current state is `new`.

---

### **Step 3: CrewAI Escalation Decision**
- **Event:** CrewAI determines escalation is needed.
- **Action:**  
  - Keep **state = in progress**.
  - Add internal note: “CrewAI escalated incident to <customer/team> due to <reason>.”
- **Rule:**  
  - If escalation occurs before acknowledgment, still transition to `in progress`.

---

### **Step 4: PagerDuty Note Added (NOC or System)**
- **Event:** PD note added.
- **Action:**  
  - Sync note into Otobo as **internal note**.
  - If incident was **not escalated**, prepare for closure transition.
- **Rule:**  
  - If alert was escalated, remain `in progress` until resolution confirmation.

---

### **Step 5: CrewAI Determines No Escalation (Auto Close Flow)**
- **Condition:** No escalation needed, alert stable.
- **Action:**  
  - **State:** `pending auto close+`
  - **Comment:** “Auto-close pending confirmation (no escalation required).”
  - **Timer:** After X minutes (e.g., 10–15 mins) of no updates, automatically close.
- **Next State:** `closed successful`

---

### **Step 6: Alert Escalated (Keep Active)**
- **Condition:** Alert escalated or unresolved.
- **Action:**  
  - Keep **state = in progress**.
  - Add note: “Escalation in progress – awaiting resolution.”
- **Rule:**  
  - Do not auto-close until PD incident resolved **and** NOC note confirmed.

---

### **Step 7: PagerDuty Incident Resolved**
- **Event:** PD incident resolved.
- **Action:**  
  - If ticket in:
    - `new` or `pending auto close+` → change to `closed successful`
    - `in progress` (escalated) → remain open until manual close.
- **Rule:**  
  - PD “resolved” event never auto-closes an escalated ticket.

---

### **Step 8: Manual Closure by NOC**
- **Event:** NOC or L2 manually closes ticket.
- **Action:**  
  - **State:** `closed successful` or `closed with workaround`
  - **Comment:** “Closed manually by NOC — reason: <details>.”
  - Sync PD note: “Incident closed manually in Otobo by <user>.”

---

### **Step 9: Auto-Close Failure or Timeout**
- **Condition:** Ticket not closed within auto-close window or failed resolution.
- **Action:**  
  - **State:** `closed unsuccessful`
  - **Comment:** “Auto-close after timeout — unresolved confirmation.”

---

### **Step 10: Re-Triggered Alert Handling**
- **Event:** PD incident re-triggered (same fingerprint or ID).
- **Action:**  
  - If existing Otobo ticket found in `closed successful` or `closed with workaround`:  
    - Reopen ticket (`open`)
    - Add note: “Alert re-triggered in PagerDuty.”

---

## 4. Summary of Best-Matched Otobo States

| Flow Stage | Otobo State | Description |
|-------------|-------------|-------------|
| PD trigger | new | Ticket created from PD alert |
| PD acknowledged | in progress | Alert being handled |
| CrewAI escalation | in progress | Escalation in progress |
| No escalation (waiting) | pending auto close+ | Awaiting auto-close |
| Auto close success | closed successful | Automatically resolved |
| Manual close | closed successful / closed with workaround | NOC closure |
| Timeout / failed handling | closed unsuccessful | Failed resolution |
| PD re-trigger | open | Reopened ticket |

---

## 5. Additional Use Cases

### **Use Case 1: Delayed PD Notes**
If PD alert resolves quickly (e.g., 5 mins) but NOC note arrives late:
- Keep ticket `in progress` until note syncs.
- After note received, if PD incident resolved → move to `pending auto close+`.

✅ Prevents premature closure and maintains audit integrity.

---

### **Use Case 2: PD Escalation to Secondary Team**
- When PD escalates to another escalation policy/team:
  - Update Otobo owner/group accordingly.
  - Add escalation reason and timestamp.

---

### **Use Case 3: CrewAI Auto-Resolution Confidence**
- If CrewAI detects recovery/self-healing:
  - Add note: “CrewAI auto-resolved due to recovery detection.”
  - Transition to `pending auto close+` with a shorter delay (e.g., 3 mins).

---

### **Use Case 4: Communication Loopback**
- If ticket updated manually in Otobo (status or note):
  - Send webhook back to PagerDuty to add note or update status for consistency.

---

## 6. Automation Logic (Recommended Implementation)

| Component | Role | Description |
|------------|------|-------------|
| **CrewAI Webhook Orchestrator** | Middleware | Receives PagerDuty webhooks, interprets data, and triggers Otobo API updates |
| **Mapping DB/Cache** | Data consistency | Maintains mapping between PD Incident ID ↔ Otobo Ticket ID |
| **Otobo REST API** | Destination | Create, update, and close tickets |
| **Idempotent updates** | Safety | Prevent duplicate state transitions |
| **Timers/Jobs** | Auto-close logic | Monitors pending tickets and triggers auto-closure after timeout |
| **Audit Logs** | Traceability | Logs all transitions and webhook interactions |

---

## 7. Summary Flow Diagram (Conceptual)

```text
PagerDuty → CrewAI → Otobo
   │            │
   │            ├── Escalation Decision
   │            │      ├── Escalate → in progress
   │            │      └── No Escalation → pending auto close+
   │
   ├── New Alert → Otobo new
   ├── Acknowledge → in progress
   ├── Note Added → add note
   ├── Resolved → closed successful (if eligible)
   └── Re-trigger → reopen (open)
```

---

## 8. Key Design Notes

- **PagerDuty “Resolved”** does not override escalated tickets in Otobo.  
- **CrewAI** acts as the intelligence layer that decides escalation and closure readiness.  
- **NOC manual closure** is final and synchronized back to PagerDuty.  
- **Audit trail** must exist for every transition.  
- **No duplicate ticket creation** for same PD incident ID.

---

**Document Version:** 1.0  
**Author:** Amin Basri  
**Date:** 2025-10-06  
**Purpose:** Developer implementation reference for PagerDuty–CrewAI–Otobo integration flow.
