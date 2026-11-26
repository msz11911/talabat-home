"""Re-upload higher-quality thumbnails without changing the live catalog.

Usage:
  python scripts/refresh_thumbnails.py --yes
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seed_catalog import (  # noqa: E402
    CATALOG_PATH,
    DEFAULT_API_BASE,
    api,
    make_client,
    render_thumbnail,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default=os.environ.get("TALABAT_API_BASE", DEFAULT_API_BASE))
    parser.add_argument("--yes", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    expected = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    base, headers = make_client(args.api_base.rstrip("/"))
    live = api(base, headers, "GET", "/api/catalog")

    live_by_name = {group["name"]: group for group in live["groups"]}
    expected_groups = expected["groups"]
    if len(live_by_name) != len(expected_groups):
        raise RuntimeError(
            f"group count changed: live={len(live_by_name)} expected={len(expected_groups)}; "
            "re-run seed_catalog.py instead"
        )

    pairs: list[tuple[dict, int]] = []
    for expected_group in expected_groups:
        group_name = expected_group["name"]
        live_group = live_by_name.get(group_name)
        if live_group is None:
            raise RuntimeError(f"group missing in live catalog: {group_name!r}")
        live_items = sorted(live_group["items"], key=lambda item: item["sort_order"])
        expected_items = [
            item
            for item in expected["items"]
            if item["group_code"] == expected_group["code"]
        ]
        expected_items.sort(key=lambda item: item["sort_order"])
        if len(live_items) != len(expected_items):
            raise RuntimeError(
                f"item count changed in {group_name}: "
                f"live={len(live_items)} expected={len(expected_items)}"
            )
        for live_item, expected_item in zip(live_items, expected_items):
            if live_item["name"] != expected_item["name"]:
                raise RuntimeError(
                    f"item mismatch in {group_name}: "
                    f"{live_item['name']!r} != {expected_item['name']!r}"
                )
            pairs.append((expected_item, live_item["id"]))

    if not args.yes:
        print(f"سيتم تحديث صور {len(pairs)} صنفاً دون تغيير الكتالوج.")
        if input("اكتب yes للمتابعة: ").strip().lower() not in {"yes", "y"}:
            print("تم الإلغاء.")
            return 0

    for index, (item, item_id) in enumerate(pairs, start=1):
        png = render_thumbnail(item)
        api(
            base,
            headers,
            "POST",
            f"/api/items/{item_id}/image",
            files={"file": ("thumb.png", png, "image/png")},
        )
        if index % 25 == 0 or index == len(pairs):
            print(f"تم رفع {index}/{len(pairs)} صورة.")

    check_ids = [item_id for _, item_id in pairs[:3]]
    for item_id in check_ids:
        response = requests.get(
            f"{base}/api/images/{item_id}",
            params={"t": headers["Authorization"].split(" ", 1)[1]},
            timeout=90,
        )
        if response.status_code != 200:
            raise RuntimeError(f"image check failed for {item_id}: {response.status_code}")
        with Image.open(io.BytesIO(response.content)) as image:
            if image.size != (256, 256):
                raise RuntimeError(f"unexpected image size for {item_id}: {image.size}")
    print(f"تم التحقق: {len(pairs)} صورة بدقة 256×256.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
