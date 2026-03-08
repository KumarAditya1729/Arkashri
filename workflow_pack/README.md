# Arkashri Workflow Pack (14 Audit Types)

This folder provides deterministic JSON templates for 14 major audit types.

## Structure

- `common/base_workflow.schema.json`: structural schema for all workflow templates.
- `index.json`: registry of all template files.
- `templates/*.json`: one workflow template per audit type.

## Template contract

Each template includes:

- `scope_fields`
- `phases` with executable step lists
- `evidence_checklist`
- `test_scripts`
- `report_sections`
- `closure_gates`
- `kpis`

## Use in Arkashri

1. Load template by `audit_type`.
2. Instantiate run metadata (`tenant_id`, period, owner assignments).
3. Execute phases in sequence and store evidence references.
4. Enforce closure gates before report sign-off.
5. Hash final report and append audit event.
