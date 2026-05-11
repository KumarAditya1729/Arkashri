from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import Engagement
from arkashri.services.audit import append_audit_event
from arkashri.services.canonical import hash_object

SpecialistAuditType = Literal[
    "penetration_testing",
    "smart_contract_audit",
    "algorithm_audit",
    "digital_forensics",
    "data_leak_investigation",
    "autonomous_control_testing",
    "model_risk_audit",
]


class SpecialistAuditError(ValueError):
    pass


SPECIALIST_ENGINES: dict[str, dict[str, Any]] = {
    "penetration_testing": {
        "name": "Penetration Testing Assurance Engine",
        "safe_mode": True,
        "objective": "Plan and document an authorized penetration test without executing exploit code from Arkashri.",
        "specialist_roles": ["Security Lead", "Application Owner", "Infrastructure Owner", "Engagement Partner"],
        "evidence": ["Signed rules of engagement", "Asset inventory", "Scope authorization", "Scanner reports", "Remediation evidence"],
        "procedures": [
            "Validate written authorization, scope, testing windows, and excluded systems.",
            "Create asset and endpoint inventory with criticality and data classification.",
            "Review vulnerability scan reports, exploitability, compensating controls, and business impact.",
            "Classify findings using severity, likelihood, exploit preconditions, and remediation complexity.",
            "Track remediation, retest evidence, and residual risk acceptance.",
        ],
        "red_flags": ["No signed authorization", "Internet-facing critical assets", "Unauthenticated critical vulnerabilities", "No retest evidence"],
    },
    "smart_contract_audit": {
        "name": "Smart Contract Audit Engine",
        "safe_mode": True,
        "objective": "Review smart contract design, source, deployment controls, and known vulnerability classes.",
        "specialist_roles": ["Blockchain Auditor", "Protocol Engineer", "Security Reviewer", "Engagement Partner"],
        "evidence": ["Repository commit hash", "Deployment addresses", "Compiler settings", "Test coverage", "Admin key policy"],
        "procedures": [
            "Freeze repository commit, compiler version, dependency graph, and deployment address evidence.",
            "Review access control, upgradeability, oracle dependency, reentrancy, arithmetic, pause and emergency controls.",
            "Validate unit, integration, invariant, and fork-test coverage supplied by the client.",
            "Map privileged roles and key custody to governance approvals and multisig evidence.",
            "Document unresolved vulnerabilities and required retest evidence before production launch.",
        ],
        "red_flags": ["Unaudited upgrade proxy", "Single-admin private key", "No invariant tests", "Unverified deployed bytecode"],
    },
    "algorithm_audit": {
        "name": "Algorithm Audit Engine",
        "safe_mode": True,
        "objective": "Assess algorithm governance, fairness, explainability, testing, monitoring, and human oversight.",
        "specialist_roles": ["Model Auditor", "Data Scientist", "Legal/Compliance Reviewer", "Business Owner"],
        "evidence": ["Model card", "Feature schema", "Training data lineage", "Validation report", "Monitoring logs"],
        "procedures": [
            "Identify algorithm objective, users impacted, prohibited uses, and human override workflow.",
            "Review data lineage, feature selection, bias controls, explainability, and validation metrics.",
            "Evaluate performance drift, adverse-impact monitoring, and incident response triggers.",
            "Test approval, change management, rollback, and access control around model deployment.",
            "Document limitations, residual risks, and mandatory human review gates.",
        ],
        "red_flags": ["No model card", "No bias testing", "Unapproved production change", "No human appeal or override path"],
    },
    "digital_forensics": {
        "name": "Digital Forensics Execution Engine",
        "safe_mode": True,
        "objective": "Manage forensic evidence handling, chain of custody, analysis plan, and litigation-ready reporting.",
        "specialist_roles": ["Forensic Lead", "Legal Counsel", "IT Custodian", "Evidence Controller"],
        "evidence": ["Legal hold notice", "Chain of custody", "Device/image hash", "Access logs", "Investigation report"],
        "procedures": [
            "Confirm legal basis, scope, custodians, preservation notice, and chain-of-custody owner.",
            "Record image/acquisition hashes, collection timestamps, storage location, and access restrictions.",
            "Triangulate user, endpoint, email, cloud, and application logs without altering original evidence.",
            "Classify events by timeline, actor, data affected, confidence, and litigation relevance.",
            "Prepare privileged/legal review package and final investigation report.",
        ],
        "red_flags": ["No legal hold", "Missing image hash", "Evidence accessed without logging", "Original evidence modified"],
    },
    "data_leak_investigation": {
        "name": "Data Leak Investigation Engine",
        "safe_mode": True,
        "objective": "Assess suspected data leakage, affected records, containment, notification, and control failures.",
        "specialist_roles": ["Incident Lead", "Privacy Officer", "Security Analyst", "Legal Counsel"],
        "evidence": ["Incident ticket", "DLP/SIEM logs", "Affected data inventory", "Containment actions", "Notification assessment"],
        "procedures": [
            "Define suspected leak vector, time window, data classes, systems, users, and external parties.",
            "Correlate DLP, email, endpoint, IAM, cloud storage, and network evidence.",
            "Quantify affected records and privacy/regulatory notification obligations.",
            "Assess containment, credential rotation, access revocation, and control gaps.",
            "Generate root-cause, remediation, and legal notification support pack.",
        ],
        "red_flags": ["Personal data exposure", "Privileged account involved", "No containment timestamp", "Regulatory deadline risk"],
    },
    "autonomous_control_testing": {
        "name": "Autonomous Control Testing Engine",
        "safe_mode": True,
        "objective": "Continuously test controls using logs, rules, exceptions, and auditor-approved thresholds.",
        "specialist_roles": ["Controls Lead", "Process Owner", "Data Owner", "Audit Reviewer"],
        "evidence": ["Control library", "Rule thresholds", "Exception logs", "Owner responses", "Retest results"],
        "procedures": [
            "Map controls to data sources, frequency, control owner, rule threshold, and evidence artifact.",
            "Generate deterministic test rules and exception criteria approved by the auditor.",
            "Run exception analysis against available logs or transaction populations.",
            "Route exceptions to management response and remediation tracking.",
            "Retest closed exceptions and preserve audit trail for each automated test run.",
        ],
        "red_flags": ["No control owner", "Threshold changed without approval", "High exceptions unresolved", "No retest evidence"],
    },
    "model_risk_audit": {
        "name": "Model Risk Audit Engine",
        "safe_mode": True,
        "objective": "Review model inventory, validation, governance, monitoring, and production risk controls.",
        "specialist_roles": ["Model Risk Lead", "Independent Validator", "Model Owner", "Compliance Reviewer"],
        "evidence": ["Model inventory", "Validation report", "Approval memo", "Monitoring dashboard", "Issue log"],
        "procedures": [
            "Inventory model purpose, tiering, owner, users, dependencies, and regulatory impact.",
            "Review independent validation, assumptions, limitations, sensitivity, and back-testing.",
            "Assess governance approvals, change controls, access controls, and production deployment evidence.",
            "Evaluate drift, performance monitoring, overrides, incidents, and retirement criteria.",
            "Document model limitations, compensating controls, and unresolved validation issues.",
        ],
        "red_flags": ["No independent validation", "High-impact model unmonitored", "No change approval", "Material drift unresolved"],
    },
}


