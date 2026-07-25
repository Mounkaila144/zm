"""Outils opérateurs locaux : revue des contributions et manifest dataset.

Ce sous-paquet héberge la logique **testable** derrière les scripts
``scripts/review_contributions.py`` et ``scripts/build_dataset_manifest.py``.
Il n'expose aucune route publique et n'introduit aucune authentification : la
sécurité repose sur les permissions du poste opérateur (story 4.5).
"""

from __future__ import annotations

from app.dataset.manifest import (
    DEFAULT_SPLIT_SEED,
    DEFAULT_SPLITS,
    ManifestError,
    ManifestResult,
    assign_split,
    build_manifest,
)
from app.dataset.review import (
    DecisionOutcome,
    apply_decision,
    format_pending,
    list_pending,
)

__all__ = [
    "DEFAULT_SPLITS",
    "DEFAULT_SPLIT_SEED",
    "DecisionOutcome",
    "ManifestError",
    "ManifestResult",
    "apply_decision",
    "assign_split",
    "build_manifest",
    "format_pending",
    "list_pending",
]
