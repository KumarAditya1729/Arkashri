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

    assert len(templates) == 14
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
        assert len(data["test_scripts"]) >= 3
        assert len(data["report_sections"]) >= 5
        assert len(data["closure_gates"]) >= 4

        for phase in data["phases"]:
            assert len(phase["steps"]) >= 2, f"Phase {phase['phase_id']} too shallow in {path.name}"
            for step in phase["steps"]:
                assert step["outputs"], f"Missing outputs in {path.name}:{step['step_id']}"
                assert step["evidence"], f"Missing evidence in {path.name}:{step['step_id']}"
