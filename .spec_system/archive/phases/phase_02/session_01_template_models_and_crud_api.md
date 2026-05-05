# Session 01: Template Models and CRUD API

**Session ID**: `phase02-session01-template-models-and-crud-api`
**Status**: Not Started
**Estimated Tasks**: ~20
**Estimated Duration**: 3-4 hours

---

## Objective

Build the template and template_versions database models, template service layer, and full CRUD API endpoints so clients can create, list, retrieve, update, and soft-delete reusable composition templates.

---

## Scope

### In Scope (MVP)
- SQLModel `templates` table: id, name, description, composition JSON, variable schema, active_version_id, is_deleted, timestamps
- SQLModel `template_versions` table: id, template_id, version number, composition JSON, variable schema, created_at
- Template service with create, list, get, update, soft-delete operations
- Version creation on update (new immutable version row, update active pointer)
- CRUD endpoints: POST /v1/templates, GET /v1/templates, GET /v1/templates/{id}, PUT /v1/templates/{id}, DELETE /v1/templates/{id}
- Pydantic request/response models for template operations
- Input validation (composition must parse as valid VidAPI composition)
- Pagination on list endpoint
- Soft-delete behavior (archived templates excluded from list, still retrievable by ID)

### Out of Scope
- Template variable substitution and rendering (Session 02)
- POST /v1/templates/{id}/renders endpoint (Session 02)
- Webhook delivery (Session 03)

---

## Prerequisites

- [ ] Phase 01 complete with working render pipeline
- [ ] SQLModel and migration tooling operational

---

## Deliverables

1. Template and TemplateVersion database models
2. Template CRUD service layer
3. Template API route handlers
4. Pydantic request/response schemas for template operations
5. Template list pagination

---

## Success Criteria

- [ ] POST /v1/templates creates a template with version 1
- [ ] GET /v1/templates returns paginated list excluding soft-deleted templates
- [ ] GET /v1/templates/{id} returns template with active version composition
- [ ] PUT /v1/templates/{id} creates a new immutable version and updates active pointer
- [ ] DELETE /v1/templates/{id} soft-deletes without destroying data
- [ ] Composition JSON is validated on create and update
