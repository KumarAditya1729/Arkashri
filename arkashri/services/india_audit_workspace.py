# pyre-ignore-all-errors
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import Engagement, EngagementPhase, PhaseStatus, SAChecklistItem, SAChecklistStatus

WORKSPACE_TEMPLATE_VERSION = "india_statutory_v1"

PHASE_BLUEPRINTS = [
    {"name": "Acceptance & Continuance", "owner_role": "Partner", "progress": 10},
    {"name": "Planning & Risk Assessment", "owner_role": "Manager", "progress": 20},
    {"name": "Fieldwork & Evidence", "owner_role": "Article", "progress": 40},
    {"name": "Manager Review", "owner_role": "Manager", "progress": 65},
    {"name": "Partner Review & Reporting", "owner_role": "Partner", "progress": 85},
    {"name": "Seal & Archive", "owner_role": "Partner", "progress": 100},
]

BASE_CHECKLIST_SECTIONS = [
    {
        "section_code": "SA210",
        "section_name": "Engagement Acceptance",
        "items": [
            {
                "item_code": "SA210-001",
                "standard_ref": "SA 210",
                "clause_ref": "Engagement Terms",
                "title": "Signed engagement letter obtained and approved",
                "response_type": "yes_no",
                "required": True,
                "audit_area": "Acceptance",
            }
        ],
    },
    {
        "section_code": "SA230",
        "section_name": "Documentation",
        "items": [
            {
                "item_code": "SA230-001",
                "standard_ref": "SA 230",
                "clause_ref": "Documentation Sufficiency",
                "title": "Working papers are sufficient for an experienced reviewer to reperform conclusions",
                "response_type": "text",
                "required": True,
                "audit_area": "Documentation",
            }
        ],
    },
    {
        "section_code": "PLANNING",
        "section_name": "Planning & Risk",
        "items": [
            {
                "item_code": "SA300-001",
                "standard_ref": "SA 300",
                "clause_ref": "Planning",
                "title": "Overall audit strategy and timeline documented",
                "response_type": "text",
                "required": True,
                "audit_area": "Planning",
            },
            {
                "item_code": "SA315-001",
                "standard_ref": "SA 315",
                "clause_ref": "Risk Assessment",
                "title": "Entity, process, and control walkthrough completed for major cycles",
                "response_type": "table",
                "required": True,
                "audit_area": "Risk",
            },
            {
                "item_code": "SA320-001",
                "standard_ref": "SA 320",
                "clause_ref": "Materiality",
                "title": "Overall and performance materiality approved",
                "response_type": "amount",
                "required": True,
                "audit_area": "Materiality",
            },
        ],
    },
    {
        "section_code": "FIELDWORK",
        "section_name": "Evidence & Analytics",
        "items": [
            {
                "item_code": "SA500-001",
                "standard_ref": "SA 500",
                "clause_ref": "Audit Evidence",
                "title": "Material balances are supported by source evidence or external confirmations",
                "response_type": "file",
                "required": True,
                "audit_area": "Evidence",
            },
            {
                "item_code": "SA520-001",
                "standard_ref": "SA 520",
                "clause_ref": "Analytical Procedures",
                "title": "Gross margin, debtor days, creditor days, and expense trend analytics completed",
                "response_type": "table",
                "required": True,
                "audit_area": "Analytics",
            },
            {
                "item_code": "SA550-001",
                "standard_ref": "SA 550",
                "clause_ref": "Related Parties",
                "title": "Related-party ledger scan and director/management inquiry completed",
                "response_type": "text",
                "required": True,
                "audit_area": "Related Parties",
            },
            {
                "item_code": "SA580-001",
                "standard_ref": "SA 580",
                "clause_ref": "Written Representations",
                "title": "Management representation letter prepared and agreed before report date",
                "response_type": "file",
                "required": True,
                "audit_area": "Representations",
            },
        ],
    },
]

CARO_SECTION = {
    "section_code": "CARO2020",
    "section_name": "CARO 2020",
    "items": [
        {
            "item_code": "CARO-3I-A",
            "standard_ref": "CARO 2020",
            "clause_ref": "Clause 3(i)(a)",
            "title": "PPE records contain quantitative details and locations",
            "response_type": "yes_no",
            "required": True,
            "audit_area": "Fixed Assets",
        },
        {
            "item_code": "CARO-3II-A",
            "standard_ref": "CARO 2020",
            "clause_ref": "Clause 3(ii)(a)",
            "title": "Inventory verification exceptions documented and reconciled",
            "response_type": "table",
            "required": True,
            "audit_area": "Inventory",
        },
        {
            "item_code": "CARO-3VII-A",
            "standard_ref": "CARO 2020",
            "clause_ref": "Clause 3(vii)(a)",
            "title": "Undisputed statutory dues including GST, PF, ESI, and income tax reviewed",
            "response_type": "table",
            "required": True,
            "audit_area": "Statutory Dues",
        },
        {
            "item_code": "CARO-3IX-A",
            "standard_ref": "CARO 2020",
            "clause_ref": "Clause 3(ix)(a)",
            "title": "Loan default and covenant breach review completed",
            "response_type": "text",
            "required": True,
            "audit_area": "Borrowings",
        },
        {
            "item_code": "CARO-3XV-A",
            "standard_ref": "CARO 2020",
            "clause_ref": "Clause 3(xv)",
            "title": "Non-cash transactions with directors or connected persons reviewed",
            "response_type": "yes_no",
            "required": True,
            "audit_area": "Related Parties",
        },
    ],
}

