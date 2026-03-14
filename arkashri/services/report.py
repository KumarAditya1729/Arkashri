# pyre-ignore-all-errors
import json
import structlog
from pathlib import Path

logger = structlog.get_logger("services.report")

try:
    from weasyprint import HTML
    import jinja2
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    logger.warning("WeasyPrint or Jinja2 not installed; PDF generation disabled.")


TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

def generate_pdf_report(run_data: dict, steps_data: list[dict]) -> bytes:
    """
    Renders an HTML template with Jinja2 using the final Audit Run state, 
    and converts it to a binary PDF via WeasyPrint.
    """
    if not WEASYPRINT_AVAILABLE:
        raise RuntimeError("PDF Export disabled. WeasyPrint/Jinja2 missing.")

    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("report.html")

    # Format steps for the template
    formatted_steps = []
    for step in steps_data:
        evidence = step.get("evidence_payload", {})
        output = evidence.get("output_payload", {})
        
        formatted_steps.append({
            "phase_id": step.get("phase_id", "Unknown"),
            "step_id": step.get("step_id", "Unknown"),
            "action": step.get("action", "Unknown"),
            "result": output.get("result", "UNKNOWN"),
            "evidence_hash": evidence.get("evidence_hash", "N/A"),
            "evidence_payload": json.dumps(evidence, indent=2)
        })

    html_out = template.render(
        tenant_id=run_data.get("tenant_id", "N/A"),
        run_id=str(run_data.get("id", "N/A")),
        audit_type=run_data.get("audit_type", "N/A"),
        jurisdiction=run_data.get("jurisdiction", "N/A"),
        status=run_data.get("status", "N/A"),
        completed_at=str(run_data.get("completed_at", "N/A")),
        run_hash=run_data.get("run_hash", "N/A"),
        steps=formatted_steps
    )

    pdf_bytes = HTML(string=html_out).write_pdf()
    return pdf_bytes
