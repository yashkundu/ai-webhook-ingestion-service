from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RawWebhook(Base):
    __tablename__ = "raw_webhooks"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_raw_webhook_idem"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    vendor_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    # Store raw JSON as text for exact canonical hashing / debugging
    body_json: Mapped[str] = mapped_column(Text, nullable=False)
    # Composite key: header-based "vendor:idem" or sha256 of vendor+body
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True, nullable=False)
    queued: Mapped[bool] = mapped_column(default=True)  # whether accepted into memory queue
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    shipment: Mapped[Optional["Shipment"]] = relationship(
        "Shipment", back_populates="raw_webhook", uselist=False
    )
    invoice: Mapped[Optional["Invoice"]] = relationship(
        "Invoice", back_populates="raw_webhook", uselist=False
    )
    dead_letters: Mapped[list["DeadLetter"]] = relationship(
        "DeadLetter", back_populates="raw_webhook"
    )


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    raw_webhook_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("raw_webhooks.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    vendor_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    tracking_number: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    raw_webhook: Mapped["RawWebhook"] = relationship("RawWebhook", back_populates="shipment")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    raw_webhook_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("raw_webhooks.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    vendor_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    invoice_id: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    raw_webhook: Mapped["RawWebhook"] = relationship("RawWebhook", back_populates="invoice")


class DeadLetter(Base):
    __tablename__ = "dead_letter_queue"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    raw_webhook_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("raw_webhooks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    error_type: Mapped[str] = mapped_column(String(128), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    raw_webhook: Mapped["RawWebhook"] = relationship("RawWebhook", back_populates="dead_letters")
