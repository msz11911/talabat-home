"""Talabat Home API — قائمة مشتريات مشتركة بين الزوج والزوجة."""

from __future__ import annotations

import csv
import io
import os
import re
import secrets
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from config import (
    CORS_ORIGINS,
    DEFAULT_GROUPS,
    MAX_IMAGE_BYTES,
    MAX_IMAGE_SIDE,
    MAX_IMPORT_BYTES,
    MAX_IMPORT_ROWS,
    MAX_ROWS_PER_ORDER,
    PIN_MIN_LENGTH,
    ROLE_NAMES,
    WEB_DIR,
)
from db import SessionLocal, get_db, init_db
from models import Group, Item, Notification, Order, OrderRow, Setting, utcnow
from schemas import (
    DeleteOrdersIn,
    GroupIn,
    GroupPatch,
    ItemIn,
    ItemPatch,
    LoginIn,
    PinChangeIn,
    PurchasedPatch,
    RowsReplaceIn,
)
from security import (
    decode_token,
    hash_pin,
    make_token,
    require_husband,
    require_wife,
    role_from_request,
    verify_pin,
)

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
DEFAULT_PINS = {"husband": "1111", "wife": "2222"}


def seed_defaults(db: Session) -> None:
    """المجموعات الأساسية ورموز الدخول عند أول تشغيل."""
    if db.scalar(select(func.count()).select_from(Group)) == 0:
        for index, (name, emoji) in enumerate(DEFAULT_GROUPS):
            db.add(Group(name=name, emoji=emoji, sort_order=index))
        db.commit()

    generated: list[str] = []
    for role in ("husband", "wife"):
        key = f"pin_{role}"
        stored = db.get(Setting, key)
        env_pin = os.getenv(f"{role.upper()}_PIN", DEFAULT_PINS[role]).strip()
        if env_pin:
            if not env_pin.isdigit() or len(env_pin) < PIN_MIN_LENGTH:
                print(f"[talabat] تحذير: {role.upper()}_PIN يجب أن يكون أرقاماً (4+)؛ تم تجاهله")
            elif stored is None:
                db.add(Setting(key=key, value=hash_pin(env_pin)))
                stored = None
            elif not verify_pin(env_pin, stored.value):
                stored.value = hash_pin(env_pin)
        elif stored is None:
            pin = "".join(secrets.choice("0123456789") for _ in range(4))
            db.add(Setting(key=key, value=hash_pin(pin)))
            generated.append(f"{ROLE_NAMES[role]}: {pin}")
    db.commit()

    if generated:
        print("\n" + "=" * 52)
        print("رموز الدخول الأولى (احفظها الآن):")
        for line in generated:
            print(f"  {line}")
        print("=" * 52 + "\n")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed_defaults(db)
        seed_notifications(db)
    yield


app = FastAPI(
    title="Talabat Home API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS.split(",")] if CORS_ORIGINS != "*" else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

DbDep = Annotated[Session, Depends(get_db)]
AnyRole = Annotated[str, Depends(role_from_request)]
Husband = Annotated[str, Depends(require_husband)]
Wife = Annotated[str, Depends(require_wife)]


def iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def notif_out(note: Notification) -> dict[str, Any]:
    return {
        "id": note.id,
        "role": note.role,
        "kind": note.kind,
        "title": note.title,
        "body": note.body,
        "order_id": note.order_id,
        "created_at": iso(note.created_at),
        "seen": bool(note.seen),
    }


def notify(
    db: Session,
    role: str,
    title: str,
    body: str,
    *,
    kind: str = "",
    order_id: int | None = None,
) -> Notification:
    note = Notification(
        role=role,
        kind=kind,
        title=title[:160],
        body=body,
        order_id=order_id,
        seen=False,
    )
    db.add(note)
    return note


def seed_notifications(db: Session) -> None:
    """ترحيل خفيف: إشعارات للطلبات المرسلة قبل تفعيل صندوق الإشعارات."""
    existing = set(
        db.scalars(
            select(Notification).where(
                Notification.role == "husband", Notification.kind == "new_order"
            )
        ).all()
    )
    covered = {note.order_id for note in existing}
    for order in db.scalars(select(Order).where(Order.status == "submitted")).all():
        if order.id in covered:
            continue
        notify(
            db,
            "husband",
            "طلب جديد 🛒",
            f"{ROLE_NAMES['wife']} أرسلت الطلب #{order.serial}",
            kind="new_order",
            order_id=order.id,
        )
    db.commit()


def item_out(item: Item) -> dict[str, Any]:
    return {
        "id": item.id,
        "group_id": item.group_id,
        "name": item.name,
        "price": round(item.price, 2),
        "has_image": bool(item.image_blob),
        "sort_order": item.sort_order,
    }


def group_out(group: Group) -> dict[str, Any]:
    return {
        "id": group.id,
        "name": group.name,
        "emoji": group.emoji,
        "sort_order": group.sort_order,
        "items": [item_out(i) for i in group.items],
    }


def get_item_or_404(db: Session, item_id: int) -> Item:
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="الصنف غير موجود")
    return item


