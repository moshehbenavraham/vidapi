# Session Specification

**Session ID**: `phase02-session02-template-variables-and-rendering`
**Phase**: 02 - Templates and Polish
**Status**: Not Started
**Created**: 2026-05-05

---

## 1. Session Overview

This session implements the Jinja2-based template variable substitution engine and the template render endpoint (`POST /v1/templates/{id}/renders`). Together these turn VidAPI's template CRUD (delivered in Session 01) into a production-ready template-driven video generation system where clients supply merge data and receive a queued render.

The engine enforces strict variable validation, sandboxed expansion on whitelisted string fields only, and post-expansion Pydantic re-validation so that template injection cannot corrupt the composition structure. Every template-based render pins to the active version at submission time and stores the expanded composition for reproducibility.

This session completes the core template value proposition: "Create once, render many variations."

---

## 2. Objectives

1. Deliver a Jinja2 SandboxedEnvironment engine that expands template variables only in whitelisted string fields with StrictUndefined handling
2. Deliver a variable schema validator that type-checks and enforces required merge variables before expansion
3. Deliver the `POST /v1/templates/{id}/renders` endpoint that accepts merge data, expands the template, creates a render, and enqueues to ARQ
4. Store template_id, template_version_id, and expanded.json on every template-based render for traceability and reproducibility

---

## 3. Prerequisites

### Required Sessions
- [x] `phase02-session01-template-models-and-crud-api` - Template/TemplateVersion models, CRUD service, and API routes

### Required Tools/Knowledge
- Python 3.11+ with type hints
- Jinja2 SandboxedEnvironment API
- Pydantic v2 discriminated unions (composition model)
- SQLModel async patterns (established in Session 01)

### Environment Requirements
- SQLite dev database operational with templates and template_versions tables
- ARQ/Redis available for async render mode
- Existing render pipeline functional (Phase 01 complete)

---

## 4. Scope

### In Scope (MVP)
- Variable schema validation: type checks (string, url, number, boolean), required field enforcement, default value application
- Jinja2 SandboxedEnvironment with StrictUndefined for safe variable substitution
- Whitelisted-field-only expansion: only designated string fields in the composition tree are subject to substitution
- `POST /v1/templates/{id}/renders` accepting merge data and optional callback URL
- Post-expansion Pydantic re-validation of the expanded composition
- Template version pinning at submission time (uses active_version_id when render is created)
- Storing expanded.json artifact on the render record
- Adding template_id and template_version_id columns to the renders table
- Including template metadata in render status responses
- Custom TemplateExpansionError with mapped error codes

### Out of Scope (Deferred)
- Webhook callback delivery on render completion - *Reason: Session 03*
- Transition and positioning enhancements - *Reason: Session 04*
- Complex variable types beyond string/url/number/boolean - *Reason: Future iteration*
- Non-string field substitution (numeric fields, arrays) - *Reason: Security risk, not needed for MVP*

---

## 5. Technical Approach

### Architecture
The template render flow inserts a pre-processing step before the existing render pipeline:

```
POST /v1/templates/{id}/renders
  -> get template + active version (pin version)
  -> validate merge data against variable_schema
  -> expand composition via Jinja2 sandbox (whitelisted fields)
  -> re-validate expanded composition via Pydantic
  -> create render record (with template_id, template_version_id)
  -> persist expanded composition as input.json
  -> enqueue to ARQ (async) or run inline (sync)
```

The worker receives the already-expanded composition and proceeds normally -- no worker modifications required for the expansion itself.

### Design Patterns
- **Whitelisted field walker**: Recursive dict/list traversal that identifies safe string fields by path pattern. Prevents template injection into numeric, boolean, or structural fields.
- **Sandbox isolation**: Jinja2 SandboxedEnvironment prevents template authors from accessing Python internals.
- **Version pinning**: Render captures template_version_id at submission time; subsequent template updates do not affect in-flight or historical renders.

### Technology Stack
- Jinja2 >= 3.1 (SandboxedEnvironment, StrictUndefined)
- Pydantic v2 (composition re-validation)
- SQLModel (render table schema extension)
- Alembic (migration for new columns)

---

## 6. Deliverables

### Files to Create
| File | Purpose | Est. Lines |
|------|---------|------------|
| `app/services/template_engine.py` | Jinja2 sandbox engine, variable schema validator, whitelisted field walker | ~200 |
| `alembic/versions/004_add_render_template_refs.py` | Migration adding template_id, template_version_id to renders | ~40 |
| `tests/test_template_engine.py` | Unit tests for engine, validator, and field walker | ~250 |
| `tests/test_api_template_renders.py` | Integration tests for POST /v1/templates/{id}/renders | ~300 |

