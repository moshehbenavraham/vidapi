# Session 02: S3-compatible Storage and Download Modes

**Session ID**: `phase03-session02-s3-compatible-storage-and-download-modes`
**Status**: Not Started
**Estimated Tasks**: ~20
**Estimated Duration**: 3-4 hours

---

## Objective

Implement S3-compatible artifact storage with configurable public, signed, and proxied download modes for render outputs and posters.

---

## Scope

### In Scope (MVP)
- Storage adapter interface review and S3 adapter implementation
- Configuration for endpoint URL, bucket, region, access key, secret key, path style, and URL mode
- Artifact upload for output, poster, logs, replay metadata, input, expanded composition, and compiled renderer spec
- Signed URL generation with configurable expiry
- Public URL generation for public bucket deployments
- Proxied `/v1/renders/{id}/download` path for private/local storage modes
- MinIO-compatible integration path for development
- Tests using mocked S3 client or MinIO when available

### Out of Scope
- Database migrations beyond what Session 01 provides
- Multi-region replication or lifecycle policies
- Browser upload flows or client-side signed uploads

---

## Prerequisites

- [ ] Session 01 complete or database configuration stable enough for artifact metadata
- [ ] Existing local filesystem storage adapter remains operational

---

## Deliverables

1. S3-compatible storage adapter
2. Storage configuration settings
3. Public, signed, and proxied URL generation paths
4. Download endpoint compatibility updates
5. Tests for upload, URL generation, and local adapter compatibility

---

## Success Criteria

- [ ] Render artifacts can be written to S3-compatible storage
- [ ] Signed URLs include expiry and do not leak credentials
- [ ] Public URL mode returns stable object URLs
- [ ] Proxied download mode streams output through the API
- [ ] Local filesystem storage tests continue to pass
