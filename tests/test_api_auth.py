from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.db import render_crud
from app.models.render import RenderStatus
from app.storage.base import ArtifactType

INVALID_API_KEY = "wrong-test-key"

TEMPLATE_COMPOSITION = {
    "timeline": {
        "background": "#000000",
        "tracks": [
            {
                "clips": [
                    {
                        "asset": {
                            "type": "text",
                            "text": "{{ headline }}",
                        },
                        "start": 0.0,
                        "length": 2.0,
                    }
                ]
            }
        ],
    },
    "output": {"format": "mp4", "width": 1280, "height": 720},
}

TEMPLATE_PAYLOAD = {
    "name": "Auth Template",
    "description": "Template used by auth tests",
    "composition": TEMPLATE_COMPOSITION,
    "variable_schema": {"headline": {"type": "string", "required": True}},
}


async def _mark_render_succeeded(session, render_id: str) -> None:
    await render_crud.update_render_status(session, render_id, RenderStatus.FETCHING)
    await render_crud.update_render_status(session, render_id, RenderStatus.COMPILING)
    await render_crud.update_render_status(session, render_id, RenderStatus.RENDERING)
    await render_crud.update_render_status(session, render_id, RenderStatus.UPLOADING)
    await render_crud.update_render_status(session, render_id, RenderStatus.SUCCEEDED)


def _request_payload(name: str, sample_composition: dict) -> dict | None:
    if name == "render":
        return sample_composition
    if name == "template":
        return TEMPLATE_PAYLOAD
    if name == "template_render":
        return {"merge": {"headline": "Authorized"}}
    return None


PROTECTED_REQUESTS = [
    ("get", "/v1/renders", None),
    ("post", "/v1/renders", "render"),
    ("get", "/v1/renders/render_missing", None),
    ("delete", "/v1/renders/render_missing", None),
    ("get", "/v1/renders/render_missing/download", None),
    ("get", "/v1/renders/render_missing/poster", None),
    ("get", "/v1/renders/render_missing/captions", None),
    ("get", "/v1/templates", None),
    ("post", "/v1/templates", "template"),
    ("post", "/v1/templates/tmpl_missing/renders", "template_render"),
]


@pytest.mark.asyncio
async def test_disabled_auth_client_remains_public(client: AsyncClient) -> None:
    response = await client.get("/v1/renders")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_openapi_omits_api_key_scheme_when_auth_disabled(
    client: AsyncClient,
) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    assert "APIKeyAuth" not in schema.get("components", {}).get(
        "securitySchemes",
        {},
    )
    assert "security" not in schema["paths"]["/v1/renders"]["post"]
    assert "API key auth is disabled" in schema["info"]["description"]


@pytest.mark.asyncio
async def test_health_routes_remain_public_when_auth_enabled(
    auth_client: AsyncClient,
) -> None:
    for path in ("/health", "/v1/health"):
        response = await auth_client.get(path)
        assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path", "payload_name"), PROTECTED_REQUESTS)
async def test_protected_routes_reject_missing_api_key(
    auth_client: AsyncClient,
    sample_composition: dict,
    method: str,
    path: str,
    payload_name: str | None,
) -> None:
    response = await auth_client.request(
        method.upper(),
        path,
        json=_request_payload(payload_name or "", sample_composition),
    )

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert body["error"]["context"] is None
    assert "X-API-Key" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path", "payload_name"), PROTECTED_REQUESTS)
async def test_protected_routes_reject_invalid_api_key_without_leaking_value(
    auth_client: AsyncClient,
    sample_composition: dict,
    method: str,
    path: str,
    payload_name: str | None,
) -> None:
    response = await auth_client.request(
        method.upper(),
        path,
        json=_request_payload(payload_name or "", sample_composition),
        headers={"X-API-Key": INVALID_API_KEY},
    )

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "INVALID_API_KEY"
    assert body["error"]["context"] is None
    assert INVALID_API_KEY not in response.text


