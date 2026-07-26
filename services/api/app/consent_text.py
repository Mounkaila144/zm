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
CONSENT_VERSION = "2.0.0"

#: Texte présenté avant toute contribution. Couvre les quatre points requis
#: (AC1) : usage, anonymat, conservation, retrait.
CONSENT_TEXT = """\
Note de confidentialité — ZarmaIA

Usage : l'application enregistre votre voix lorsque vous dites un nombre ou \
un calcul. L'enregistrement est envoyé au serveur pour reconnaître votre \
demande et vous donner une réponse.

Amélioration des modèles : si vous acceptez, chaque enregistrement de calcul \
est conservé de façon sécurisée afin d'entraîner, tester et améliorer les \
prochains modèles de reconnaissance vocale en zarma.

Anonymat : les enregistrements sont associés uniquement à un identifiant \
technique aléatoire. Aucun nom, numéro de téléphone, contact ou position GPS \
n'est collecté.

Conservation et Retrait : vous pouvez retirer votre accord. Les fichiers audio \
encore actifs seront alors supprimés et leurs métadonnées anonymisées. Après \
un retrait, l'application demandera un nouvel accord avant de pouvoir être \
utilisée.

En appuyant sur « J'accepte », vous autorisez le traitement et la conservation \
de vos enregistrements vocaux pour le fonctionnement de l'application et \
l'amélioration des modèles. Si vous refusez, aucun enregistrement n'est envoyé \
et l'application ne peut pas être utilisée.
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
