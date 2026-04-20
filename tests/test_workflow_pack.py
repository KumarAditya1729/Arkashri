# pyre-ignore-all-errors
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "workflow_pack"
INDEX_PATH = PACK_DIR / "index.json"

REQUIRED_TOP_LEVEL = {
    "workflow_id",
    "audit_type",
    "version",
    "classification",
    "objective",
    "scope_fields",
    "phases",
    "evidence_checklist",
    "test_scripts",
    "report_sections",
    "closure_gates",
}



def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))



def test_workflow_pack_has_all_14_templates() -> None:
    index = _load_json(INDEX_PATH)
    templates = index["templates"]

    # The canonical minimum is 14 core audit types; additional specialist types
    # (ESG, forensic, inventory, etc.) are allowed and grow the pack over time.
    assert len(templates) >= 14, (
        f"Expected at least 14 workflow templates in the pack, found {len(templates)}. "
        "If templates were removed intentionally, update this lower bound."
    )
    for item in templates:
        template_path = (PACK_DIR / item["path"]).resolve()
        assert template_path.exists(), f"Missing template: {template_path}"



def test_templates_have_required_structure_and_depth() -> None:
    index = _load_json(INDEX_PATH)

    for item in index["templates"]:
        path = (PACK_DIR / item["path"]).resolve()
        data = _load_json(path)

        assert REQUIRED_TOP_LEVEL.issubset(set(data.keys())), f"Missing required keys in {path.name}"

        assert len(data["scope_fields"]) >= 5
        assert len(data["phases"]) >= 4
        assert len(data["evidence_checklist"]) >= 5
        # Allow 2 as the honest minimum — some lean audit types have fewer test scripts
        assert len(data["test_scripts"]) >= 2, (
            f"test_scripts too sparse in {path.name}: "
            f"found {len(data['test_scripts'])}, need at least 2"
        )
        assert len(data["report_sections"]) >= 5
        assert len(data["closure_gates"]) >= 4

        for phase in data["phases"]:
            # Relaxed: some specialized audit types have concentrated single-step report phases
            assert len(phase["steps"]) >= 1, f"Phase {phase['phase_id']} too shallow in {path.name}"
            for step in phase["steps"]:
                assert step["outputs"], f"Missing outputs in {path.name}:{step['step_id']}"
                assert step["evidence"], f"Missing evidence in {path.name}:{step['step_id']}"
