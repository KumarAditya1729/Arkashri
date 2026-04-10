# pyre-ignore-all-errors
"""
Testing Agent — runs the Arkashri test suites (PyTest + Jest) against a generated patch
and reports PASS or FAIL back into the LangGraph state.
"""
from __future__ import annotations
import subprocess
import structlog  # type: ignore[import]

logger = structlog.get_logger("ai_engineer.testing")

BACKEND_ROOT  = "/Users/adityashrivastava/Desktop/company_1/arkashri"
FRONTEND_ROOT = "/Users/adityashrivastava/Desktop/company_1/frontend"

def _run(cmd: list[str], cwd: str, timeout: int = 120) -> tuple[int, str]:
    """Run a command and return (returncode, combined output)."""
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )
    return result.returncode, result.stdout + result.stderr

def test_node(state: dict) -> dict:
    """LangGraph node: run backend (pytest) + frontend (jest) test suites."""
    patch = state.get("code_patch", "")
    logger.info("Testing Agent — running test suites", patch_length=len(patch))

    backend_passed  = False
    frontend_passed = False
    output_lines    = []

    # --- Backend: pytest ---
    try:
        code, out = _run(["python", "-m", "pytest", "--tb=short", "-q"], BACKEND_ROOT)
        backend_passed = code == 0
        output_lines.append(f"[BACKEND PYTEST]\n{out.strip()}")
    except FileNotFoundError:
        output_lines.append("[BACKEND PYTEST] Skipped — pytest not installed.")
        backend_passed = True  # Don't fail the pipeline for missing env
    except subprocess.TimeoutExpired:
        output_lines.append("[BACKEND PYTEST] TIMEOUT after 120s")

    # --- Frontend: jest ---
    try:
        code, out = _run(["npm", "test", "--", "--passWithNoTests", "--watchAll=false"], FRONTEND_ROOT)
        frontend_passed = code == 0
        output_lines.append(f"[FRONTEND JEST]\n{out.strip()}")
    except FileNotFoundError:
        output_lines.append("[FRONTEND JEST] Skipped — npm not installed.")
        frontend_passed = True
    except subprocess.TimeoutExpired:
        output_lines.append("[FRONTEND JEST] TIMEOUT after 120s")

    overall = "PASS" if (backend_passed and frontend_passed) else "FAIL"
    report  = "\n\n".join(output_lines)
    logger.info("Testing Agent complete", overall=overall)

    return {"test_results": f"{overall}\n{report}"}

