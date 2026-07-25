"""Modèles ORM portables de reconnaissance et de feedback."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base déclarative unique de l'API."""


class Recognition(Base):
    """Métadonnées d'une reconnaissance ; aucune donnée audio."""

    __tablename__ = "recognitions"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('accept', 'confirm', 'repeat')",
            name="ck_recognitions_decision",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    anon_id: Mapped[str] = mapped_column(Text, nullable=False)
    recognized_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_asr_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    alternatives: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    grammar_version: Mapped[str] = mapped_column(Text, nullable=False)
    latency_total_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_asr_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )


class Feedback(Base):
    """Feedback lié à une reconnaissance persistée."""

    __tablename__ = "feedbacks"
    __table_args__ = (
        CheckConstraint(
            "feedback_type IN " "('confirmed', 'corrected', 'rejected', 'repeat_requested')",
            name="ck_feedbacks_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    recognition_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("recognitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    anon_id: Mapped[str] = mapped_column(Text, nullable=False)
    feedback_type: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    corrected_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    grammar_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )


class Consent(Base):
    """Acceptation versionnée et traçable d'un contributeur ; identité = ``anon_id``.

    Prérequis éthique à toute conservation de voix (FR19/FR20). Le champ
    ``consent_version`` est persisté tel qu'accepté pour permettre l'audit d'une
    acceptation face au texte en vigueur à ce moment. ``withdrawn`` prépare le
    retrait (story 4.4) et reste ``false`` par défaut.
    """

    __tablename__ = "consents"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    anon_id: Mapped[str] = mapped_column(Text, nullable=False)
    consent_version: Mapped[str] = mapped_column(Text, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    withdrawn: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=func.false(),
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class Contribution(Base):
    """Métadonnées d'un audio consenti stocké hors base (FR20/FR22)."""

    __tablename__ = "contributions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'validated', 'rejected', 'withdrawn')",
            name="ck_contributions_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    anon_id: Mapped[str] = mapped_column(Text, nullable=False)
    consent_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("consents.id"),
        nullable=False,
    )
    expected_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    audio_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    speaker_key: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="pending",
        server_default="pending",
    )
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    grammar_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )


Index(
    "idx_recognitions_anon",
    Recognition.anon_id,
    Recognition.created_at.desc(),
)
Index("idx_feedbacks_recognition", Feedback.recognition_id)
Index("idx_consents_anon", Consent.anon_id)
Index("idx_contrib_speaker", Contribution.speaker_key)
Index("idx_contrib_status", Contribution.status)


__all__ = ["Base", "Consent", "Contribution", "Feedback", "Recognition"]
