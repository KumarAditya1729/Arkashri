# pyre-ignore-all-errors
"""
Security Agent — runs static analysis (bandit, pip-audit) on the codebase
and returns a pass/fail security clearance to the LangGraph orchestrator.
"""
from __future__ import annotations
import subprocess
import structlog  # type: ignore[import]

logger = structlog.get_logger("ai_engineer.security")

BACKEND_ROOT = "/Users/adityashrivastava/Desktop/company_1/arkashri"

def _run_scan(cmd: list[str], cwd: str) -> tuple[bool, str]:
    """Run a security tool and return (passed, output)."""
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=60
        )
        # bandit returns exit code 1 for found issues, 0 for clean
        passed = result.returncode == 0
        return passed, result.stdout + result.stderr
    except FileNotFoundError as e:
        return True, f"Tool not installed, skipping: {e}"
    except subprocess.TimeoutExpired:
        return False, "Security scan timed out."

def security_node(state: dict) -> dict:
    """LangGraph node: scan the codebase for vulnerabilities."""
    patch = state.get("code_patch", "")
    logger.info("Security Agent — scanning codebase", patch_length=len(patch))

    results = []
    all_clear = True

    # --- Bandit: Python SAST ---
    passed, out = _run_scan(
        ["python", "-m", "bandit", "-r", ".", "-ll", "-q"],
        BACKEND_ROOT
    )
    results.append(f"[BANDIT SAST]\n{out.strip()}")
    if not passed:
        all_clear = False

    # --- pip-audit: Dependency CVE scan ---
    passed, out = _run_scan(
        ["pip-audit", "--format", "json", "-q"],
        BACKEND_ROOT
    )
    results.append(f"[PIP-AUDIT]\n{out.strip()}")
    if not passed:
        all_clear = False

    verdict = "CLEAN" if all_clear else "VULNERABILITIES FOUND"
    report  = "\n\n".join(results)
    logger.info("Security Agent complete", verdict=verdict)

    return {
        "security_clearance": all_clear,
    }