WORKING_PAPER_BLUEPRINTS = [
    {
        "paper_code": "TB-01",
        "title": "Trial Balance Lead Schedule",
        "audit_area": "Financial Statements",
        "source_data_required": ["trial_balance", "ledger_mapping"],
        "linked_checklist_codes": ["SA230-001", "SA320-001"],
    },
    {
        "paper_code": "REV-01",
        "title": "Revenue Analytics and Cut-off Testing",
        "audit_area": "Revenue",
        "source_data_required": ["vouchers", "sales_register"],
        "linked_checklist_codes": ["SA315-001", "SA520-001"],
    },
    {
        "paper_code": "GST-01",
        "title": "GST Reconciliation Summary",
        "audit_area": "GST",
        "source_data_required": ["sales_vouchers", "purchase_vouchers", "gstr_exports"],
        "linked_checklist_codes": ["CARO-3VII-A"],
    },
    {
        "paper_code": "RPT-01",
        "title": "Related Party Review",
        "audit_area": "Related Parties",
        "source_data_required": ["ledger_scan", "director_list"],
        "linked_checklist_codes": ["SA550-001", "CARO-3XV-A"],
    },
    {
        "paper_code": "MRL-01",
        "title": "Management Representation Letter Tracker",
        "audit_area": "Reporting",
        "source_data_required": ["management_responses"],
        "linked_checklist_codes": ["SA580-001"],
    },
]

REPORTING_PACK = {
    "report_sections": [
        "Opinion",
        "Basis for Opinion",
        "Key Audit Matters",
        "Other Information",
        "Management Responsibility",
        "Auditor Responsibility",
        "CARO Annexure",
    ],
    "finalization_gates": [
        "all_required_checklist_items_completed",
        "all_review_notes_resolved",
        "materiality_recorded",
        "management_rep_letter_attached",
        "partner_signoff_complete",
    ],
}


def _build_workspace_template(engagement: Engagement) -> dict:
    sections = copy.deepcopy(BASE_CHECKLIST_SECTIONS)
    if engagement.engagement_type.value in {"STATUTORY_AUDIT", "FINANCIAL_AUDIT"}:
        sections.append(copy.deepcopy(CARO_SECTION))

    checklist_sections = []
    for section in sections:
        items = []
        for item in section["items"]:
            items.append(
                {
                    **item,
                    "status": "PENDING",
                    "response": None,
                    "notes": None,
                    "review_status": "NOT_REVIEWED",
                    "updated_at": None,
                    "updated_by": None,
                }
            )
        checklist_sections.append(
            {
                "section_code": section["section_code"],
                "section_name": section["section_name"],
                "items": items,
            }
        )

    working_papers = []
    for paper in WORKING_PAPER_BLUEPRINTS:
        working_papers.append(
            {
                **paper,
                "status": "NOT_STARTED",
                "prepared_by": None,
                "reviewed_by": None,
                "last_updated_at": None,
            }
        )

    return {
        "template_version": WORKSPACE_TEMPLATE_VERSION,
        "jurisdiction": engagement.jurisdiction,
        "engagement_type": engagement.engagement_type.value,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checklist_sections": checklist_sections,
        "working_papers": working_papers,
        "reporting_pack": copy.deepcopy(REPORTING_PACK),
    }


def _ensure_workspace_bucket(engagement: Engagement) -> dict:
    metadata = engagement.state_metadata or {}
    if "history" not in metadata:
        metadata["history"] = []
    return metadata


