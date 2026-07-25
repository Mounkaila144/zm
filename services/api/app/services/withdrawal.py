"""Orchestration réessayable du retrait des contributions consenties."""

from __future__ import annotations

from uuid import UUID

from app.db.repositories import ConsentRepo, ContributionRepo
from app.storage.audio_store import AudioStorageError, AudioStore


class WithdrawalIncompleteError(Exception):
    """Au moins un fichier n'a pas pu être supprimé ; un retry est requis."""


class WithdrawalService:
    """Révoque d'abord, supprime les fichiers, puis anonymise les tombstones."""

    def __init__(
        self,
        *,
        consent_repo: ConsentRepo,
        contribution_repo: ContributionRepo,
        audio_store: AudioStore,
    ) -> None:
        self._consent_repo = consent_repo
        self._contribution_repo = contribution_repo
        self._audio_store = audio_store

    async def withdraw(self, anon_id: UUID) -> None:
        await self._consent_repo.revoke_and_anonymize_all(anon_id)
        targets = await self._contribution_repo.withdrawal_targets(anon_id)
        try:
            for target in targets:
                if target.audio_ref is not None:
                    await self._audio_store.delete(target.audio_ref)
        except AudioStorageError as exc:
            raise WithdrawalIncompleteError from exc
        await self._contribution_repo.finalize_withdrawal([target.id for target in targets])


__all__ = ["WithdrawalIncompleteError", "WithdrawalService"]
