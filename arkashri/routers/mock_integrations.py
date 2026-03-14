# pyre-ignore-all-errors
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class IndependenceWebhookPayload(BaseModel):
    tenant_id: str
    client_name: str
    engagement_type: str

@router.post("/independence")
async def mock_independence_webhook(payload: IndependenceWebhookPayload):
    """
    Mock external webhook for Independence Checking.
    Returns cleared=False if the client_name contains 'conflict' or 'restricted'.
    """
    client_lower = payload.client_name.lower()
    if "conflict" in client_lower or "restricted" in client_lower:
        return {
            "cleared": False,
            "notes": "Mock Webhook: Entity flagged due to restricted keyword."
        }
    
    return {
        "cleared": True,
        "notes": "Mock Webhook: No conflicts found. Cleared."
    }