async def bootstrap_india_audit_workspace(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    actor_id: str,
) -> Engagement:
    engagement = await session.get(Engagement, engagement_id)
    if not engagement:
        raise ValueError("Engagement not found")

    metadata = _ensure_workspace_bucket(engagement)
    workspace = metadata.get("india_workspace")
    if workspace is None:
        workspace = _build_workspace_template(engagement)
    else:
        workspace = copy.deepcopy(workspace)

    existing_phases = list(
        await session.scalars(
            select(EngagementPhase).where(EngagementPhase.engagement_id == engagement_id)
        )
    )
    existing_phase_names = {phase.name for phase in existing_phases}
    if not existing_phases:
        phase_statuses = [PhaseStatus.IN_PROGRESS] + [PhaseStatus.UPCOMING] * (len(PHASE_BLUEPRINTS) - 1)
    else:
        phase_statuses = None

    for index, blueprint in enumerate(PHASE_BLUEPRINTS):
        if blueprint["name"] in existing_phase_names:
            continue
        session.add(
            EngagementPhase(
                engagement_id=engagement_id,
                name=blueprint["name"],
                status=phase_statuses[index] if phase_statuses else PhaseStatus.UPCOMING,
                owner=blueprint["owner_role"],
                progress=blueprint["progress"],
            )
        )

    existing_sa = list(
        await session.scalars(
            select(SAChecklistItem).where(SAChecklistItem.engagement_id == engagement_id)
        )
    )
    existing_sa_keys = {(item.standard_ref, item.requirement) for item in existing_sa}
    for section in workspace["checklist_sections"]:
        for item in section["items"]:
            if not str(item["standard_ref"]).startswith("SA "):
                continue
            key = (item["standard_ref"], item["title"])
            if key in existing_sa_keys:
                continue
            session.add(
                SAChecklistItem(
                    engagement_id=engagement_id,
                    standard_ref=item["standard_ref"],
                    requirement=item["title"],
                    status=SAChecklistStatus.PENDING,
                )
            )

    metadata["india_workspace"] = workspace
    metadata["history"].append(
        {
            "from": engagement.status.value,
            "to": engagement.status.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": actor_id,
            "action": "INDIA_WORKSPACE_BOOTSTRAPPED",
        }
    )
    engagement.state_metadata = metadata
    session.add(engagement)
    await session.commit()
    await session.refresh(engagement)
    return engagement


def get_india_workspace(engagement: Engagement) -> dict:
    metadata = engagement.state_metadata or {}
    workspace = metadata.get("india_workspace")
    if workspace is None:
        raise ValueError("India audit workspace has not been bootstrapped for this engagement.")
    return workspace


async def update_workspace_checklist_item(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    item_code: str,
    status: str,
    response: dict | str | float | int | bool | None,
    notes: str | None,
    actor_id: str,
) -> dict:
    engagement = await session.get(Engagement, engagement_id)
    if not engagement:
        raise ValueError("Engagement not found")

    metadata = _ensure_workspace_bucket(engagement)
    workspace = copy.deepcopy(get_india_workspace(engagement))
    allowed_statuses = {"PENDING", "IN_PROGRESS", "COMPLETED", "REVIEWED", "NOT_APPLICABLE"}

    if status not in allowed_statuses:
        raise ValueError(f"Unsupported checklist status: {status}")

    updated_item: dict | None = None
    for section in workspace["checklist_sections"]:
        for item in section["items"]:
            if item["item_code"] != item_code:
                continue
            item["status"] = status
            item["response"] = response
            item["notes"] = notes
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            item["updated_by"] = actor_id
            if status in {"COMPLETED", "REVIEWED", "NOT_APPLICABLE"}:
                item["review_status"] = "READY_FOR_MANAGER"
            updated_item = item
            break
        if updated_item:
            break

    if updated_item is None:
        raise ValueError("Checklist item not found in workspace")

    metadata["india_workspace"] = workspace
    engagement.state_metadata = metadata
    session.add(engagement)
    await session.commit()
    return updated_item


def compute_workspace_readiness(engagement: Engagement) -> dict:
    workspace = get_india_workspace(engagement)
    checklist_items = [
        item
        for section in workspace["checklist_sections"]
        for item in section["items"]
    ]
    required_items = [item for item in checklist_items if item["required"]]
    completed_statuses = {"COMPLETED", "REVIEWED", "NOT_APPLICABLE"}
    completed_required = [item for item in required_items if item["status"] in completed_statuses]

    working_papers = workspace["working_papers"]
    finished_papers = [
        paper for paper in working_papers if paper["status"] in {"PREPARED", "REVIEWED", "FINAL"}
    ]

    blockers = []
    if len(completed_required) != len(required_items):
        pending_codes = [item["item_code"] for item in required_items if item["status"] not in completed_statuses]
        blockers.append(
            {
                "code": "CHECKLIST_PENDING",
                "message": "Mandatory SA/CARO checklist items are still pending.",
                "item_codes": pending_codes,
            }
        )
    if not finished_papers:
        blockers.append(
            {
                "code": "WORKING_PAPERS_NOT_STARTED",
                "message": "No working paper has been marked prepared or reviewed yet.",
                "item_codes": [paper["paper_code"] for paper in working_papers],
            }
        )

    return {
        "template_version": workspace["template_version"],
        "required_checklist_total": len(required_items),
        "required_checklist_completed": len(completed_required),
        "working_papers_total": len(working_papers),
        "working_papers_ready": len(finished_papers),
        "is_report_ready": not blockers,
        "blockers": blockers,
    }