def get_group_or_404(db: Session, group_id: int) -> Group:
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="المجموعة غير موجودة")
    return group


def get_order_or_404(db: Session, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    return order


def row_out(row: OrderRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "item_id": row.item_id,
        "name": row.name,
        "quantity": row.quantity,
        "estimated_price": round(row.estimated_price, 2),
        "is_custom": row.is_custom,
        "purchased": row.purchased,
        "note": row.note,
        "has_image": bool(row.item and row.item.image_blob),
    }


def order_summary(rows: list[OrderRow]) -> dict[str, Any]:
    return {
        "item_count": len(rows),
        "purchased_count": sum(1 for r in rows if r.purchased),
        "total_quantity": round(sum(r.quantity for r in rows), 2),
        "estimated_total": round(sum(r.quantity * r.estimated_price for r in rows), 2),
    }


def order_out(db: Session, order: Order) -> dict[str, Any]:
    item_ids = [r.item_id for r in order.rows if r.item_id is not None]
    items = (
        db.scalars(select(Item).where(Item.id.in_(item_ids))).all() if item_ids else []
    )
    item_map = {item.id: item for item in items}

    groups: OrderedDict[int, dict[str, Any]] = OrderedDict()
    custom_rows: list[dict[str, Any]] = []
    for row in order.rows:
        data = row_out(row)
        item = item_map.get(row.item_id) if row.item_id is not None else None
        if row.is_custom or item is None:
            custom_rows.append(data)
            continue
        group = item.group
        groups.setdefault(
            group.id,
            {"id": group.id, "name": group.name, "emoji": group.emoji, "rows": []},
        )["rows"].append(data)

    return {
        "id": order.id,
        "serial": order.serial,
        "created_at": iso(order.created_at),
        "submitted_at": iso(order.submitted_at),
        "closed_at": iso(order.closed_at),
        "status": order.status,
        "seen_by_husband": bool(order.seen_by_husband),
        "groups": list(groups.values()),
        "custom_rows": custom_rows,
        "summary": order_summary(order.rows),
    }


def order_list_out(order: Order) -> dict[str, Any]:
    rows = order.rows
    return {
        "id": order.id,
        "serial": order.serial,
        "created_at": iso(order.created_at),
        "submitted_at": iso(order.submitted_at),
        "status": order.status,
        "seen_by_husband": bool(order.seen_by_husband),
        "item_count": len(rows),
        "purchased_count": sum(1 for r in rows if r.purchased),
        "estimated_total": round(sum(r.quantity * r.estimated_price for r in rows), 2),
    }


# --------------------------------------------------------------------------
# الدخول والإعدادات
# --------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "app": "Talabat Home", "version": "1.0.0"}


@app.post("/api/auth/login")
def login(payload: LoginIn, db: DbDep) -> dict[str, Any]:
    stored = db.get(Setting, f"pin_{payload.role}")
    if stored is None or not verify_pin(payload.pin, stored.value):
        raise HTTPException(status_code=401, detail="رمز الدخول غير صحيح")
    return {
        "token": make_token(payload.role),
        "role": payload.role,
        "display_name": ROLE_NAMES[payload.role],
    }


@app.get("/api/me")
def me(role: AnyRole) -> dict[str, Any]:
    return {"role": role, "display_name": ROLE_NAMES[role]}


@app.post("/api/settings/pin")
def change_pin(payload: PinChangeIn, db: DbDep, _role: Husband) -> dict[str, Any]:
    current = db.get(Setting, "pin_husband")
    if current is None or not verify_pin(payload.current_pin, current.value):
        raise HTTPException(status_code=401, detail="رمز الزوج الحالي غير صحيح")
    target = db.get(Setting, f"pin_{payload.target_role}")
    if target is None:
        target = Setting(key=f"pin_{payload.target_role}", value="")
        db.add(target)
    target.value = hash_pin(payload.new_pin)
    db.commit()
    return {"ok": True, "role": payload.target_role}


# --------------------------------------------------------------------------
# القوائم والأصناف (الزوج فقط للتعديل)
# --------------------------------------------------------------------------


@app.get("/api/catalog")
def catalog(db: DbDep, _role: AnyRole) -> dict[str, Any]:
    groups = db.scalars(select(Group).order_by(Group.sort_order, Group.id)).all()
    return {"groups": [group_out(g) for g in groups]}


IMPORT_ALIASES: dict[str, set[str]] = {
    "group": {"group", "groups", "groupname", "category", "المجموعة", "مجموعة", "القسم", "قسم", "الفئة"},
    "name": {"name", "item", "items", "itemname", "product", "الصنف", "اسمالصنف", "المنتج", "الصنفالمطلوب"},
    "price": {"price", "cost", "السعر", "السعرالتقديري"},
    "order": {"order", "sortorder", "الترتيب", "ترتيب"},
    "emoji": {"emoji", "symbol", "الرمز"},
}


def normalized_header(value: Any) -> str:
    return re.sub(r"[\s_\-]+", "", str(value or "").strip().lower())


def parse_import_rows(filename: str, raw: bytes) -> list[dict[str, Any]]:
    """Parse an .xlsx/.csv sheet into normalized group/item rows."""
    suffix = Path(filename).suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise HTTPException(status_code=500, detail="مكتبة Excel غير مثبتة على السيرفر") from exc
        try:
            workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            sheet = workbook.active
            table = [[cell for cell in row] for row in sheet.iter_rows(values_only=True)]
            workbook.close()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="تعذّر قراءة ملف Excel") from exc
    elif suffix == ".csv":
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1256", errors="replace")
        table = [row for row in csv.reader(io.StringIO(text))]
    else:
        raise HTTPException(status_code=415, detail="ارفع ملف Excel بصيغة xlsx أو csv")

    if not table:
        raise HTTPException(status_code=400, detail="الملف فارغ")

    columns: dict[str, int] = {}
    first = [normalized_header(cell) for cell in table[0]]
    header_found = any(
        value in IMPORT_ALIASES["group"] or value in IMPORT_ALIASES["name"] for value in first
    )
    if header_found:
        for key, aliases in IMPORT_ALIASES.items():
            for index, value in enumerate(first):
                if value in aliases:
                    columns[key] = index
                    break
        table = table[1:]
    else:
        columns = {"group": 0, "name": 1, "price": 2, "order": 3, "emoji": 4}

    if "group" not in columns or "name" not in columns:
        raise HTTPException(
            status_code=400,
            detail="الملف يجب أن يحتوي على عمود للمجموعة وعمود للصنف",
        )

    def cell(row: list[Any], key: str) -> Any:
        index = columns.get(key)
        return row[index] if index is not None and index < len(row) else None

    def number(value: Any) -> float | None:
        if value is None or str(value).strip() == "":
            return None
        try:
            return float(str(value).replace("٫", ".").replace(",", "."))
        except ValueError:
            return None

    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for row_number, row in enumerate(table, start=2 if header_found else 1):
        if not any(str(value or "").strip() for value in row):
            continue
        if len(entries) + len(errors) >= MAX_IMPORT_ROWS:
            errors.append(f"عدد الصفوف أكبر من {MAX_IMPORT_ROWS}")
            break
        group_name = str(cell(row, "group") or "").strip()
        item_name = str(cell(row, "name") or "").strip()
        if not group_name or not item_name:
            errors.append(f"صف {row_number}: اسم المجموعة والصنف مطلوبان")
            continue
        if len(group_name) > 120 or len(item_name) > 160:
            errors.append(f"صف {row_number}: الاسم طويل جداً")
            continue
        key = (group_name, item_name)
        if key in seen:
            errors.append(f"صف {row_number}: الصنف مكرر ({item_name})")
            continue
        seen.add(key)
        price = number(cell(row, "price")) or 0.0
        if price < 0 or price > 1_000_000:
            errors.append(f"صف {row_number}: السعر غير صالح")
            continue
        order_value = number(cell(row, "order"))
        sort_order = int(order_value) if order_value is not None and order_value >= 0 else None
        entries.append(
            {
                "group": group_name,
                "name": item_name,
                "price": round(price, 2),
                "order": sort_order,
                "emoji": str(cell(row, "emoji") or "🛒").strip()[:16] or "🛒",
            }
        )

    if errors:
        raise HTTPException(
            status_code=400,
            detail="أخطاء في الملف: " + "؛ ".join(errors[:8]),
        )
    if not entries:
        raise HTTPException(status_code=400, detail="لم يتم العثور على أصناف في الملف")
    return entries


