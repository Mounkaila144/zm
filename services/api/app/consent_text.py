"""Source **versionnée** du texte de consentement (FR19).

Le texte de consentement et sa version sont une ressource serveur versionnée
(constante de module, suivie par Git) : traçable et rechargeable. La version
**courante** est servie par ``GET /api/v1/consent`` ; la version qu'un
contributeur accepte est persistée telle quelle (``consents.consent_version``),
ce qui permet d'auditer une acceptation face au texte en vigueur à ce moment —
même si le texte courant évolue par la suite.

Règle « Versions systématiques » (Coding Standards) : toute réponse porte une
version explicite. Faire évoluer le texte = incrémenter ``CONSENT_VERSION`` et
mettre à jour ``CONSENT_TEXT`` dans le même commit.
"""

from __future__ import annotations

from typing import NamedTuple

#: Version du texte de consentement courant. Incrémenter à chaque modification
#: de ``CONSENT_TEXT`` (SemVer simplifié).
CONSENT_VERSION = "1.0.0"

#: Texte présenté avant toute contribution. Couvre les quatre points requis
#: (AC1) : usage, anonymat, conservation, retrait.
CONSENT_TEXT = """\
Contribution de votre voix — Zarma

Usage : votre enregistrement vocal sert uniquement à améliorer la \
reconnaissance des nombres en zarma (constitution d'un jeu de données \
d'apprentissage et d'évaluation). Il n'est jamais utilisé à d'autres fins.

Anonymat : votre contribution est anonyme. Elle est associée à un identifiant \
technique aléatoire de votre appareil, sans nom, numéro de téléphone ni aucune \
donnée personnelle permettant de vous identifier.

Conservation : par défaut, l'audio d'une simple reconnaissance n'est jamais \
conservé — il est supprimé après traitement. Seuls les enregistrements que \
vous choisissez de contribuer, après acceptation de ce consentement, sont \
conservés de façon sécurisée.

Retrait : vous pouvez à tout moment retirer votre consentement. Vos \
enregistrements consentis sont alors supprimés et les métadonnées associées \
anonymisées.

En appuyant sur « Accepter », vous confirmez avoir compris et accepté ces \
conditions pour la version indiquée de ce texte.
"""


class ConsentContent(NamedTuple):
    """Couple immuable ``(version, texte)`` du consentement courant."""

    consent_version: str
    text: str


def current_consent() -> ConsentContent:
    """Retourne le texte de consentement **courant** et sa version."""

    return ConsentContent(consent_version=CONSENT_VERSION, text=CONSENT_TEXT)


__all__ = [
    "CONSENT_TEXT",
    "CONSENT_VERSION",
    "ConsentContent",
    "current_consent",
]
