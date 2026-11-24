"""اختبار رحلة الطلب الكاملة بين الزوج والزوجة."""

from __future__ import annotations

import io

from PIL import Image
from fastapi.testclient import TestClient


def login(client: TestClient, role: str, pin: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"role": role, "pin": pin})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def png_bytes() -> bytes:
    image = Image.new("RGBA", (200, 200), (255, 0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_full_flow(client: TestClient) -> None:
    assert client.get("/api/health").json()["ok"] is True

    # الدخول ورموز خاطئة
    assert client.post("/api/auth/login", json={"role": "husband", "pin": "9999"}).status_code == 401
    husband = login(client, "husband", "1111")
    wife = login(client, "wife", "2222")
    assert client.get("/api/me", headers=husband).json()["role"] == "husband"

    # صلاحيات منفصلة
    assert client.post("/api/groups", json={"name": " x"}, headers=wife).status_code == 403
    assert client.post("/api/orders", headers=husband).status_code == 403

    # القوائم الأساسية
    catalog = client.get("/api/catalog", headers=wife).json()["groups"]
    assert len(catalog) == 8
    assert catalog[0]["name"] == "خضراوات"

    # الزوج يضيف مجموعة وصنفاً وصورة شفافة
    group = client.post(
        "/api/groups",
        json={"name": "مجموعة اختبار", "emoji": "🧪"},
        headers=husband,
    ).json()
    item = client.post(
        "/api/items",
        json={"group_id": group["id"], "name": "طماطم", "price": 7.5},
        headers=husband,
    ).json()
    upload = client.post(
        f"/api/items/{item['id']}/image",
        files={"file": ("tomato.png", png_bytes(), "image/png")},
        headers=husband,
    )
    assert upload.status_code == 200, upload.text
    image_response = client.get(f"/api/images/{item['id']}", params={"t": husband["Authorization"][7:]})
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"

    # الزوجة تفتح طلباً وتضيف أصنافاً (من القائمة + صنف مطلوب)
    order = client.post("/api/orders", headers=wife).json()
    assert order["serial"] == 1
    assert order["status"] == "draft"

    rows_response = client.put(
        f"/api/orders/{order['id']}/rows",
        json={
            "rows": [
                {"item_id": item["id"], "quantity": 2, "estimated_price": 7.5},
                {"name": "زعتر مجفف", "quantity": 1, "estimated_price": 12, "is_custom": True},
            ]
        },
        headers=wife,
    )
    assert rows_response.status_code == 200, rows_response.text
    assert rows_response.json()["summary"]["item_count"] == 2
    assert rows_response.json()["summary"]["estimated_total"] == 27

    submitted = client.post(f"/api/orders/{order['id']}/submit", headers=wife)
    assert submitted.status_code == 200, submitted.text

    # إشعار الزوج
    notes = client.get("/api/notifications", headers=husband).json()
    assert notes["unread"] == 1
    assert notes["latest"]["id"] == order["id"]

    detail = client.get(f"/api/orders/{order['id']}", headers=husband).json()
    assert detail["groups"][0]["name"] == "مجموعة اختبار"
    rows = detail["groups"][0]["rows"] + detail["custom_rows"]
    assert len(rows) == 2

    # الزوج يحدد صنفاً كمشترى ويغلق الطلب
    client.patch(
        f"/api/orders/{order['id']}/rows/{rows[0]['id']}",
        json={"purchased": True},
        headers=husband,
    )
    closed = client.post(f"/api/orders/{order['id']}/close", headers=husband)
    assert closed.status_code == 200, closed.text
    report = closed.json()
    assert len(report["purchased"]) == 1
    assert len(report["not_purchased"]) == 1
    assert client.get("/api/notifications", headers=husband).json()["unread"] == 0

    # تغيير رمز الزوجة
    changed = client.post(
        "/api/settings/pin",
        json={"current_pin": "1111", "target_role": "wife", "new_pin": "3333"},
        headers=husband,
    )
    assert changed.status_code == 200
    assert client.post("/api/auth/login", json={"role": "wife", "pin": "2222"}).status_code == 401
    login(client, "wife", "3333")

    # حذف الطلبات لتوفير المساحة
    deleted = client.request("DELETE", "/api/orders", json={"ids": [order["id"]]}, headers=husband)
    assert deleted.json()["deleted"] == 1
    assert client.get("/api/orders", headers=husband).json()["orders"] == []
