"""Élagage des silences de bord et détection d'audio muet, **avant** l'inférence.

Pourquoi ici, et pourquoi ça compte
-----------------------------------

Le coût du modèle est très exactement **linéaire en nombre de trames** : mesuré
sur ce VPS, ~10 ms par trame de 20 ms, de bout en bout et quelle que soit la
longueur (155, 252 et 375 trames donnent 9,5 / 9,9 / 10,4 ms par trame). Une
seconde de silence en tête d'enregistrement coûte donc ~500 ms de calcul, pour
une information nulle.

Or l'enregistrement mobile démarre sur appui et s'arrête sur appui : du silence
en tête et en queue est la règle, pas l'exception. C'est le levier le moins
risqué du chemin, parce qu'il ne touche ni au modèle, ni au décodage, ni aux
seuils de décision — il retire seulement des trames qui ne portent pas de parole.

Deux garde-fous, parce qu'un élagage trop zélé couperait un début de mot :

- le seuil est **relatif au bruit propre de l'enregistrement**, jamais absolu :
  une prise faible (micro éloigné) a un plancher bas et un pic bas, et reste
  traitée comme de la parole ;
- une **marge** généreuse est réintégrée de part et d'autre du segment détecté,
  et seuls les bords sont touchés — jamais l'intérieur, où une pause entre deux
  mots fait partie de l'énoncé.

La détection d'audio **entièrement muet** est un cas à part : elle évite un
passage modèle complet (7,7 s mesurées sur 8 s de silence numérique) pour un
résultat connu d'avance. Le seuil en est délibérément très bas : rater un
silence coûte le temps de calcul habituel, alors que le déclarer à tort
transformerait une vraie parole en abstention. Le premier échec est cher, le
second est faux — on refuse le second.

Ce module est **sans torch** : testable en CI sans modèle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

#: Durée d'une trame d'analyse d'énergie (s). 20 ms = la trame du modèle.
_FRAME_S = 0.02

#: Sous ce pic (dBFS), l'enregistrement est considéré comme muet et n'est jamais
#: envoyé au modèle. Très bas volontairement : le plancher de bruit d'un micro
#: de téléphone se situe entre −60 et −45 dBFS, donc seule une prise
#: numériquement muette (ou quasi) tombe sous ce seuil.
_SILENCE_PEAK_DBFS = -65.0

#: Marge conservée de part et d'autre du segment de parole détecté (s).
#: Une attaque de consonne sourde peut être 15 dB sous la voyelle qui suit :
#: sans marge, l'élagage mangerait le début du premier mot.
_MARGIN_S = 0.30

#: Un segment de parole n'est jamais réduit sous cette durée (s) — au-delà, on
#: préfère laisser passer du silence plutôt que risquer une troncature.
_MIN_KEPT_S = 0.50

#: Écart au-dessus du plancher de bruit à partir duquel une trame est « parole ».
_ABOVE_FLOOR_DB = 8.0

#: Écart maximal sous le pic : borne le seuil vers le haut pour qu'un plancher
#: de bruit élevé (enregistrement bruité) ne fasse pas passer tout l'énoncé
#: sous le seuil.
_BELOW_PEAK_DB = 35.0


@dataclass(frozen=True)
class TrimResult:
    """Issue de l'analyse : échantillons à transcrire, ou constat de silence."""

    samples: np.ndarray
    #: L'enregistrement ne contient aucune parole exploitable : ne pas appeler
    #: le modèle, s'abstenir (texte vide) comme le ferait le décodeur.
    is_silent: bool
    #: Durées avant/après, pour la journalisation et la mesure du gain.
    original_seconds: float
    kept_seconds: float

    @property
    def trimmed_seconds(self) -> float:
        return max(0.0, self.original_seconds - self.kept_seconds)


def _frame_db(samples: np.ndarray, frame_length: int) -> np.ndarray:
    """Niveau RMS par trame, en dBFS (``-inf`` pour une trame nulle)."""
    usable = (len(samples) // frame_length) * frame_length
    if usable == 0:
        return np.empty(0, dtype=np.float64)
    frames = samples[:usable].reshape(-1, frame_length).astype(np.float64)
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    with np.errstate(divide="ignore"):
        return 20.0 * np.log10(rms)


def analyse(
    samples: np.ndarray,
    sample_rate: int,
    *,
    margin_s: float = _MARGIN_S,
    silence_peak_dbfs: float = _SILENCE_PEAK_DBFS,
) -> TrimResult:
    """Détecte le silence total et élague les silences de **bord** uniquement."""
    original_seconds = len(samples) / sample_rate if sample_rate else 0.0
    frame_length = max(1, int(_FRAME_S * sample_rate))
    levels = _frame_db(samples, frame_length)

    if levels.size == 0:
        return TrimResult(samples, True, original_seconds, original_seconds)

    finite = levels[np.isfinite(levels)]
    peak = float(finite.max()) if finite.size else -math.inf
    if peak <= silence_peak_dbfs:
        return TrimResult(samples, True, original_seconds, original_seconds)

    # Seuil : au-dessus du plancher propre de l'enregistrement, mais jamais trop
    # loin sous le pic — les deux bornes protègent des cas opposés (prise très
    # propre / prise très bruitée).
    floor = float(np.percentile(finite, 10)) if finite.size else peak - _BELOW_PEAK_DB
    threshold = max(floor + _ABOVE_FLOOR_DB, peak - _BELOW_PEAK_DB)
    voiced = np.flatnonzero(levels >= threshold)
    if voiced.size == 0:
        # Le pic dépasse le seuil de silence mais aucune trame ne se détache :
        # on ne coupe rien et on laisse le décodeur juger.
        return TrimResult(samples, False, original_seconds, original_seconds)

    margin_frames = max(1, int(round(margin_s / _FRAME_S)))
    first = max(0, int(voiced[0]) - margin_frames)
    last = min(len(levels) - 1, int(voiced[-1]) + margin_frames)

    start = first * frame_length
    end = min(len(samples), (last + 1) * frame_length)
    if (end - start) < int(_MIN_KEPT_S * sample_rate):
        # Segment trop court pour être élagué sans risque : on garde tout.
        return TrimResult(samples, False, original_seconds, original_seconds)

    kept = samples[start:end]
    return TrimResult(kept, False, original_seconds, len(kept) / sample_rate)


__all__ = ["TrimResult", "analyse"]