@app.post("/api/catalog/import")
async def import_catalog(
    file: Annotated[UploadFile, File()],
    db: DbDep,
    _role: Husband,
    mode: str = Query(default="append"),
) -> dict[str, Any]:
    """استيراد مجموعات وأصناف من Excel مع الحفاظ على ترتيب الصفوف."""
    if mode not in {"append", "replace"}:
        raise HTTPException(status_code=400, detail="وضع الاستيراد غير صالح")
    raw = await file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="حجم الملف أكبر من 5 ميجابايت")
    entries = parse_import_rows(file.filename or "", raw)

    groups = list(db.scalars(select(Group).order_by(Group.sort_order, Group.id)).all())
    if mode == "replace":
        for group in groups:
            db.delete(group)
        db.flush()
        groups = []

    groups_by_name = {group.name.strip(): group for group in groups}
    group_order: dict[str, int] = {}
    group_emoji: dict[str, str] = {}
    for entry in entries:
        group_order.setdefault(entry["group"], len(group_order))
        group_emoji.setdefault(entry["group"], entry["emoji"])

    groups_created = 0
    for name, position in group_order.items():
        if name in groups_by_name:
            continue
        group = Group(
            name=name,
            emoji=group_emoji[name],
            sort_order=len(groups_by_name),
        )
        db.add(group)
        groups_by_name[name] = group
        groups_created += 1
    db.flush()

    items_created = 0
    for name, position in group_order.items():
        group = groups_by_name[name]
        highest = -1 if mode == "replace" else (
            db.scalar(select(func.max(Item.sort_order)).where(Item.group_id == group.id)) or -1
        )
        next_order = highest + 1
        for entry in (row for row in entries if row["group"] == name):
            sort_order = entry["order"] if entry["order"] is not None else next_order
            db.add(
                Item(
                    group_id=group.id,
                    name=entry["name"],
                    price=entry["price"],
                    sort_order=sort_order,
                )
            )
            items_created += 1
            next_order = max(next_order, sort_order + 1)

    notify(
        db,
        "wife",
        "تحديث القائمة 🗂️",
        f"{ROLE_NAMES['husband']} حدّث القائمة: {groups_created} مجموعة و{items_created} صنفاً",
        kind="catalog_import",
    )
    db.commit()
    return {
        "ok": True,
        "mode": mode,
        "groups_created": groups_created,
        "items_created": items_created,
        "groups": len(group_order),
        "rows": len(entries),
    }


