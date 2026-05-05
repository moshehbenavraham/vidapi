"""Integration tests for POST /v1/templates/{id}/renders endpoint."""

from __future__ import annotations

import pytest

from app.db import render_crud

TEMPLATE_COMPOSITION = {
    "timeline": {
        "background": "#000000",
        "tracks": [
            {
                "clips": [
                    {
                        "asset": {
                            "type": "image",
                            "src": "{{ product_image }}",
                        },
                        "start": 0.0,
                        "length": 3.0,
                    }
                ]
            },
            {
                "clips": [
                    {
                        "asset": {
                            "type": "text",
                            "text": "{{ headline }}",
                            "color": "{{ text_color }}",
                        },
                        "start": 0.5,
                        "length": 2.0,
                    }
                ]
            },
        ],
    },
    "output": {"format": "mp4", "width": 1920, "height": 1080},
}

VARIABLE_SCHEMA = {
    "product_image": {"type": "url", "required": True},
    "headline": {"type": "string", "required": True},
    "text_color": {"type": "string", "default": "#ffffff"},
}


_SENTINEL = object()


async def _create_template(client, composition=None, variable_schema=_SENTINEL):
    payload = {
        "name": "Product Ad",
        "description": "A product advertisement template",
        "composition": composition or TEMPLATE_COMPOSITION,
        "variable_schema": (
            VARIABLE_SCHEMA if variable_schema is _SENTINEL else variable_schema
        ),
    }
    resp = await client.post("/v1/templates", json=payload)
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Happy Path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_template_happy_path(client):
    tmpl = await _create_template(client)
    template_id = tmpl["id"]

    resp = await client.post(
        f"/v1/templates/{template_id}/renders",
        json={
            "merge": {
                "product_image": "https://example.com/product.jpg",
                "headline": "Buy Now!",
            }
        },
    )
    assert resp.status_code == 202

    data = resp.json()
    assert data["id"].startswith("render_")
    assert data["status"] == "queued"
    assert data["progress"] == 0
    assert data["template_id"] == template_id
    assert data["template_version_id"] == tmpl["active_version"]["id"]


@pytest.mark.asyncio
async def test_render_template_persists_input_and_expanded_through_storage(
    client,
    db_session,
    test_storage,
):
    tmpl = await _create_template(client)
    template_id = tmpl["id"]

    resp = await client.post(
        f"/v1/templates/{template_id}/renders",
        json={
            "merge": {
                "product_image": "https://example.com/product.jpg",
                "headline": "Buy Now!",
            }
        },
    )
    assert resp.status_code == 202
    render_id = resp.json()["id"]

    render = await render_crud.get_render_by_id(db_session, render_id)

    assert render is not None
    assert render.input_path is not None
    assert render.expanded_path is not None
    assert await test_storage.read_uri(render.input_path)
    expanded_json = await test_storage.read_uri(render.expanded_path)
    assert b"Buy Now!" in expanded_json


