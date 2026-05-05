# Session 02: Template Variables and Rendering

**Session ID**: `phase02-session02-template-variables-and-rendering`
**Status**: Not Started
**Estimated Tasks**: ~18
**Estimated Duration**: 3-4 hours

---

## Objective

Implement Jinja2-based template variable substitution with strict validation, the template render endpoint, and expanded composition storage so clients can render templates with merge data and reproduce historical renders.

---

## Scope

### In Scope (MVP)
- Jinja2 SandboxedEnvironment with StrictUndefined for variable substitution
- Variable schema validation before expansion (type checks, required field enforcement)
- Whitelisted string field substitution only (prevent injection into non-string fields)
- POST /v1/templates/{id}/renders endpoint accepting merge data and optional callback
- Expanded composition validation after substitution
- Store expanded.json on render record for template-based renders
- Template version pinning: render uses the active version at submission time
- Error handling for missing variables, type mismatches, and invalid expanded compositions

### Out of Scope
- Webhook callback delivery (Session 03)
- Transition and positioning enhancements (Session 04)
- Non-string variable types beyond basic coercion

---

## Prerequisites

- [ ] Session 01 complete (template CRUD and models)
- [ ] Existing render pipeline accepts compositions programmatically

---

## Deliverables

1. Jinja2 sandbox variable substitution engine
2. Variable schema validator
3. Whitelisted field walker for safe substitution
4. POST /v1/templates/{id}/renders route handler
5. Expanded composition storage on render records

---

## Success Criteria

- [ ] Template with {{ placeholders }} renders correctly with supplied merge data
- [ ] Missing required variables produce clear validation errors
- [ ] Substitution only occurs in whitelisted string fields
- [ ] Expanded composition is validated after substitution
- [ ] expanded.json is stored for template-based renders
- [ ] Rendering uses the active template version at submission time