### Files to Modify
| File | Changes | Est. Lines |
|------|---------|------------|
| `pyproject.toml` | Add Jinja2 dependency | ~2 |
| `app/models/template.py` | Add TemplateRenderRequest/TemplateRenderResponse models | ~30 |
| `app/db/models.py` | Add template_id, template_version_id columns to Render | ~5 |
| `app/db/render_crud.py` | Accept optional template fields in create_render | ~10 |
| `app/services/template_service.py` | Add render_from_template method | ~60 |
| `app/api/routes_templates.py` | Add POST /templates/{id}/renders route | ~50 |
| `app/api/deps.py` | Ensure render deps available to template routes | ~5 |
| `app/models/render.py` | Add template fields to render response models | ~10 |
| `app/models/error_codes.py` | Add template expansion error codes | ~10 |

---

## 7. Success Criteria

### Functional Requirements
- [ ] Template with {{ placeholders }} renders correctly with supplied merge data
- [ ] Missing required variables produce clear 422 validation errors
- [ ] Type-mismatched variables produce clear 422 validation errors
- [ ] Substitution only occurs in whitelisted string fields (src, text, color, background, font_family, callback)
- [ ] Expanded composition passes Pydantic re-validation after substitution
- [ ] expanded.json is stored and accessible on template-based render records
- [ ] Render uses the active template version at submission time (version pinning)
- [ ] Deleted templates return 409 on render attempts
- [ ] Non-existent templates return 404 on render attempts

### Testing Requirements
- [ ] Unit tests for variable schema validator (types, required, defaults)
- [ ] Unit tests for Jinja2 sandbox engine (expansion, strict undefined, injection prevention)
- [ ] Unit tests for whitelisted field walker (safe fields, unsafe fields, nested structures)
- [ ] Integration tests for the template render endpoint (happy path, error paths)
- [ ] Edge case tests (missing vars, deleted template, version pinning, invalid expansion)

### Non-Functional Requirements
- [ ] Template expansion completes in under 50ms for typical compositions
- [ ] No Jinja2 sandbox escapes possible through variable values or template strings

### Quality Gates
- [ ] All files ASCII-encoded
- [ ] Unix LF line endings
- [ ] Code follows project conventions (CONVENTIONS.md)
- [ ] Full test suite passes (376+ existing tests plus new tests)

---

## 8. Implementation Notes

### Key Considerations
- The existing `app/services/merge.py` uses regex-based `{{var}}` substitution on raw JSON strings. Template expansion uses Jinja2 on the composition dict structure instead, operating only on whitelisted fields. The two systems coexist: merge.py for direct render requests with the `merge` field, template_engine.py for template-based renders.
- Template compositions may contain `{{ }}` placeholders in string fields that would fail Pydantic validation if not expanded first. The active version's composition is stored as a JSON string, parsed to dict, expanded, then validated.

### Potential Challenges
- **Nested field identification**: The composition model has a deep structure (timeline -> tracks -> clips -> asset -> fields). The field walker must correctly identify safe string fields at any nesting depth without false positives.
- **Jinja2 in JSON strings**: Template variables like `{{ product_image }}` appear inside JSON string values. The walker must expand individual string values, not the entire JSON blob, to prevent structural injection.
- **Type coercion**: Variable schema types (string, number, url, boolean) must coerce merge values appropriately for JSON embedding.

### Relevant Considerations
- [P00] **Text rendering via Pillow**: Template variable substitution in text assets regenerates different text content -- the Pillow PNG rendering happens downstream in the worker after expansion, so no special handling needed here.
- [P01] **Persist input.json before enqueue**: Template renders follow the same pattern -- expanded composition is persisted as input.json before ARQ enqueue.

### Behavioral Quality Focus
Checklist active: Yes
Top behavioral risks for this session's deliverables:
- Schema-validated input and explicit error mapping for merge variable validation
- Idempotency protection: template version pinning ensures deterministic renders
- State reset or revalidation on re-entry: deleted/archived template guard on render attempts

---

## 9. Testing Strategy

### Unit Tests
- Variable schema validator: required fields, optional fields, defaults, type mismatches, unknown variables
- Jinja2 sandbox engine: basic expansion, strict undefined errors, sandbox security (no Python eval)
- Whitelisted field walker: safe field expansion, unsafe field preservation, nested composition structures, empty merge data

### Integration Tests
- Happy path: create template, render with merge data, verify 202 response, check render record has template_id/version_id
- Version pinning: create template, render, update template, render again -- both renders should reference different versions
- Error paths: render deleted template (409), render non-existent template (404), missing required vars (422), invalid expanded composition (422)

### Manual Testing
- Create a product-ad template with image, text, and price placeholders
- Render two variations with different merge data
- Verify both render records store expanded.json with different content

### Edge Cases
- Template with no variables (should render as-is)
- Merge data with extra unused variables (should succeed or warn)
- Variable value containing Jinja2 syntax (must not cause double-expansion)
- Empty string variable values
- Very long variable values

---

## 10. Dependencies

### External Libraries
- Jinja2: >= 3.1

### Other Sessions
- **Depends on**: phase02-session01-template-models-and-crud-api
- **Depended by**: phase02-session03-webhook-delivery-system (renders from templates may include callback URLs)

---

## Next Steps

Run the implement workflow step to begin AI-led implementation.