@pytest.mark.asyncio
async def test_render_template_includes_template_fields_in_status(client):
    tmpl = await _create_template(client)
    template_id = tmpl["id"]

    render_resp = await client.post(
        f"/v1/templates/{template_id}/renders",
        json={
            "merge": {
                "product_image": "https://example.com/product.jpg",
                "headline": "Buy Now!",
            }
        },
    )
    render_id = render_resp.json()["id"]

    status_resp = await client.get(f"/v1/renders/{render_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["template_id"] == template_id
    assert data["template_version_id"] == tmpl["active_version"]["id"]


@pytest.mark.asyncio
async def test_render_template_with_defaults(client):
    tmpl = await _create_template(client)
    template_id = tmpl["id"]

    resp = await client.post(
        f"/v1/templates/{template_id}/renders",
        json={
            "merge": {
                "product_image": "https://example.com/product.jpg",
                "headline": "Sale!",
            }
        },
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_render_template_with_all_variables(client):
    tmpl = await _create_template(client)
    template_id = tmpl["id"]

    resp = await client.post(
        f"/v1/templates/{template_id}/renders",
        json={
            "merge": {
                "product_image": "https://example.com/product.jpg",
                "headline": "Premium!",
                "text_color": "#ff0000",
            }
        },
    )
    assert resp.status_code == 202


# ---------------------------------------------------------------------------
# Version Pinning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_version_pinning_after_update(client):
    tmpl = await _create_template(client)
    template_id = tmpl["id"]
    v1_id = tmpl["active_version"]["id"]

    resp1 = await client.post(
        f"/v1/templates/{template_id}/renders",
        json={
            "merge": {
                "product_image": "https://example.com/v1.jpg",
                "headline": "V1",
            }
        },
    )
    assert resp1.status_code == 202
    assert resp1.json()["template_version_id"] == v1_id

    update_resp = await client.put(
        f"/v1/templates/{template_id}",
        json={"composition": TEMPLATE_COMPOSITION},
    )
    assert update_resp.status_code == 200
    v2_id = update_resp.json()["active_version"]["id"]
    assert v2_id != v1_id

    resp2 = await client.post(
        f"/v1/templates/{template_id}/renders",
        json={
            "merge": {
                "product_image": "https://example.com/v2.jpg",
                "headline": "V2",
            }
        },
    )
    assert resp2.status_code == 202
    assert resp2.json()["template_version_id"] == v2_id


# ---------------------------------------------------------------------------
# Error Paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_nonexistent_template_404(client):
    resp = await client.post(
        "/v1/templates/tmpl_does_not_exist/renders",
        json={"merge": {}},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_render_deleted_template_409(client):
    tmpl = await _create_template(client)
    template_id = tmpl["id"]

    del_resp = await client.delete(f"/v1/templates/{template_id}")
    assert del_resp.status_code == 200

    resp = await client.post(
        f"/v1/templates/{template_id}/renders",
        json={
            "merge": {
                "product_image": "https://example.com/x.jpg",
                "headline": "No",
            }
        },
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_render_missing_required_vars_422(client):
    tmpl = await _create_template(client)
    template_id = tmpl["id"]

    resp = await client.post(
        f"/v1/templates/{template_id}/renders",
        json={"merge": {}},
    )
    assert resp.status_code == 422
    data = resp.json()["detail"]
    assert "errors" in data
    assert any("Missing required" in e for e in data["errors"])


@pytest.mark.asyncio
async def test_render_type_mismatch_422(client):
    schema = {"count": {"type": "number", "required": True}}
    comp = {
        "timeline": {
            "tracks": [
                {
                    "clips": [
                        {
                            "asset": {
                                "type": "text",
                                "text": "{{ count }}",
                            },
                            "start": 0.0,
                            "length": 2.0,
                        }
                    ]
                }
            ]
        },
        "output": {"format": "mp4", "width": 1920, "height": 1080},
    }
    tmpl = await _create_template(client, composition=comp, variable_schema=schema)
    template_id = tmpl["id"]

    resp = await client.post(
        f"/v1/templates/{template_id}/renders",
        json={"merge": {"count": [1, 2, 3]}},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_template_with_no_variables(client):
    comp = {
        "timeline": {
            "tracks": [
                {
                    "clips": [
                        {
                            "asset": {
                                "type": "image",
                                "src": "https://example.com/static.jpg",
                            },
                            "start": 0.0,
                            "length": 3.0,
                        }
                    ]
                }
            ]
        },
        "output": {"format": "mp4", "width": 1920, "height": 1080},
    }
    tmpl = await _create_template(client, composition=comp, variable_schema=None)
    template_id = tmpl["id"]

    resp = await client.post(
        f"/v1/templates/{template_id}/renders",
        json={"merge": {}},
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_extra_unused_variables_succeed(client):
    tmpl = await _create_template(client)
    template_id = tmpl["id"]

    resp = await client.post(
        f"/v1/templates/{template_id}/renders",
        json={
            "merge": {
                "product_image": "https://example.com/product.jpg",
                "headline": "Works!",
                "unused_var": "should be fine",
            }
        },
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_jinja2_syntax_in_variable_value(client):
    tmpl = await _create_template(client)
    template_id = tmpl["id"]

    resp = await client.post(
        f"/v1/templates/{template_id}/renders",
        json={
            "merge": {
                "product_image": "https://example.com/product.jpg",
                "headline": "{{ not_a_real_variable }}",
            }
        },
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_empty_merge_body(client):
    tmpl = await _create_template(client)
    template_id = tmpl["id"]

    resp = await client.post(
        f"/v1/templates/{template_id}/renders",
        json={},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_render_appears_in_render_list(client):
    tmpl = await _create_template(client)
    template_id = tmpl["id"]

    await client.post(
        f"/v1/templates/{template_id}/renders",
        json={
            "merge": {
                "product_image": "https://example.com/product.jpg",
                "headline": "Listed!",
            }
        },
    )

    list_resp = await client.get("/v1/renders")
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    template_renders = [i for i in items if i["template_id"] == template_id]
    assert len(template_renders) >= 1
    assert template_renders[0]["template_version_id"] is not None


@pytest.mark.asyncio
async def test_render_with_callback(client):
    tmpl = await _create_template(client)
    template_id = tmpl["id"]

    resp = await client.post(
        f"/v1/templates/{template_id}/renders",
        json={
            "merge": {
                "product_image": "https://example.com/product.jpg",
                "headline": "With callback",
            },
            "callback": "https://example.com/webhook",
        },
    )
    assert resp.status_code == 202
