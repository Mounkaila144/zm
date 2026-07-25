#!/usr/bin/env python
"""Revue locale des contributions vocales en attente (story 4.5).

Outil **local** réservé au responsable données ; sa sécurité repose sur les
permissions du poste (aucun back-office web, aucune auth admin). Il permet de :

- lister les contributions ``pending`` (projection sûre, sans PII) ;
- valider (``validated``) ou rejeter (``rejected``) une contribution par UUID.

Un retrait (``withdrawn``) est terminal : aucune décision ne peut le restaurer.

Configuration (via ``Settings`` / variables d'environnement, cf. ``.env``) :
- ``DATABASE_URL``       — base des métadonnées (SQLite en dev, PostgreSQL en prod) ;
- ``AUDIO_STORAGE_DIR``  — racine du stockage audio consenti (hors base, hors Git).

Écoute de l'audio : la commande ``list`` affiche la référence opaque (``réf=``) et
l'état de présence, jamais un chemin absolu. Rejouez le fichier depuis la racine
configurée : ``<AUDIO_STORAGE_DIR>/<réf>``.

Exemples :
    uv run python scripts/review_contributions.py list
    uv run python scripts/review_contributions.py list --limit 20 --offset 40
    uv run python scripts/review_contributions.py validate <UUID>
    uv run python scripts/review_contributions.py reject <UUID> --yes
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

# Permet d'importer le paquet ``app`` même sans installation editable préalable.
_API_ROOT = Path(__file__).resolve().parents[1] / "services" / "api"
if _API_ROOT.is_dir() and str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.config import get_settings  # noqa: E402
from app.dataset.review import (  # noqa: E402
    ContributionNotFoundError,
    apply_decision,
    format_pending,
    list_pending,
)
from app.dataset.session import session_scope  # noqa: E402
from app.db.repositories import InvalidContributionTransitionError  # noqa: E402
from app.storage.audio_store import FilesystemAudioStore  # noqa: E402


async def _run_list(limit: int, offset: int) -> int:
    store = FilesystemAudioStore(get_settings().AUDIO_STORAGE_DIR)
    async with session_scope() as session:
        items = await list_pending(session, limit=limit, offset=offset)
    print(format_pending(items, store))
    return 0


async def _run_decision(decision: str, contribution_id: UUID, assume_yes: bool) -> int:
    if not assume_yes:
        verb = "VALIDER" if decision == "validate" else "REJETER"
        answer = input(f"Confirmer {verb} {contribution_id} ? [oui/non] ").strip().lower()
        if answer not in {"oui", "o", "yes", "y"}:
            print("Annulé.")
            return 1
    async with session_scope() as session:
        try:
            outcome = await apply_decision(session, contribution_id, decision)
        except ContributionNotFoundError:
            print(f"Introuvable : {contribution_id}", file=sys.stderr)
            return 2
        except InvalidContributionTransitionError:
            print(
                f"Transition refusée : {contribution_id} est retirée (terminal).",
                file=sys.stderr,
            )
            return 3
    print(outcome.message)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Revue locale des contributions en attente.")
    sub = parser.add_subparsers(dest="command", required=True)

    list_cmd = sub.add_parser("list", help="Lister les contributions pending.")
    list_cmd.add_argument("--limit", type=int, default=50)
    list_cmd.add_argument("--offset", type=int, default=0)

    for name, help_text in (("validate", "Valider"), ("reject", "Rejeter")):
        decision_cmd = sub.add_parser(name, help=f"{help_text} une contribution par UUID.")
        decision_cmd.add_argument("contribution_id", type=UUID)
        decision_cmd.add_argument(
            "--yes",
            action="store_true",
            help="Confirme sans invite (décision explicite).",
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "list":
        return asyncio.run(_run_list(args.limit, args.offset))
    return asyncio.run(_run_decision(args.command, args.contribution_id, args.yes))


if __name__ == "__main__":
    raise SystemExit(main())
