# pyre-ignore-all-errors
# fmt: off
"""
DevOps Agent — triggers deployment via Railway API or kubectl rollout
after a patch has been tested and security-cleared.
"""
from __future__ import annotations
import os
import subprocess
import structlog  # type: ignore[import]

logger = structlog.get_logger("ai_engineer.devops")

# Deployment method is chosen by env variable:
#   DEPLOYMENT_MODE = "railway" | "kubernetes" | "dry_run" (default)
DEPLOYMENT_MODE  = os.getenv("DEPLOYMENT_MODE", "dry_run")
RAILWAY_TOKEN    = os.getenv("RAILWAY_API_TOKEN", "")
K8S_NAMESPACE    = os.getenv("K8S_NAMESPACE", "arkashri")
K8S_DEPLOYMENT   = os.getenv("K8S_DEPLOYMENT_NAME", "arkashri-backend")

def _railway_deploy() -> tuple[bool, str]:
    """Trigger a Railway redeployment using the Railway CLI."""
    try:
        result = subprocess.run(
            ["railway", "up", "--detach"],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "RAILWAY_TOKEN": RAILWAY_TOKEN}
        )
        success = result.returncode == 0
        return success, result.stdout + result.stderr
    except FileNotFoundError:
        return False, "Railway CLI not found. Install with: npm i -g @railway/cli"
    except subprocess.TimeoutExpired:
        return False, "Railway deploy timed out after 120s"

def _kubectl_rollout() -> tuple[bool, str]:
    """Trigger a Kubernetes rolling restart."""
    try:
        result = subprocess.run(
            ["kubectl", "rollout", "restart", f"deployment/{K8S_DEPLOYMENT}",
             "-n", K8S_NAMESPACE],
            capture_output=True, text=True, timeout=60
        )
        success = result.returncode == 0
        return success, result.stdout + result.stderr
    except FileNotFoundError:
        return False, "kubectl not found. Cannot trigger Kubernetes rollout."
    except subprocess.TimeoutExpired:
        return False, "kubectl rollout timed out."

def deploy_node(state: dict) -> dict:
    """LangGraph node: deploy the patched code to production."""
    patch = state.get("code_patch", "")
    logger.info("DevOps Agent — initiating deployment", mode=DEPLOYMENT_MODE)

    if DEPLOYMENT_MODE == "railway":
        success, output = _railway_deploy()
    elif DEPLOYMENT_MODE == "kubernetes":
        success, output = _kubectl_rollout()
    else:
        # Dry-run mode: just log what would happen
        success = True
        output = (
            f"[DRY RUN] Deployment skipped. Set DEPLOYMENT_MODE=railway or kubernetes.\n"
            f"Patch staged ({len(patch)} bytes):\n{patch[:500]}..."
        )

    status = "SUCCESS" if success else "FAILED"
    logger.info("DevOps Agent complete", status=status)

    truncated: str = output.strip()[:300]  # type: ignore[index]
    return {
        "deployment_status": f"{status}: {truncated}"
    }

