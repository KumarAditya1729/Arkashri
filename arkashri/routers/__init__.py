# pyre-ignore-all-errors
from fastapi import APIRouter

from arkashri.routers.engagements import router as engagements_router
from arkashri.routers.system import router as system_router
from arkashri.routers.workflow_pack import router as workflow_pack_router
from arkashri.routers.orchestration import router as orchestration_router
from arkashri.routers.approvals import router as approvals_router
from arkashri.routers.rag import router as rag_router
from arkashri.routers.blockchain import router as blockchain_router
from arkashri.routers.analytics import router as analytics_router
from arkashri.routers.multi_chain import router as multi_chain_router
from arkashri.routers.security import router as security_router
from arkashri.routers.regulatory import router as regulatory_router
from arkashri.routers.usas import router as usas_router
from arkashri.routers.reporting import router as reporting_router
from arkashri.routers.jurisdictions import router as jurisdictions_router
from arkashri.routers.playbooks import router as playbooks_router
from arkashri.routers.auth import router as auth_router
from arkashri.routers.overrides import router as overrides_router
from arkashri.routers.risks import router as risks_router
from arkashri.routers.evidence import router as evidence_router
from arkashri.routers.token import router as token_router
from arkashri.routers.seal_sessions import router as seal_sessions_router
from arkashri.routers.erp_ingestion import router as erp_ingestion_router
from arkashri.routers.users import router as users_router
from arkashri.routers.controls import router as controls_router
from arkashri.routers.planning import router as planning_router
from arkashri.routers.going_concern import router as going_concern_router
from arkashri.routers.bank_ingestion import router as bank_ingestion_router

router = APIRouter()

router.include_router(engagements_router, prefix="/engagements", tags=["Engagements"])
router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
router.include_router(users_router, prefix="/auth", tags=["User Management"])
router.include_router(token_router, prefix="/token", tags=["Token Auth"])
router.include_router(system_router, prefix="/system", tags=["System Setup"])
router.include_router(workflow_pack_router, prefix="/workflow-pack", tags=["Workflow Pack Templates"])
router.include_router(orchestration_router, prefix="/orchestration", tags=["Audit Orchestration"])
router.include_router(approvals_router, prefix="/approvals", tags=["Governance & Approvals"])
router.include_router(rag_router, prefix="/rag", tags=["Knowledge Center (RAG)"])
router.include_router(blockchain_router, prefix="/blockchain", tags=["Blockchain Anchoring"])
router.include_router(analytics_router, prefix="/analytics", tags=["ML Analytics"])
router.include_router(multi_chain_router, prefix="/multi-chain", tags=["Multi-Chain Blockchain"])
router.include_router(security_router, prefix="/security", tags=["Security & Auth"])
router.include_router(regulatory_router, prefix="/regulatory", tags=["Regulatory Intelligence"])
router.include_router(usas_router, prefix="/usas", tags=["Specialized Audits (USAS)"])
router.include_router(reporting_router, prefix="/reporting", tags=["Automated Reporting"])
router.include_router(jurisdictions_router, prefix="/jurisdiction", tags=["Jurisdiction Mappings"])
router.include_router(playbooks_router, prefix="/playbooks", tags=["Audit Playbooks"])
router.include_router(overrides_router, prefix="/overrides", tags=["Professional Skepticism (Overrides)"])
router.include_router(risks_router, prefix="", tags=["Risk Register"])
router.include_router(evidence_router, prefix="", tags=["Evidence Management"])
router.include_router(seal_sessions_router, prefix="", tags=["Multi-Partner Seal Sessions"])
router.include_router(erp_ingestion_router, prefix="", tags=["ERP Integration"])
router.include_router(bank_ingestion_router, prefix="", tags=["Bank Ingestion"])
router.include_router(controls_router, prefix="", tags=["Controls Registry"])
router.include_router(planning_router, prefix="", tags=["Audit Planning"])
router.include_router(going_concern_router, prefix="", tags=["Going Concern (SA 570)"])
