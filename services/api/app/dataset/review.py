"""Revue locale des contributions ``pending`` (validation / rejet).

Toutes les fonctions travaillent au niveau d'une ``AsyncSession`` afin d'être
testables sans réseau. La création de session à partir de la configuration est
laissée à la couche CLI (``scripts/review_contributions.py``).

Invariants de confidentialité (AC1/AC3/AC5) :
- aucune sortie ne contient ``anon_id``, ``device_info`` ni de chemin absolu ;
- un retrait (``withdrawn``) est terminal : toute tentative de transition lève
  :class:`~app.db.repositories.InvalidContributionTransitionError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import ContributionRepo, PendingReviewItem
from app.storage.audio_store import AudioStorageError, FilesystemAudioStore

#: Décisions explicites autorisées depuis la revue.
DECISIONS: dict[str, str] = {"validate": "validated", "reject": "rejected"}


@dataclass(frozen=True, slots=True)
class DecisionOutcome:
    """Résultat idempotent et explicite d'une décision de revue."""

    contribution_id: UUID
    previous_status: str
    new_status: str
    changed: bool

    @property
    def message(self) -> str:
        opaque = str(self.contribution_id)
        if not self.changed:
            return f"{opaque} : déjà « {self.new_status} » (aucun changement)"
        return f"{opaque} : {self.previous_status} → {self.new_status}"


class ContributionNotFoundError(Exception):
    """La contribution ciblée n'existe pas."""


async def list_pending(
    session: AsyncSession,
    limit: int = 50,
    offset: int = 0,
) -> list[PendingReviewItem]:
    """Retourne la file de revue paginée (projection sûre uniquement)."""

    return await ContributionRepo(session).pending_for_review(limit=limit, offset=offset)


async def apply_decision(
    session: AsyncSession,
    contribution_id: UUID,
    decision: str,
) -> DecisionOutcome:
    """Applique ``validate``/``reject`` de façon idempotente et verrouillée.

    Refuse toute décision inconnue et toute transition depuis ``withdrawn``
    (délégué à :meth:`ContributionRepo.update_status`). Réappliquer la même
    décision est un no-op signalé (``changed=False``).
    """

    if decision not in DECISIONS:
        raise ValueError(f"unknown decision: {decision!r}")
    target = DECISIONS[decision]
    repo = ContributionRepo(session)
    previous = await repo.status_of(contribution_id)
    if previous is None:
        raise ContributionNotFoundError
    row = await repo.update_status(contribution_id, target)
    if row is None:
        raise ContributionNotFoundError
    return DecisionOutcome(
        contribution_id=contribution_id,
        previous_status=previous,
        new_status=row.status,
        changed=previous != row.status,
    )


def _audio_state(store: FilesystemAudioStore | None, audio_ref: str | None) -> str:
    """Décrit la présence de l'audio sans jamais révéler de chemin absolu."""

    if not audio_ref:
        return "absent"
    if store is None:
        return "présent (réf.)"
    try:
        path = store.local_path(audio_ref)
    except AudioStorageError:
        return "référence invalide"
    return "présent" if path.is_file() else "MANQUANT"


def format_pending(
    items: list[PendingReviewItem],
    store: FilesystemAudioStore | None = None,
) -> str:
    """Rend la file de revue en texte sûr (ni PII, ni chemin absolu).

    Chaque ligne : ``<uuid opaque>  n=<nombre>  prompt=<zarma>  région=<...>
    audio=<état>  réf=<audio_ref opaque>``. La colonne ``réf`` ne montre que le
    nom de fichier opaque (relatif) ; l'opérateur rejoue l'audio depuis la racine
    de stockage configurée (voir ``scripts/README.md``).
    """

    if not items:
        return "Aucune contribution en attente de revue."
    lines = [f"{len(items)} contribution(s) en attente :"]
    for item in items:
        region = item.region if item.region else "—"
        lines.append(
            f"  {item.id}  n={item.expected_number}  "
            f"prompt=« {item.expected_prompt} »  région={region}  "
            f"audio={_audio_state(store, item.audio_ref)}  "
            f"réf={item.audio_ref or '—'}"
        )
    return "\n".join(lines)


__all__ = [
    "DECISIONS",
    "ContributionNotFoundError",
    "DecisionOutcome",
    "apply_decision",
    "format_pending",
    "list_pending",
]
