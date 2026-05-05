# Task Checklist

**Session ID**: `phase02-session02-template-variables-and-rendering`
**Total Tasks**: 20
**Estimated Duration**: 3-4 hours
**Created**: 2026-05-05

---

## Legend

- `[x]` = Completed
- `[ ]` = Pending
- `[P]` = Parallelizable (can run with other [P] tasks)
- `[S0202]` = Session reference (02=phase number, 02=session number)
- `TNNN` = Task ID

---

## Progress Summary

| Category | Total | Done | Remaining |
|----------|-------|------|-----------|
| Setup | 2 | 2 | 0 |
| Foundation | 5 | 5 | 0 |
| Implementation | 8 | 8 | 0 |
| Testing | 5 | 5 | 0 |
| **Total** | **20** | **20** | **0** |

---

## Setup (2 tasks)

Initial configuration and environment preparation.

- [x] T001 [S0202] Verify prerequisites met: Phase 02 S01 complete, 376 tests passing, SQLite operational, ARQ/Redis available
- [x] T002 [S0202] Add Jinja2 >= 3.1 dependency to pyproject.toml and install (`pyproject.toml`)

---

## Foundation (5 tasks)

Core structures and base implementations.

- [x] T003 [S0202] [P] Create TemplateRenderRequest and TemplateRenderResponse Pydantic models with schema-validated input and explicit error mapping (`app/models/template.py`)
- [x] T004 [S0202] [P] Add template_id and template_version_id nullable columns to Render DB model (`app/db/models.py`)
- [x] T005 [S0202] Create Alembic migration 004 adding template_id and template_version_id columns to renders table (`alembic/versions/004_add_render_template_refs.py`)
- [x] T006 [S0202] [P] Create variable schema validator: type-check merge data against template variable_schema with required enforcement, default application, and explicit error mapping (`app/services/template_engine.py`)
- [x] T007 [S0202] Create Jinja2 SandboxedEnvironment engine with StrictUndefined and whitelisted-field-only recursive walker that expands only safe string fields (src, text, color, background, font_family, callback) (`app/services/template_engine.py`)

---

## Implementation (8 tasks)

Main feature implementation.

- [x] T008 [S0202] Add render_from_template method to TemplateService: fetch active version, validate merge vars, expand composition, re-validate with Pydantic, with explicit error mapping for all failure paths (`app/services/template_service.py`)
- [x] T009 [S0202] Create POST /v1/templates/{id}/renders route handler returning 202 Accepted with render ID, with duplicate-trigger prevention while in-flight (`app/api/routes_templates.py`)
- [x] T010 [S0202] Wire RenderServiceDep, ArqPoolDep, and SettingsDep into template render route via deps (`app/api/deps.py`)
- [x] T011 [S0202] Update render_crud.create_render to accept optional template_id and template_version_id parameters (`app/db/render_crud.py`)
- [x] T012 [S0202] Add TemplateExpansionError, TemplateVariableError error codes to error_codes module (`app/models/error_codes.py`)
- [x] T013 [S0202] Include template_id and template_version_id in RenderResponse and RenderListItem models (`app/models/render.py`)
- [x] T014 [S0202] Implement expanded.json persistence in the template render flow: store original template composition as context and expanded result as input.json for worker (`app/api/routes_templates.py`)
- [x] T015 [S0202] Update conftest.py test fixtures to support template render endpoint testing with proper service overrides (`tests/conftest.py`)

---

## Testing (5 tasks)

Verification and quality assurance.

- [x] T016 [S0202] [P] Write unit tests for variable schema validator: required fields, optional fields, defaults, type mismatches, unknown variables, empty schema (`tests/test_template_engine.py`)
- [x] T017 [S0202] [P] Write unit tests for Jinja2 sandbox engine and whitelisted field walker: basic expansion, strict undefined, injection prevention, nested structures, non-string field preservation (`tests/test_template_engine.py`)
- [x] T018 [S0202] Write integration tests for POST /v1/templates/{id}/renders: happy path, render record has template_id/version_id, expanded composition stored (`tests/test_api_template_renders.py`)
- [x] T019 [S0202] Write edge case tests: missing required vars (422), deleted template (409), non-existent template (404), version pinning after update, template with no variables, extra unused variables, Jinja2 syntax in values (`tests/test_api_template_renders.py`)
- [x] T020 [S0202] Run full test suite, validate ASCII encoding on all new/modified files, verify ruff check passes

---

## Completion Checklist

Before marking session complete:

- [x] All tasks marked `[x]`
- [x] All tests passing (429 = 376 existing + 53 new)
- [x] All files ASCII-encoded
- [x] implementation-notes.md updated
- [x] Ready for the validate workflow step

---

## Next Steps

Run the implement workflow step to begin AI-led implementation.