@pytest.mark.asyncio
async def test_valid_api_key_allows_render_status_list_cancel_and_artifacts(
    auth_client: AsyncClient,
    auth_headers: dict[str, str],
    sample_composition: dict,
    db_session,
    test_storage,
) -> None:
    create_response = await auth_client.post(
        "/v1/renders",
        json=sample_composition,
        headers=auth_headers,
    )
    assert create_response.status_code == 202
    created_render_id = create_response.json()["id"]

    status_response = await auth_client.get(
        f"/v1/renders/{created_render_id}",
        headers=auth_headers,
    )
    assert status_response.status_code == 200

    list_response = await auth_client.get("/v1/renders", headers=auth_headers)
    assert list_response.status_code == 200
    assert list_response.json()["total"] >= 1

    queued_render = await render_crud.create_render(db_session)
    cancel_response = await auth_client.delete(
        f"/v1/renders/{queued_render.id}",
        headers=auth_headers,
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"

    artifact_render = await render_crud.create_render(db_session)
    output_uri = await test_storage.publish_bytes(
        artifact_render.id,
        ArtifactType.OUTPUT,
        b"video-bytes",
    )
    poster_uri = await test_storage.publish_bytes(
        artifact_render.id,
        ArtifactType.POSTER,
        b"poster-bytes",
    )
    await render_crud.update_render_paths(
        db_session,
        artifact_render.id,
        output_path=output_uri,
        poster_path=poster_uri,
    )
    await _mark_render_succeeded(db_session, artifact_render.id)

    download_response = await auth_client.get(
        f"/v1/renders/{artifact_render.id}/download",
        headers=auth_headers,
    )
    assert download_response.status_code == 200
    assert download_response.content == b"video-bytes"

    poster_response = await auth_client.get(
        f"/v1/renders/{artifact_render.id}/poster",
        headers=auth_headers,
    )
    assert poster_response.status_code == 200
    assert poster_response.content == b"poster-bytes"


@pytest.mark.asyncio
async def test_valid_api_key_allows_template_crud_and_template_render(
    auth_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    create_response = await auth_client.post(
        "/v1/templates",
        json=TEMPLATE_PAYLOAD,
        headers=auth_headers,
    )
    assert create_response.status_code == 201
    template_id = create_response.json()["id"]

    list_response = await auth_client.get("/v1/templates", headers=auth_headers)
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    get_response = await auth_client.get(
        f"/v1/templates/{template_id}",
        headers=auth_headers,
    )
    assert get_response.status_code == 200

    update_response = await auth_client.put(
        f"/v1/templates/{template_id}",
        json={"description": "Updated by auth test"},
        headers=auth_headers,
    )
    assert update_response.status_code == 200

    render_response = await auth_client.post(
        f"/v1/templates/{template_id}/renders",
        json={"merge": {"headline": "Authorized render"}},
        headers=auth_headers,
    )
    assert render_response.status_code == 202

    delete_response = await auth_client.delete(
        f"/v1/templates/{template_id}",
        headers=auth_headers,
    )
    assert delete_response.status_code == 200


@pytest.mark.asyncio
async def test_download_and_poster_require_auth_before_artifact_lookup(
    auth_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    for path in (
        "/v1/renders/render_does_not_exist/download",
        "/v1/renders/render_does_not_exist/poster",
        "/v1/renders/render_does_not_exist/captions",
    ):
        missing_key_response = await auth_client.get(path)
        invalid_key_response = await auth_client.get(
            path,
            headers={"X-API-Key": INVALID_API_KEY},
        )
        valid_key_response = await auth_client.get(path, headers=auth_headers)

        assert missing_key_response.status_code == 401
        assert invalid_key_response.status_code == 403
        assert valid_key_response.status_code == 404


@pytest.mark.asyncio
async def test_openapi_documents_api_key_scheme_for_protected_routes(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    security_scheme = schema["components"]["securitySchemes"]["APIKeyAuth"]
    assert security_scheme["type"] == "apiKey"
    assert security_scheme["in"] == "header"
    assert security_scheme["name"] == "X-API-Key"

    assert {"APIKeyAuth": []} in schema["paths"]["/v1/renders"]["post"]["security"]
    assert {"APIKeyAuth": []} in schema["paths"]["/v1/templates"]["post"]["security"]
    assert "security" not in schema["paths"]["/v1/health"]["get"]
