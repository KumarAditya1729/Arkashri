# pyre-ignore-all-errors
import json
import structlog
from circuitbreaker import circuit, CircuitBreakerError
from typing import Any
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from arkashri.config import get_settings

logger = structlog.get_logger("services.ai_fabric")
settings = get_settings()

client: Any
try:
    from openai import AsyncOpenAI
    # Initialize a singleton client if the API key is present
    if settings.openai_api_key:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
    else:
        client = None
except ImportError:
    client = None
    logger.warning("openai SDK not installed; AI Fabric disabled.")


class OpenAIInference:
    """Helper to maintain persistent circuit breaker state across inference calls."""
    @circuit(failure_threshold=3, recovery_timeout=60)
    async def call(self, system_prompt: str, user_prompt: str) -> str:
        if not client:
            raise RuntimeError("Client uninitialized")
            
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "audit_verdict",
                    "schema": AuditVerdict.model_json_schema()
                }
            },
            temperature=0.1,
            max_tokens=600,
        )
        return response.choices[0].message.content or ""

# Global instance to persist circuit state
inference_engine = OpenAIInference()


class AuditVerdict(BaseModel):
    """Structured LLM output dictating the pass/fail determination of an Audit Step."""
    verdict: str = Field(description="Must be strictly 'PASS' or 'FAIL'")
    confidence_score: float = Field(description="float between 0.0 and 1.0 indicating AI certainty")
    reasoning: str = Field(description="A concise narrative explaining the verdict based on supplied evidence")
    extracted_anomalies: list[str] = Field(description="A list of specific flags or deviations found (empty if none)")


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    reraise=True
)
async def analyze_step_evidence(
    step_instruction: str,
    evidence_payload: dict[str, Any],
    audit_type: str = "general_audit",
    audit_objective: str = "Verify compliance and integrity.",
) -> dict[str, Any]:
    """
    Submits contextual step evidence to the OpenAI GPT-4o engine requesting
    a deterministic JSON formatted PASS/FAIL verdict.

    If the OpenAI API key is unconfigured or the SDK is missing,
    it falls back to a deterministic manual mock payload to prevent blocking the engine.
    """
    if not client:
        logger.warning(
            "ai_fabric_disabled",
            message="OpenAI client unavailable (missing key or dependency). Returning UNVERIFIED payload."
        )
        return {
            "verdict": "UNVERIFIED",
            "confidence_score": 0.0,
            "reasoning": "AI Execution disabled due to missing active OpenAI API Key.",
            "extracted_anomalies": ["AI_SYSTEM_UNAVAILABLE"],
        }

    display_type = audit_type.replace("_", " ").title()
    system_prompt = (
        f"You are an expert {display_type} professional for Arkashri OS.\n"
        f"GLOBAL AUDIT OBJECTIVE: {audit_objective}\n\n"
        "Your task: evaluate the given JSON structured evidence against the required instruction.\n"
        "You MUST return a JSON payload matching the target schema exactly.\n"
        "Determine if the evidence strictly satisfies the requirement (PASS) or if there are anomalies (FAIL)."
    )
    
    user_prompt = (
        f"INSTRUCTION TO VERIFY:\n{step_instruction}\n\n"
        f"SUPPLIED EVIDENCE:\n{json.dumps(evidence_payload, indent=2)}"
    )

    try:
        raw_json = await inference_engine.call(system_prompt, user_prompt)
        if not raw_json:
            raise ValueError("No content returned from OpenAI")
            
        return json.loads(raw_json)

    except CircuitBreakerError:
        logger.error("openai_circuit_open", message="OpenAI API is currently unreachable. Circuit broken.")
        return {
            "verdict": "FAIL",
            "confidence_score": 0.0,
            "reasoning": "AI Circuit Breaker triggered due to cascade failures.",
            "extracted_anomalies": ["CIRCUIT_BROKEN"],
        }
    except Exception as e:
        logger.error("openai_inference_failed", error=str(e))
        return {
            "verdict": "FAIL",
            "confidence_score": 0.0,
            "reasoning": f"AI evaluation crashed: {e}",
            "extracted_anomalies": ["SYSTEM_ERROR"],
        }
