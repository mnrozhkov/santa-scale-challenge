"""Bundled Gallery catalog drives ``GET /api/wall`` demo rows."""

from __future__ import annotations

from santa.service.demo_gallery import GALLERY_DIR, demo_wall_items, load_catalog, merge_demo_wall


def test_catalog_and_pngs_cover_g1_to_g12() -> None:
    rows = load_catalog()
    assert [row["id"] for row in rows] == [f"g{i}" for i in range(1, 13)]
    items = demo_wall_items()
    assert [item["id"] for item in items] == [f"g{i}" for i in range(1, 13)]
    for item in items:
        assert (GALLERY_DIR / item["id"] / "card.png").is_file()
        assert item["png_url"] == f"/demo/{item['id']}/card.png"
        assert item["model"] == "demo"
        if item["has_video"]:
            assert (GALLERY_DIR / item["id"] / "video.mp4").is_file()
            assert item["video_url"] == f"/demo/{item['id']}/video.mp4"


def test_merge_demo_wall_published_id_wins() -> None:
    merged = merge_demo_wall({"items": [{"id": "g1", "name": "Published Emma", "has_video": True}]})
    by_id = {item["id"]: item for item in merged["items"]}
    assert by_id["g1"]["name"] == "Published Emma"
    assert len(merged["items"]) >= 12
