"""نماذج الطلبات الواردة (Pydantic)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LoginIn(BaseModel):
    role: Literal["husband", "wife"]
    pin: str = Field(min_length=1, max_length=16)


class PinChangeIn(BaseModel):
    current_pin: str = Field(min_length=1, max_length=16)
    target_role: Literal["husband", "wife"]
    new_pin: str = Field(min_length=4, max_length=16)

    @field_validator("new_pin")
    @classmethod
    def digits_only(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("يجب أن يتكون الرمز من أرقام فقط")
        return value


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    emoji: str = Field(default="🛒", max_length=16)
    sort_order: int = Field(default=0, ge=0, le=100_000)


class GroupPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    emoji: str | None = Field(default=None, max_length=16)
    sort_order: int | None = Field(default=None, ge=0, le=100_000)


class ItemIn(BaseModel):
    group_id: int
    name: str = Field(min_length=1, max_length=160)
    price: float = Field(default=0.0, ge=0, le=1_000_000)
    sort_order: int = Field(default=0, ge=0, le=100_000)


class ItemPatch(BaseModel):
    group_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    price: float | None = Field(default=None, ge=0, le=1_000_000)
    sort_order: int | None = Field(default=None, ge=0, le=100_000)


class RowIn(BaseModel):
    item_id: int | None = None
    name: str | None = Field(default=None, max_length=160)
    quantity: float = Field(default=1.0, gt=0, le=10_000)
    estimated_price: float = Field(default=0.0, ge=0, le=1_000_000)
    is_custom: bool = False
    note: str | None = Field(default=None, max_length=500)


class RowsReplaceIn(BaseModel):
    rows: list[RowIn] = Field(default_factory=list)


class PurchasedPatch(BaseModel):
    purchased: bool


class DeleteOrdersIn(BaseModel):
    ids: list[int] = Field(default_factory=list)
