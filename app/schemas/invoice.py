from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator


# ISO 4217 alphabetic: three letters after strip/upper (shape only, not official registry).
class Iso4217:
    @classmethod
    def is_valid(cls, code: str) -> bool:
        c = code.strip().upper()
        return re.fullmatch(r"[A-Z]{3}", c) is not None


class InvoiceSchema(BaseModel):
    """Named InvoiceSchema to avoid clashing with ORM model `Invoice` when importing."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    vendorId: str
    invoiceId: str
    amount: float
    currency: str

    @field_validator("amount")
    @classmethod
    def amount_finite(cls, v: float) -> float:
        if v != v:  # NaN
            raise ValueError("amount must be a finite number")
        return v

    @field_validator("currency")
    @classmethod
    def currency_iso4217(cls, v: str) -> str:
        c = v.strip().upper()
        if not Iso4217.is_valid(c):
            raise ValueError("currency must be a 3-letter ISO 4217 alphabetic code")
        return c
