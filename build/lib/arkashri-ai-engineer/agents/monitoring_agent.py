# pyre-ignore-all-errors
"""
Monitoring Agent — parses Prometheus alertmanager payloads or structured log
files to extract an actionable incident report for the Debugging Agent.
"""
from __future__ import annotations
import json
import os
import subprocess
import structlog  # type: ignore[import]

logger = structlog.get_logger("ai_engineer.monitoring")

LOG_PATHS = [
    "/var/log/arkashri/backend.log",
    "/tmp/arkashri-backend.log",
    "/Users/adityashrivastava/Desktop/company_1/arkashri/arkashri.log",
]

def _tail_logs(n: int = 80) -> str:
    """Return the last N lines from the first accessible log file."""
    for path in LOG_PATHS:
        if os.path.exists(path):
            try:
                result = subprocess.run(
                    ["tail", "-n", str(n), path],
                    capture_output=True, text=True, timeout=10
                )
                return result.stdout
            except Exception:
                continue
    return ""

def _parse_prometheus_alert(payload: dict) -> str:
    """Extract a human-readable description from a Prometheus alertmanager payload."""
    alerts = payload.get("alerts", [])
    if not alerts:
        return payload.get("commonAnnotations", {}).get("summary", "Unknown alert")
    alert = alerts[0]
    name  = alert.get("labels", {}).get("alertname", "Unknown")
    desc  = alert.get("annotations", {}).get("description", "No description")
    sev   = alert.get("labels", {}).get("severity", "unknown")
    return f"[{sev.upper()}] {name}: {desc}"

def _fetch_sentry_errors() -> str:
    """
    Pull the most recent unresolved error from the Sentry Issues API.
    Requires SENTRY_DSN or SENTRY_AUTH_TOKEN + SENTRY_ORG + SENTRY_PROJECT env vars.
    """
    try:
        import urllib.request
        token   = os.getenv("SENTRY_AUTH_TOKEN", "")
        org     = os.getenv("SENTRY_ORG", "")
        project = os.getenv("SENTRY_PROJECT", "")
        if not all([token, org, project]):
            return ""
        url = f"https://sentry.io/api/0/projects/{org}/{project}/issues/?query=is:unresolved&limit=1"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            issues = json.loads(resp.read())
            if issues:
                issue = issues[0]
                return f"[SENTRY] {issue.get('title', 'Unknown error')} — {issue.get('permalink', '')}"
    except Exception as e:
        logger.debug("Sentry fetch skipped", reason=str(e))
    return ""

def monitoring_check_node(state: dict) -> dict:
    """
    LangGraph node: ingest an alert payload or scan logs to produce an incident report.
    Priority order: Prometheus payload → Sentry Issues API → local log files.
    """
    raw_alert = state.get("raw_alert")
    incident  = ""

    # 1. Prometheus alertmanager payload
    if raw_alert:
        if isinstance(raw_alert, str):
            try:
                raw_alert = json.loads(raw_alert)
            except json.JSONDecodeError:
                raw_alert = {"alerts": [{"annotations": {"description": raw_alert}}]}
        incident = _parse_prometheus_alert(raw_alert)

    # 2. Sentry Issues API
    if not incident:
        incident = _fetch_sentry_errors()

    # 3. Tail local log files
    if not incident:
        log_tail = _tail_logs()
        if log_tail:
            lines  = log_tail.splitlines()
            errors = [l for l in lines if "ERROR" in l or "CRITICAL" in l or "Traceback" in l]
            incident = errors[-1] if errors else "No recent errors found in logs."
        else:
            incident = "Monitoring Agent: no alert payload, Sentry unreachable, and no log files."

    logger.info("Monitoring Agent created incident report", incident=incident)
    return {"incident_report": incident}