def _validate_type(audit_type: str) -> dict[str, Any]:
    engine = SPECIALIST_ENGINES.get(audit_type)
    if engine is None:
        raise SpecialistAuditError(f"Unknown specialist audit type: {audit_type}")
    return engine


def get_specialist_engine_catalog() -> dict[str, Any]:
    return {
        "engine_id": "arkashri_specialist_audit_execution_engine",
        "version": "1.0.0",
        "safe_execution_policy": "Arkashri generates authorized audit workprograms, evidence requirements, findings, and review gates. It does not execute exploits, bypass controls, or alter forensic evidence.",
        "audit_types": [{"audit_type": key, **value} for key, value in SPECIALIST_ENGINES.items()],
    }


def build_specialist_workprogram(audit_type: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    engine = _validate_type(audit_type)
    context = context or {}
    risks = [
        {
            "risk_ref": f"SP-{index:03d}",
            "title": red_flag,
            "severity": "HIGH" if index <= 2 else "MEDIUM",
            "recommended_response": "Obtain evidence, assign owner, document management response, and retest before closure.",
        }
        for index, red_flag in enumerate(engine["red_flags"], start=1)
    ]
    tests = [
        {
            "test_ref": f"T-{index:03d}",
            "procedure": procedure,
            "evidence_required": engine["evidence"],
            "pass_condition": "Auditor obtains sufficient appropriate evidence and unresolved exceptions are tracked.",
        }
        for index, procedure in enumerate(engine["procedures"], start=1)
    ]
    workprogram = {
        "audit_type": audit_type,
        "name": engine["name"],
        "safe_mode": engine["safe_mode"],
        "objective": engine["objective"],
        "specialist_roles": engine["specialist_roles"],
        "scope_context": context,
        "evidence_checklist": [
            {"id": f"E-{index:03d}", "description": item, "required": True}
            for index, item in enumerate(engine["evidence"], start=1)
        ],
        "test_program": tests,
        "risk_register": risks,
        "report_sections": [
            "Scope and authorization",
            "Methodology and limitations",
            "Evidence reviewed",
            "Findings and severity",
            "Management response",
            "Retest and closure",
            "Human specialist sign-off",
        ],
        "closure_gates": [
            "Written authorization and scope approved",
            "All high findings have management response",
            "Retest evidence obtained or residual risk accepted",
            "Specialist reviewer and engagement partner sign-off completed",
        ],
        "human_review_required": True,
    }
    return {**workprogram, "workprogram_hash": hash_object(workprogram)}


async def record_specialist_workprogram(
    session: AsyncSession,
    *,
    engagement: Engagement,
    actor: str,
    audit_type: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workprogram = build_specialist_workprogram(audit_type, context)
    run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"arkashri:specialist:{engagement.tenant_id}:{engagement.id}:{audit_type}:{workprogram['workprogram_hash']}"))
    await append_audit_event(
        session,
        tenant_id=engagement.tenant_id,
        engagement_id=engagement.id,
        jurisdiction=engagement.jurisdiction,
        event_type="SPECIALIST_AUDIT_WORKPROGRAM_GENERATED",
        entity_type="specialist_audit_workprogram",
        entity_id=run_id,
        payload={
            "actor": actor,
            "audit_type": audit_type,
            "workprogram_hash": workprogram["workprogram_hash"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "human_review_required": True,
        },
    )
    await session.commit()
    return {"run_id": run_id, "workprogram": workprogram}
