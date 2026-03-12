from arkashri.models import StandardsFramework, MaterialityBasis

JURISDICTION_MAP = {
    "IN": StandardsFramework.ICAI_SA,
    "US": StandardsFramework.PCAOB_AS,
    "UK": StandardsFramework.FRC_ISA,
    "GB": StandardsFramework.FRC_ISA, # Alternate for UK
    "IFRS": StandardsFramework.ISA,
    "EU": StandardsFramework.ISA,
}

def get_standards_for_jurisdiction(jurisdiction: str) -> dict:
    """
    Returns the applicable standards framework and default risk/materiality 
    thresholds for a given jurisdiction code.
    Defaults to International Standards on Auditing (ISA) for unknown codes.
    """
    # Defensive uppercase and strip
    clean_jur = str(jurisdiction).upper().strip()
    framework = JURISDICTION_MAP.get(clean_jur, StandardsFramework.ISA)
    
    if framework == StandardsFramework.ICAI_SA:
        return {
            "framework": framework,
            "materiality_basis": MaterialityBasis.PROFIT_BEFORE_TAX,
            "risk_thresholds": {"high": 0.85, "medium": 0.60},
            "sa_equivalents": "SA 200 - 720"
        }
    elif framework == StandardsFramework.PCAOB_AS:
        return {
            "framework": framework,
            "materiality_basis": MaterialityBasis.REVENUE,
            "risk_thresholds": {"high": 0.80, "medium": 0.55}, # PCAOB leans towards lower thresholds
            "sa_equivalents": "AS 1000 - 3310"
        }
    elif framework == StandardsFramework.FRC_ISA:
        return {
            "framework": framework,
            "materiality_basis": MaterialityBasis.TOTAL_ASSETS,
            "risk_thresholds": {"high": 0.82, "medium": 0.58},
            "sa_equivalents": "ISA (UK) 200 - 720"
        }
    else: # ISA default
        return {
            "framework": framework,
            "materiality_basis": MaterialityBasis.PROFIT_BEFORE_TAX,
            "risk_thresholds": {"high": 0.85, "medium": 0.60},
            "sa_equivalents": "ISA 200 - 720"
        }
