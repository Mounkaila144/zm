"""Configuration du service ASR (story 5.6, task 7).

Même règle que l'API : **toute** lecture de configuration passe par un objet
``Settings`` (pydantic-settings), jamais un ``os.environ`` dispersé, et
**aucun secret en dur**. Les paramètres du décodage contraint (largeur de
faisceau, exposant de longueur, seuil de rejet…) sont donc configurables sans
toucher au code — ce sont précisément les valeurs calibrées de la story.

Le décodage s'exécutant **côté service ASR** (là où vivent les logits, cf.
`services/asr/README.md`), sa configuration vit ici plutôt que dans
``services/api/app/config.py`` — l'API n'a aucun paramètre de décodage à
connaître, ce qui préserve l'étanchéité de l'interface ``SpeechRecognizer``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Langues contraintes disponibles : les nombres seuls (epics 1–5) ou les
#: expressions arithmétiques (story 6.1). Même automate, même décodeur — c'est
#: la **langue** qui change, pas l'algorithme.
GrammarKind = Literal["numbers", "expressions"]


class AsrSettings(BaseSettings):
    """Paramètres du service ASR, lus depuis l'environnement (Modal secrets/env).

    Les défauts reprennent les valeurs **validées empiriquement** par la story
    5.6 (Annexe A §3 pour ``p = 1.0``, Annexe D §1 pour ``blank = 0``). Le seuil
    de rejet vaut ``0.0`` par défaut — c'est-à-dire *aucun rejet* — tant qu'il
    n'a pas été calibré sur un corpus dédié (`scripts/bench/calibrate_rejection.py`,
    jamais sur le split de test, NFR10). Un défaut non calibré qui rejetterait
    serait pire que pas de rejet du tout.
    """

    #: Active le décodage contraint à la grammaire (sinon décodage glouton).
    DECODE_CONSTRAINED: bool = True
    #: Langue contrainte : ``numbers`` (défaut — comportement des epics 1–5
    #: **inchangé**) ou ``expressions`` (calculatrice vocale, story 6.1).
    #: Bascule par configuration, jamais par du code applicatif (NFR9).
    DECODE_GRAMMAR: GrammarKind = "numbers"
    #: Largeur du faisceau (préfixes conservés par trame) — choisie sur un
    #: critère de **latence**, pas sur l'accuracy (cf. `services/asr/README.md`).
    DECODE_BEAM_WIDTH: int = Field(default=256, ge=1)
    #: Nombre d'hypothèses exposées (alimente ``AsrResult.candidates``).
    DECODE_NBEST: int = Field(default=5, ge=1)
    #: Id du token blank CTC — 0 pour Omnilingual (PAS 1, cf. Annexe D §1).
    DECODE_BLANK_ID: int = Field(default=0, ge=0)
    #: Exposant ``p`` de la normalisation par longueur (optimum mesuré : 1.0).
    DECODE_LENGTH_EXPONENT: float = Field(default=1.0, ge=0.0)
    #: Trames minimales par token restant (contrainte de durée, Annexe A §5).
    DECODE_MIN_FRAMES_PER_TOKEN: float = Field(default=1.0, ge=0.0)
    #: Re-score exact (forward CTC) des hypothèses finales.
    DECODE_EXACT_RESCORE: bool = True
    #: Seuil de rejet sur la confiance de décodage (0.0 = aucun rejet).
    DECODE_REJECT_THRESHOLD: float = Field(default=0.0, ge=0.0, le=1.0)
    #: Ids du séparateur de mots du tokenizer (JSON/CSV, ex. « 5262 »).
    #: Vide = pas de séparateur explicite entre deux mots.
    DECODE_SEPARATOR_IDS: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def separator_ids(self) -> tuple[int, ...]:
        """``DECODE_SEPARATOR_IDS`` parsé en tuple d'entiers (vide si absent)."""
        raw = self.DECODE_SEPARATOR_IDS.strip()
        if not raw:
            return ()
        return tuple(int(part) for part in raw.replace(",", " ").split())

    def load_grammar(self):
        """Automate correspondant à ``DECODE_GRAMMAR`` (import tardif : léger).

        Point d'accès **unique** à la grammaire côté service ASR : le module de
        décodage reste agnostique de la langue qu'il contraint, et basculer la
        calculatrice vocale ne demande qu'une variable d'environnement.
        """
        from zarma_numbers.grammar import (  # noqa: PLC0415 - construction coûteuse
            load_expression_grammar,
            load_grammar,
        )

        if self.DECODE_GRAMMAR == "expressions":
            return load_expression_grammar()
        return load_grammar()

    def decoder_config(self):
        """Construit le ``DecoderConfig`` correspondant (import tardif : léger)."""
        from .decoding import DecoderConfig  # noqa: PLC0415 - évite numpy à l'import

        return DecoderConfig(
            beam_width=self.DECODE_BEAM_WIDTH,
            nbest=self.DECODE_NBEST,
            blank_id=self.DECODE_BLANK_ID,
            length_exponent=self.DECODE_LENGTH_EXPONENT,
            min_frames_per_token=self.DECODE_MIN_FRAMES_PER_TOKEN,
            exact_rescore=self.DECODE_EXACT_RESCORE,
            reject_threshold=self.DECODE_REJECT_THRESHOLD,
        )


__all__ = ["AsrSettings", "GrammarKind"]
