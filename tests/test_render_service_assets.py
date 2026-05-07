from __future__ import annotations

from pathlib import Path

import pytest

from app.models.composition import Composition


@pytest.mark.asyncio
async def test_text_resolution_passes_safe_max_width(
    render_service,
    mock_asset_service,
    tmp_path: Path,
) -> None:
    composition = Composition.model_validate(
        {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "text",
                                    "text": "Large bottom-left title",
                                },
                                "position": "bottom-left",
                                "length": 1.0,
                            }
                        ]
                    }
                ]
            },
            "output": {"width": 1000, "height": 500},
        }
    )

    await render_service._resolve_all_assets(composition, tmp_path)

    call = mock_asset_service.resolve_asset.await_args
    assert call is not None
    assert call.kwargs["text_max_width"] == 900