@app.post("/api/groups", status_code=201)
def create_group(payload: GroupIn, db: DbDep, _role: Husband) -> dict[str, Any]:
    group = Group(name=payload.name.strip(), emoji=payload.emoji or "🛒", sort_order=payload.sort_order)
    db.add(group)
    db.commit()
    db.refresh(group)
    return group_out(group)


@app.patch("/api/groups/{group_id}")
def update_group(
    group_id: int, payload: GroupPatch, db: DbDep, _role: Husband
) -> dict[str, Any]:
    group = get_group_or_404(db, group_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if isinstance(value, str):
            value = value.strip()
        setattr(group, field, value)
    db.commit()
    return group_out(group)


@app.delete("/api/groups/{group_id}")
def delete_group(group_id: int, db: DbDep, _role: Husband) -> dict[str, Any]:
    group = get_group_or_404(db, group_id)
    db.delete(group)
    db.commit()
    return {"ok": True}


@app.post("/api/items", status_code=201)
def create_item(payload: ItemIn, db: DbDep, _role: Husband) -> dict[str, Any]:
    get_group_or_404(db, payload.group_id)
    item = Item(
        group_id=payload.group_id,
        name=payload.name.strip(),
        price=payload.price,
        sort_order=payload.sort_order,
    )
    db.add(item)
    notify(
        db,
        "wife",
        "تحديث القائمة 🗂️",
        f"{ROLE_NAMES['husband']} أضاف الصنف: {item.name.strip()}",
        kind="catalog_item",
    )
    db.commit()
    db.refresh(item)
    return item_out(item)


@app.patch("/api/items/{item_id}")
def update_item(
    item_id: int, payload: ItemPatch, db: DbDep, _role: Husband
) -> dict[str, Any]:
    item = get_item_or_404(db, item_id)
    data = payload.model_dump(exclude_unset=True)
    if "group_id" in data and data["group_id"] is not None:
        get_group_or_404(db, data["group_id"])
    for field, value in data.items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        setattr(item, field, value)
    db.commit()
    return item_out(item)


@app.delete("/api/items/{item_id}")
def delete_item(item_id: int, db: DbDep, _role: Husband) -> dict[str, Any]:
    item = get_item_or_404(db, item_id)
    db.delete(item)
    db.commit()
    return {"ok": True}


@app.post("/api/items/{item_id}/image")
async def upload_item_image(
    item_id: int,
    file: Annotated[UploadFile, File()],
    db: DbDep,
    _role: Husband,
) -> dict[str, Any]:
    item = get_item_or_404(db, item_id)
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="الصورة يجب أن تكون PNG أو JPEG أو WEBP")
    raw = await file.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="حجم الصورة أكبر من 2 ميجابايت")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            image.thumbnail(
                (MAX_IMAGE_SIDE, MAX_IMAGE_SIDE),
                Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS,
            )
            if image.mode not in ("RGBA", "LA"):
                image = image.convert("RGBA")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            blob = buffer.getvalue()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="تعذّر قراءة الصورة") from exc

    item.image_blob = blob
    item.image_type = "image/png"
    db.commit()
    return {"ok": True, "has_image": True}


