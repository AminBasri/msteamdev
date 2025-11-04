---
title: "Alert Management KPI Framework"
version: "1.3"
scope: "CloudWatch → PagerDuty → OTOBO"
type: "metrics-definition"
stage: "alert-management"
author: "Amin Basri / CrewAI"
last_updated: "2025-10-31"
---

# 📊 Alert Management KPI Framework (CloudWatch → PagerDuty → OTOBO)

This document defines **Alert Management KPIs** to measure NOC responsiveness before incidents are formally logged in OTOBO.  
It aligns with **ITIL best practices** and is designed for automation by the **CrewAI reporting engine**.

---

## 🧠 Section 1: Scope

- **Covers:** Alert stage (CloudWatch → PagerDuty)  
- **Excludes:** Incident KPI tracking (handled in OTOBO after incident creation)  
- **Purpose:** Measure alert responsiveness (acknowledgment + resolution times)  
- **Metric Source:** PagerDuty alerts in JSON format (raw event data)

---

## ⚙️ Section 2: KPI Metrics

| Metric | Description | Purpose |
| ------- | ------------ | -------- |
| **MTTA (Mean Time To Acknowledge)** | Time between alert trigger and acknowledgment by NOC | Measures alert responsiveness |
| **MTTR (Mean Time To Resolve)** | Time between alert trigger and alert resolution | Measures how long it takes to clear/close the alert |
| **MTTFR (Mean Time To First Response)** | *Not applicable at this stage* | Used only at incident management stage |

✅ **Notes:**
- Alert Management focuses on **KPI measurements** and tracking.  
- **MTTR** is optional — used only to track alert closure speed.

---

## 🕓 Section 3: KPI Thresholds by Priority

| Priority | Business Impact | MTTA Target (mins) | MTTR Target (hrs) | Description |
| -------- | ---------------- | ------------------ | ----------------- | ------------ |
| **P1** | Critical | 5 | 4 | Major outage or total system failure |
| **P2** | High | 10 | 8 | High service degradation impacting many users |
| **P3** | Medium | 15 | 24 | Moderate issue with limited impact |
| **P4** | Low | 20 | 72 | Informational or minor issues |

🟢 **ITIL-Aligned:** Faster acknowledgment for higher priorities.

---

## 🧩 Section 4: KPI Compliance Logic (Updated)

```python
# Calculate averages
mean_time_to_resolve = f"{sum(ttr_values) / len(ttr_values):.1f}m" if ttr_values else "N/A"
mean_time_to_acknowledge = f"{sum(tta_values) / len(tta_values):.1f}m" if tta_values else "N/A"

# KPI compliance per priority
total_kpi_breaches = 0
total_kpi_incidents = 0

for alert in alerts:
    priority = alert["priority"]
    tta = alert["tta_minutes"]

    threshold = KPI_THRESHOLDS[priority].acknowledgment_minutes
    total_kpi_incidents += 1

    if tta > threshold:
        total_kpi_breaches += 1

kpi_compliance = 100 * (1 - total_kpi_breaches / total_kpi_incidents)

Rationale:

Dynamically applies acknowledgment thresholds per priority.

Evaluates responsiveness (MTTA) and optional resolution (MTTR).

Focuses on KPIs before incident creation.

Focuses purely on alert-level operational performance.

## ⚙️ Section 5: KPI Threshold Configuration

```python
KPI_THRESHOLDS = {
    "P1": KPIThreshold(acknowledgment_minutes=5,  resolution_hours=4),
    "P2": KPIThreshold(acknowledgment_minutes=10, resolution_hours=8),
    "P3": KPIThreshold(acknowledgment_minutes=15, resolution_hours=24),
    "P4": KPIThreshold(acknowledgment_minutes=20, resolution_hours=72)
}

## 📈 Section 6: Weighted Overall KPI Compliance
🎯 Purpose

Produce one aggregate KPI score across all priorities, based on business importance.

| Priority | Business Impact | Weight | Example KPI Compliance |
| -------- | --------------- | ------ | ---------------------- |
| **P1**   | Critical        | 0.4    | 95%                    |
| **P2**   | High            | 0.3    | 90%                    |
| **P3**   | Medium          | 0.2    | 85%                    |
| **P4**   | Low             | 0.1    | 80%                    |

Formula
Overall KPI Compliance=∑(Priority Weight×KPI Compliance)
Overall KPI Compliance=∑(Priority Weight×KPI Compliance)

Example:

(0.4×95)+(0.3×90)+(0.2×85)+(0.1×80)=90.5%
(0.4×95)+(0.3×90)+(0.2×85)+(0.1×80)=90.5%

✅ Result: Overall KPI compliance = 90.5 %

⚖️ Section 7: Weighted MTTA KPI Calculation (Overall KPI Compliance)
| Priority                         | MTTA Target (mins) | Weight (%) | Weighted Value (Target × Weight) |
| -------------------------------- | ------------------ | ---------- | -------------------------------- |
| **P1**                           | 5                  | 40 %       | 2.0                              |
| **P2**                           | 10                 | 30 %       | 3.0                              |
| **P3**                           | 15                 | 20 %       | 3.0                              |
| **P4**                           | 20                 | 10 %       | 2.0                              |
| **✅ Weighted Total MTTA Target** |                    |            | **10 mins**                      |

Formula
Weighted MTTA Target=∑(MTTA Targeti×Weighti)
(5×0.4)+(10×0.3)+(15×0.2)+(20×0.1)=10mins

💡 Interpretation

Overall MTTA KPI Target: ≤ 10 minutes

Balances critical alert responsiveness (P1/P2) with lower-priority volume

Suitable for management dashboards or CrewAI summary metrics

🧮 Section 8: Recommended Best-Practice Weight Ranges

| Priority | Suggested Weight Range | Typical MTTA Target | Notes                                  |
| -------- | ---------------------- | ------------------- | -------------------------------------- |
| **P1**   | 35–45 %                | 5–10 mins           | Major outage or critical impact        |
| **P2**   | 25–35 %                | 10–15 mins          | Significant degradation                |
| **P3**   | 15–25 %                | 15–30 mins          | Minor functional issue                 |
| **P4**   | 5–15 %                 | 20–60 mins          | Informational or non-service impacting |


✅ Section 9: Final Summary
| Metric                                | Description                                                 | Example Target |
| ------------------------------------- | ----------------------------------------------------------- | -------------- |
| **Overall Weighted MTTA Target**      | Combined average acknowledgment speed across all priorities | **≤ 10 mins**  |
| **Overall KPI Compliance (Weighted)** | Combined performance compliance across all priorities       | **≥ 90 %**     |
