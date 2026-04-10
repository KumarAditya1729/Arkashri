# pyre-ignore-all-errors
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

logger = structlog.get_logger("ai_engineer")

app = FastAPI(
    title="Arkashri Autonomous AI Engineer",
    description="Multi-agent orchestrator for Arkashri OS self-healing and deployment.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "arkashri-ai-engineer"}

@app.post("/webhook/alert")
async def receive_monitoring_alert(request: Request):
    """
    Ingest alerts from Prometheus/Grafana or Sentry.
    Triggers the LangGraph Orchestrator to debug the issue.
    """
    payload = await request.json()
    logger.info("received_alert", payload=payload)
    from agents.orchestrator import engine
    
    # Kick off the LangGraph State machine
    logger.info("Triggering Autonomous AI Engineer Workflow...")
    
    initial_state = {
        "incident_report": payload.get("alert_name", "Unknown 500 Error"),
    }
    
    final_state = engine.invoke(initial_state)
    logger.info("Workflow completed", final_state=final_state)
    
    return {
        "status": "acknowledged", 
        "job_id": "mock-job-123",
        "resolution_status": final_state.get("deployment_status")
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