@app.delete("/api/items/{item_id}/image")
def delete_item_image(item_id: int, db: DbDep, _role: Husband) -> dict[str, Any]:
    item = get_item_or_404(db, item_id)
    item.image_blob = None
    item.image_type = None
    db.commit()
    return {"ok": True, "has_image": False}


@app.get("/api/images/{item_id}")
def item_image(item_id: int, db: DbDep, t: str = Query(default="")) -> Response:
    role = decode_token(t)
    if role is None:
        raise HTTPException(status_code=401, detail="جلسة غير صالحة")
    item = get_item_or_404(db, item_id)
    if not item.image_blob:
        raise HTTPException(status_code=404, detail="لا توجد صورة لهذا الصنف")
    return Response(
        content=item.image_blob,
        media_type=item.image_type or "image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# --------------------------------------------------------------------------
# الطلبات
# --------------------------------------------------------------------------


@app.post("/api/orders", status_code=201)
def create_order(db: DbDep, _role: Wife) -> dict[str, Any]:
    next_serial = (db.scalar(select(func.max(Order.serial))) or 0) + 1
    order = Order(serial=next_serial, status="draft", created_at=utcnow())
    db.add(order)
    db.commit()
    db.refresh(order)
    return {
        "id": order.id,
        "serial": order.serial,
        "created_at": iso(order.created_at),
        "status": order.status,
    }


@app.get("/api/orders")
def list_orders(
    db: DbDep,
    role: AnyRole,
    include_drafts: bool = Query(default=False),
) -> dict[str, Any]:
    query = select(Order)
    if role == "husband" and not include_drafts:
        query = query.where(Order.status.in_(("submitted", "closed")))
    query = query.order_by(Order.serial.desc())
    orders = db.scalars(query).all()
    return {"orders": [order_list_out(o) for o in orders]}


@app.get("/api/orders/{order_id}")
def read_order(order_id: int, db: DbDep, _role: AnyRole) -> dict[str, Any]:
    return order_out(db, get_order_or_404(db, order_id))


@app.put("/api/orders/{order_id}/rows")
def replace_rows(
    order_id: int, payload: RowsReplaceIn, db: DbDep, _role: Wife
) -> dict[str, Any]:
    order = get_order_or_404(db, order_id)
    if order.status != "draft":
        raise HTTPException(status_code=409, detail="لا يمكن تعديل طلب تم إرساله")
    if len(payload.rows) > MAX_ROWS_PER_ORDER:
        raise HTTPException(status_code=400, detail="عدد الأصناف كبير جداً")

    new_rows: list[OrderRow] = []
    for entry in payload.rows:
        item = None
        if entry.item_id is not None:
            item = db.get(Item, entry.item_id)
            if item is None:
                raise HTTPException(status_code=404, detail=f"الصنف {entry.item_id} غير موجود")
        name = (entry.name or (item.name if item else "")).strip()
        if not name:
            raise HTTPException(status_code=400, detail="اسم الصنف مطلوب")
        price = entry.estimated_price if entry.estimated_price else (item.price if item else 0.0)
        new_rows.append(
            OrderRow(
                order_id=order.id,
                item_id=item.id if item else None,
                name=name,
                quantity=entry.quantity,
                estimated_price=price,
                is_custom=bool(entry.is_custom or item is None),
                note=entry.note,
            )
        )

    for row in list(order.rows):
        db.delete(row)
    db.flush()
    db.add_all(new_rows)
    db.commit()
    db.refresh(order)
    return order_out(db, order)


@app.post("/api/orders/{order_id}/submit")
def submit_order(order_id: int, db: DbDep, _role: Wife) -> dict[str, Any]:
    order = get_order_or_404(db, order_id)
    if order.status != "draft":
        raise HTTPException(status_code=409, detail="تم إرسال هذا الطلب من قبل")
    if not order.rows:
        raise HTTPException(status_code=400, detail="أضف صنفاً واحداً على الأقل قبل الإرسال")
    order.status = "submitted"
    order.submitted_at = utcnow()
    order.seen_by_husband = False
    notify(
        db,
        "husband",
        "طلب جديد 🛒",
        f"{ROLE_NAMES['wife']} أرسلت الطلب #{order.serial} بـ {len(order.rows)} أصناف",
        kind="new_order",
        order_id=order.id,
    )
    db.commit()
    return order_out(db, order)


@app.delete("/api/orders/{order_id}")
def delete_own_draft(order_id: int, db: DbDep, _role: Wife) -> dict[str, Any]:
    order = get_order_or_404(db, order_id)
    if order.status != "draft":
        raise HTTPException(status_code=409, detail="يمكن حذف المسودة فقط")
    db.delete(order)
    db.commit()
    return {"ok": True}


@app.patch("/api/orders/{order_id}/rows/{row_id}")
def toggle_purchased(
    order_id: int,
    row_id: int,
    payload: PurchasedPatch,
    db: DbDep,
    _role: Husband,
) -> dict[str, Any]:
    order = get_order_or_404(db, order_id)
    if order.status != "submitted":
        raise HTTPException(status_code=409, detail="يمكن تعديل الطلبات المفتوحة فقط")
    row = db.get(OrderRow, row_id)
    if row is None or row.order_id != order.id:
        raise HTTPException(status_code=404, detail="الصنف غير موجود في الطلب")
    row.purchased = payload.purchased
    db.commit()
    return row_out(row)


@app.post("/api/orders/{order_id}/close")
def close_order(order_id: int, db: DbDep, _role: Husband) -> dict[str, Any]:
    order = get_order_or_404(db, order_id)
    if order.status != "submitted":
        raise HTTPException(status_code=409, detail="الطلب مغلق بالفعل أو لم يُرسل")
    detail = order_out(db, order)
    order.status = "closed"
    order.closed_at = utcnow()
    order.seen_by_husband = True
    for note in db.scalars(
        select(Notification).where(
            Notification.role == "husband",
            Notification.kind == "new_order",
            Notification.order_id == order.id,
        )
    ).all():
        note.seen = True
    notify(
        db,
        "wife",
        "تم إغلاق الطلب ✅",
        f"{ROLE_NAMES['husband']} أغلق الطلب #{order.serial}. تم شراء {detail['summary']['purchased_count']} من {detail['summary']['item_count']}",
        kind="order_closed",
        order_id=order.id,
    )
    db.commit()
    return {
        "serial": order.serial,
        "closed_at": iso(order.closed_at),
        "purchased": [r for g in detail["groups"] for r in g["rows"] if r["purchased"]]
        + [r for r in detail["custom_rows"] if r["purchased"]],
        "not_purchased": [r for g in detail["groups"] for r in g["rows"] if not r["purchased"]]
        + [r for r in detail["custom_rows"] if not r["purchased"]],
        "summary": detail["summary"],
    }


@app.delete("/api/orders")
def delete_orders(payload: DeleteOrdersIn, db: DbDep, _role: Husband) -> dict[str, Any]:
    ids = list(dict.fromkeys(payload.ids))
    if not ids:
        return {"deleted": 0}
    deleted = db.execute(delete(Order).where(Order.id.in_(ids))).rowcount
    db.commit()
    return {"deleted": deleted}


@app.get("/api/notifications")
def notifications(db: DbDep, role: AnyRole) -> dict[str, Any]:
    """صندوق إشعارات مشترك: الزوج يستقبل الطلبات والزوجة تحديثاتها."""
    unread = db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.role == role, Notification.seen.is_(False)
        )
    )
    recent = db.scalars(
        select(Notification)
        .where(Notification.role == role)
        .order_by(Notification.id.desc())
        .limit(20)
    ).all()
    items = [notif_out(note) for note in recent]

    # توافق مع الواجهة القديمة: أحدث طلب مرسل للزوج.
    latest_order = None
    if role == "husband":
        latest_order = db.scalar(
            select(Order)
            .where(Order.status == "submitted")
            .order_by(Order.serial.desc())
            .limit(1)
        )
    latest = items[0] if items else None
    if latest_order and (not latest or not latest.get("order_id")):
        latest = {
            "id": latest_order.id,
            "order_id": latest_order.id,
            "serial": latest_order.serial,
            "title": "طلب جديد 🛒",
            "body": f"طلب جديد رقم #{latest_order.serial}",
            "created_at": None,
            "seen": False,
        }
    return {
        "unread": int(unread or 0),
        "latest": latest,
        "items": items,
    }


@app.post("/api/notifications/seen")
def mark_notifications_seen(db: DbDep, role: AnyRole) -> dict[str, Any]:
    notes = db.scalars(
        select(Notification).where(
            Notification.role == role, Notification.seen.is_(False)
        )
    ).all()
    for note in notes:
        note.seen = True
    if role == "husband":
        orders = db.scalars(
            select(Order).where(
                Order.status == "submitted", Order.seen_by_husband.is_(False)
            )
        ).all()
        for order in orders:
            order.seen_by_husband = True
    else:
        orders = []
    db.commit()
    return {"ok": True, "marked": len(notes) + len(orders)}


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
