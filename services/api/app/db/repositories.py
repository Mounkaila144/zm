"""Repositories async pour isoler l'accès SQLAlchemy des routes."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, Annotated
from uuid import UUID, uuid4

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.consent_text import CONSENT_VERSION
from app.db.models import Consent, Contribution, Feedback, Recognition, utc_now
from app.db.session import get_session

if TYPE_CHECKING:
    from app.api.v1.feedback import FeedbackRequest
    from app.api.v1.recognize import RecognitionResponse


class RecognitionNotFoundError(Exception):
    """La reconnaissance demandée n'existe pas pour cet identifiant anonyme."""


class ContributionConsentInvalidError(Exception):
    """Le consentement n'autorise plus le commit d'une contribution."""


class InvalidContributionTransitionError(Exception):
    """Une transition interdite, notamment depuis ``withdrawn``, a été demandée."""


class RecognitionRepo:
    """Persistance et historique des reconnaissances."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(
        self,
        response: RecognitionResponse,
        anon_id: UUID,
        raw_asr_text: str,
    ) -> Recognition:
        row = Recognition(
            id=response.id,
            anon_id=str(anon_id),
            recognized_number=response.recognized_number,
            normalized_text=response.normalized_text,
            raw_asr_text=raw_asr_text,
            confidence=response.confidence,
            decision=response.decision,
            alternatives=[
                alternative.model_dump(mode="json") for alternative in response.alternatives
            ],
            expression=(
                response.expression.model_dump(mode="json")
                if response.expression is not None
                else None
            ),
            model_version=response.model_version,
            grammar_version=response.grammar_version,
            latency_total_ms=response.latency_total_ms,
            latency_asr_ms=response.latency_asr_ms,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def history(self, anon_id: UUID, limit: int = 50) -> list[Recognition]:
        bounded_limit = max(1, min(int(limit), 200))
        query = (
            select(Recognition)
            .where(Recognition.anon_id == str(anon_id))
            .order_by(Recognition.created_at.desc())
            .limit(bounded_limit)
        )
        return list((await self._session.scalars(query)).all())


class FeedbackRepo:
    """Persistance des feedbacks liés à une reconnaissance existante."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, request: FeedbackRequest) -> Feedback:
        recognition = await self._session.scalar(
            select(Recognition).where(
                Recognition.id == request.recognition_id,
                Recognition.anon_id == str(request.anon_id),
            )
        )
        if recognition is None:
            raise RecognitionNotFoundError

        row = Feedback(
            recognition_id=recognition.id,
            anon_id=str(request.anon_id),
            feedback_type=request.feedback_type,
            proposed_number=request.proposed_number,
            corrected_number=request.corrected_number,
            model_version=recognition.model_version,
            grammar_version=recognition.grammar_version,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row


class ConsentRepo:
    """Persistance et relecture des consentements versionnés (FR19)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, anon_id: UUID, consent_version: str) -> Consent:
        """Enregistre une acceptation ; ``accepted_at`` est horodaté par la base."""

        row = Consent(anon_id=str(anon_id), consent_version=consent_version)
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def latest_for(self, anon_id: UUID) -> Consent | None:
        """Dernier consentement accepté pour cet ``anon_id`` (traçabilité, audit)."""

        query = (
            select(Consent)
            .where(Consent.anon_id == str(anon_id))
            .order_by(Consent.accepted_at.desc())
            .limit(1)
        )
        return await self._session.scalar(query)

    async def has_valid_consent(self, anon_id: UUID) -> bool:
        """Vrai si la version courante est acceptée et non retirée (FR20).

        Base de ``require_valid_consent`` (upload consenti en story 4.3) ; ici
        aucune collecte n'a lieu sans ce prérequis.
        """

        query = (
            select(Consent.id)
            .where(
                Consent.anon_id == str(anon_id),
                Consent.consent_version == CONSENT_VERSION,
                Consent.withdrawn.is_(False),
            )
            .limit(1)
        )
        return await self._session.scalar(query) is not None

    async def valid_for(self, consent_id: UUID, anon_id: UUID) -> Consent | None:
        """Retourne uniquement un consentement courant, non retiré et possédé."""

        query = select(Consent).where(
            Consent.id == consent_id,
            Consent.anon_id == str(anon_id),
            Consent.consent_version == CONSENT_VERSION,
            Consent.withdrawn.is_(False),
        )
        return await self._session.scalar(query)

    async def revoke_and_anonymize_all(self, anon_id: UUID) -> None:
        """Révoque immédiatement tous les consentements et efface leur identité."""

        query = select(Consent).where(Consent.anon_id == str(anon_id)).with_for_update()
        rows = list((await self._session.scalars(query)).all())
        withdrawn_at = utc_now()
        for row in rows:
            row.withdrawn = True
            row.withdrawn_at = row.withdrawn_at or withdrawn_at
            row.anon_id = _tombstone("consent")
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise


def speaker_key_for(anon_id: UUID) -> str:
    """Dérive une clé stable non réversible pour séparer les locuteurs."""

    return sha256(anon_id.bytes).hexdigest()


@dataclass(frozen=True, slots=True)
class ContributionCreate:
    anon_id: UUID
    consent_id: UUID
    expected_number: int
    expected_prompt: str
    audio_ref: str
    region: str | None
    device_info: str | None
    model_version: str
    grammar_version: str


@dataclass(frozen=True, slots=True)
class ContributionWithdrawalTarget:
    id: UUID
    audio_ref: str | None


@dataclass(frozen=True, slots=True)
class PendingReviewItem:
    """Projection sûre exposée à l'opérateur de revue.

    Ne contient **jamais** ``anon_id``, ``device_info`` ni de chemin physique :
    uniquement les champs nécessaires pour juger une contribution ``pending``.
    """

    id: UUID
    expected_number: int
    expected_prompt: str
    region: str | None
    audio_ref: str | None


@dataclass(frozen=True, slots=True)
class DatasetManifestRow:
    """Projection minimale d'un candidat éligible au manifest dataset.

    Exclut toute PII (``anon_id``, ``device_info``) ; ``speaker_key`` est déjà
    une dérivation non réversible et ``audio_ref`` une référence opaque relative.
    """

    id: UUID
    audio_ref: str
    expected_number: int
    speaker_key: str
    region: str | None


def _dataset_eligibility():
    """Prédicat **unique** d'éligibilité dataset (story 4.5, AC2).

    Toute sélection destinée à un manifest ou un benchmark passe par ce
    prédicat : ``status = validated`` **et** ``audio_ref IS NOT NULL``. Les états
    ``pending``, ``rejected`` et ``withdrawn`` sont donc systématiquement exclus.
    """

    return (
        Contribution.status == "validated",
        Contribution.audio_ref.is_not(None),
    )


class ContributionRepo:
    """Persistance atomique des métadonnées de contributions consenties."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, contribution: ContributionCreate) -> Contribution:
        if not contribution.audio_ref:
            raise ValueError("audio_ref is required for a pending contribution")
        consent_query = (
            select(Consent.id)
            .where(
                Consent.id == contribution.consent_id,
                Consent.anon_id == str(contribution.anon_id),
                Consent.consent_version == CONSENT_VERSION,
                Consent.withdrawn.is_(False),
            )
            .with_for_update()
        )
        if await self._session.scalar(consent_query) is None:
            await self._session.rollback()
            raise ContributionConsentInvalidError
        row = Contribution(
            anon_id=str(contribution.anon_id),
            consent_id=contribution.consent_id,
            expected_number=contribution.expected_number,
            expected_prompt=contribution.expected_prompt,
            audio_ref=contribution.audio_ref,
            speaker_key=speaker_key_for(contribution.anon_id),
            region=contribution.region,
            device_info=contribution.device_info,
            status="pending",
            model_version=contribution.model_version,
            grammar_version=contribution.grammar_version,
        )
        self._session.add(row)
        try:
            await self._session.commit()
            await self._session.refresh(row)
        except Exception:
            await self._session.rollback()
            raise
        return row

    async def withdrawal_targets(
        self,
        anon_id: UUID,
    ) -> list[ContributionWithdrawalTarget]:
        """Capture les références encore actives puis libère la transaction de lecture."""

        query = select(Contribution.id, Contribution.audio_ref).where(
            Contribution.anon_id == str(anon_id),
            Contribution.status != "withdrawn",
        )
        rows = (await self._session.execute(query)).all()
        await self._session.commit()
        return [ContributionWithdrawalTarget(id=row.id, audio_ref=row.audio_ref) for row in rows]

    async def finalize_withdrawal(self, contribution_ids: list[UUID]) -> None:
        """Anonymise en lot les tombstones après suppression de tous les fichiers."""

        if not contribution_ids:
            return
        query = (
            select(Contribution)
            .where(
                Contribution.id.in_(contribution_ids),
                Contribution.status != "withdrawn",
            )
            .with_for_update()
        )
        rows = list((await self._session.scalars(query)).all())
        for row in rows:
            row.status = "withdrawn"
            row.audio_ref = None
            row.region = None
            row.device_info = None
            row.anon_id = _tombstone("contribution")
            row.speaker_key = _tombstone("speaker")
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

    async def pending_for_review(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PendingReviewItem]:
        """File de revue paginée et ordonnée des contributions ``pending``.

        Retourne une projection sûre (jamais ``anon_id``/``device_info``) et
        exclut par construction les états ``validated``, ``rejected`` et
        ``withdrawn``. L'ordre est stable (plus ancien d'abord, ``id`` en
        départage) pour une revue reproductible.
        """

        bounded_limit = max(1, min(int(limit), 500))
        bounded_offset = max(0, int(offset))
        query = (
            select(
                Contribution.id,
                Contribution.expected_number,
                Contribution.expected_prompt,
                Contribution.region,
                Contribution.audio_ref,
            )
            .where(Contribution.status == "pending")
            .order_by(Contribution.created_at.asc(), Contribution.id.asc())
            .limit(bounded_limit)
            .offset(bounded_offset)
        )
        rows = (await self._session.execute(query)).all()
        return [
            PendingReviewItem(
                id=row.id,
                expected_number=row.expected_number,
                expected_prompt=row.expected_prompt,
                region=row.region,
                audio_ref=row.audio_ref,
            )
            for row in rows
        ]

    async def status_of(self, contribution_id: UUID) -> str | None:
        """Retourne l'état courant d'une contribution, ou ``None`` si absente."""

        return await self._session.scalar(
            select(Contribution.status).where(Contribution.id == contribution_id)
        )

    async def update_status(
        self,
        contribution_id: UUID,
        status: str,
    ) -> Contribution | None:
        """Applique une transition métier sans permettre de restaurer un retrait."""

        if status not in {"pending", "validated", "rejected"}:
            raise InvalidContributionTransitionError
        row = await self._session.scalar(
            select(Contribution).where(Contribution.id == contribution_id).with_for_update()
        )
        if row is None:
            return None
        if row.status == "withdrawn":
            await self._session.rollback()
            raise InvalidContributionTransitionError
        row.status = status
        try:
            await self._session.commit()
            await self._session.refresh(row)
        except Exception:
            await self._session.rollback()
            raise
        return row

    async def dataset_candidates(self) -> list[Contribution]:
        """Retourne l'unique ensemble éligible aux manifests et benchmarks."""

        query = select(Contribution).where(*_dataset_eligibility())
        return list((await self._session.scalars(query)).all())

    async def dataset_manifest_rows(self) -> list[DatasetManifestRow]:
        """Projection sûre et ordonnée des candidats éligibles au manifest.

        Utilise le **même** prédicat que :meth:`dataset_candidates` et ne charge
        que les champs publiables ; l'ordre stable (``speaker_key`` puis
        ``audio_ref``) rend la génération reproductible.
        """

        query = (
            select(
                Contribution.id,
                Contribution.audio_ref,
                Contribution.expected_number,
                Contribution.speaker_key,
                Contribution.region,
            )
            .where(*_dataset_eligibility())
            .order_by(Contribution.speaker_key.asc(), Contribution.audio_ref.asc())
        )
        rows = (await self._session.execute(query)).all()
        return [
            DatasetManifestRow(
                id=row.id,
                audio_ref=row.audio_ref,
                expected_number=row.expected_number,
                speaker_key=row.speaker_key,
                region=row.region,
            )
            for row in rows
        ]


def _tombstone(kind: str) -> str:
    """Produit une valeur opaque aléatoire sans lien avec l'identité originale."""

    return f"withdrawn-{kind}-{uuid4().hex}"


class MetricsRepo:
    """Agrégations en lecture seule pour le pilotage qualité (story 4.6).

    Ne lit que des **agrégats** (comptes, latences) — jamais d'``anon_id``
    individuel, de texte brut ni d'audio (NFR6).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def feedback_counts(self) -> dict[str, int]:
        """Compte les feedbacks par ``feedback_type`` (agrégat pur)."""

        query = select(Feedback.feedback_type, func.count()).group_by(Feedback.feedback_type)
        rows = (await self._session.execute(query)).all()
        return {feedback_type: count for feedback_type, count in rows}

    async def latency_values(self) -> tuple[list[int], list[int]]:
        """Retourne les latences non nulles ``(total_ms, asr_ms)``.

        Le calcul moyenne/percentiles est fait en Python pour rester portable
        entre SQLite (dev) et PostgreSQL (prod).
        """

        total = await self._session.scalars(
            select(Recognition.latency_total_ms).where(Recognition.latency_total_ms.is_not(None))
        )
        asr = await self._session.scalars(
            select(Recognition.latency_asr_ms).where(Recognition.latency_asr_ms.is_not(None))
        )
        return list(total.all()), list(asr.all())


def get_recognition_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RecognitionRepo:
    return RecognitionRepo(session)


def get_feedback_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FeedbackRepo:
    return FeedbackRepo(session)


def get_metrics_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MetricsRepo:
    return MetricsRepo(session)


def get_consent_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ConsentRepo:
    return ConsentRepo(session)


def get_contribution_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ContributionRepo:
    return ContributionRepo(session)


__all__ = [
    "ConsentRepo",
    "ContributionConsentInvalidError",
    "ContributionCreate",
    "ContributionRepo",
    "ContributionWithdrawalTarget",
    "DatasetManifestRow",
    "FeedbackRepo",
    "InvalidContributionTransitionError",
    "MetricsRepo",
    "PendingReviewItem",
    "RecognitionNotFoundError",
    "RecognitionRepo",
    "get_consent_repo",
    "get_contribution_repo",
    "get_feedback_repo",
    "get_metrics_repo",
    "get_recognition_repo",
    "speaker_key_for",
]
