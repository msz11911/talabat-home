"""Seed the exact catalog order from the attached image, plus one thumbnail per item.

The script is safe to re-run: it replaces the current catalog with the rows in
scripts/catalog_final.json and uploads a small white-background PNG for every row.

Usage:
  python scripts/seed_catalog.py --yes
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont

from item_emoji import render_thumbnail as _render_picture_thumbnail

HERE = Path(__file__).resolve().parent
CATALOG_PATH = HERE / "catalog_final.json"
DEFAULT_API_BASE = "https://talabat-home.vercel.app"

GROUP_COLORS = {
    "101": "#3F9C62", "102": "#D9784E", "103": "#D6A93B", "104": "#9A7B4F",
    "105": "#7B8E4B", "106": "#B45A55", "107": "#B87A9B", "108": "#C58B4D",
    "109": "#8C72A8", "110": "#5B8CA8", "111": "#D08B3E", "112": "#5B9AA6",
    "113": "#7A8796", "114": "#C47A8A", "115": "#6F7FBF",
}

FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\arialbd.ttf"),
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = FONT_CANDIDATES if bold else list(reversed(FONT_CANDIDATES))
    for candidate in candidates:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size)
            except OSError:
                continue
    return ImageFont.load_default()


def display_text(text: str) -> str:
    """Shape Arabic and apply bidi so Pillow draws it in visual order."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        width = draw.textbbox((0, 0), display_text(trial), font=font)[2]
        if current and width > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


THUMB_SIZE = 256
THUMB_SCALE = 3  # render large, then downsample for clean anti-aliased edges


def render_thumbnail(item: dict[str, Any]) -> bytes:
    """A crisp 256x256 white-background *picture* for one catalog item."""
    return _render_picture_thumbnail(item)


def make_client(base: str) -> tuple[str, dict[str, str]]:
    """Return (base, auth headers) after logging in as the husband."""
    pin = os.environ.get("HUSBAND_PIN", "1234")
    response = requests.post(
        f"{base}/api/auth/login",
        json={"role": "husband", "pin": pin},
        timeout=90,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"login failed: {response.status_code} {response.text[:300]}")
    token = response.json()["token"]
    return base, {"Authorization": f"Bearer {token}"}


def api(
    base: str,
    headers: dict[str, str],
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
) -> Any:
    response = requests.request(
        method,
        f"{base}{path}",
        headers=headers,
        json=payload,
        files=files,
        timeout=90,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"{method} {path} failed: {response.status_code} {response.text[:300]}")
    if not response.content:
        return None
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default=os.environ.get("TALABAT_API_BASE", DEFAULT_API_BASE))
    parser.add_argument("--thumb-dir", type=Path, help="Optional folder to also save generated thumbnails")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args()

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    groups = catalog["groups"]
    items = catalog["items"]

    if not args.yes:
        print(f"سيتم استبدال الكتالوج الحالي بـ {len(groups)} مجموعة و{len(items)} صنفًا.")
        if input("اكتب yes للمتابعة: ").strip().lower() not in {"yes", "y"}:
            print("تم الإلغاء.")
            return 0

    base, headers = make_client(args.api_base.rstrip("/"))

    old = api(base, headers, "GET", "/api/catalog")
    for group in old["groups"]:
        api(base, headers, "DELETE", f"/api/groups/{group['id']}")
    print(f"تم حذف {len(old['groups'])} مجموعة قديمة.")

    group_ids: dict[str, int] = {}
    for group in groups:
        created = api(
            base,
            headers,
            "POST",
            "/api/groups",
            payload={
                "name": group["name"],
                "emoji": group["emoji"],
                "sort_order": group["sort_order"],
            },
        )
        group_ids[group["code"]] = created["id"]

    item_ids: list[int] = []
    for item in items:
        created = api(
            base,
            headers,
            "POST",
            "/api/items",
            payload={
                "group_id": group_ids[item["group_code"]],
                "name": item["name"],
                "price": 0,
                "sort_order": item["sort_order"],
            },
        )
        item_ids.append(created["id"])
    print(f"تم إنشاء {len(item_ids)} صنفًا.")

    if args.thumb_dir:
        args.thumb_dir.mkdir(parents=True, exist_ok=True)

    for index, (item, item_id) in enumerate(zip(items, item_ids), start=1):
        png = render_thumbnail(item)
        if args.thumb_dir:
            safe = re.sub(r"[^A-Za-z0-9_-]", "_", item["key"])
            (args.thumb_dir / f"{safe}.png").write_bytes(png)
        api(
            base,
            headers,
            "POST",
            f"/api/items/{item_id}/image",
            files={"file": ("thumb.png", png, "image/png")},
        )
        if index % 25 == 0 or index == len(items):
            print(f"تم رفع {index}/{len(items)} صورة.")

    final = api(base, headers, "GET", "/api/catalog")
    final_groups = final["groups"]
    actual_names = [
        [item["name"] for item in group["items"]]
        for group in sorted(final_groups, key=lambda g: g["sort_order"])
    ]
    expected_names = [
        [item["name"] for item in items if item["group_code"] == group["code"]]
        for group in groups
    ]
    total = sum(len(names) for names in actual_names)
    with_images = sum(1 for group in final_groups for item in group["items"] if item["has_image"])
    if actual_names != expected_names or total != len(items) or with_images != len(items):
        raise RuntimeError(
            f"verification failed: groups={len(final_groups)} items={total} images={with_images}"
        )
    print(f"تم التحقق: {len(final_groups)} مجموعة، {total} صنفًا، {with_images} صورة.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
