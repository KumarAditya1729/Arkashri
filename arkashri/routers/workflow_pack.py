from fastapi import APIRouter, HTTPException
from arkashri.schemas import WorkflowPackIndexOut, WorkflowTemplateOut
from arkashri.services.workflow_pack import get_workflow_pack_summary, load_workflow_template

router = APIRouter()

@router.get("", response_model=WorkflowPackIndexOut)
def workflow_pack_index() -> WorkflowPackIndexOut:
    try:
        summary = get_workflow_pack_summary()
        return WorkflowPackIndexOut(**summary)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{audit_type}", response_model=WorkflowTemplateOut)
def workflow_pack_template(audit_type: str) -> WorkflowTemplateOut:
    try:
        template = load_workflow_template(audit_type)
        return WorkflowTemplateOut(audit_type=audit_type, template=template)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
