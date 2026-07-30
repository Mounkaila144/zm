"""Teste la reconnaissance vocale (voix -> texte) sur de vrais enregistrements
zarma, avec un Whisper généraliste public (pas spécialisé zarma) — pour
avoir un premier repère avant d'investir dans un entraînement dédié.

=== Pourquoi un modèle généraliste, pas un modèle "zarma" ===
Trois pistes de modèles zarma spécialisés ont été essayées et ont toutes
échoué :
1. MMS-1B-all (Meta) : la doc officielle annonce le zarma ('dje') supporté
   pour l'ASR, mais le vocabulaire réel du checkpoint HF ne le contient pas
   — incohérence documentation/modèle publié.
2. Mamadou2727/whisper-medium-zarma-model1 : existe et est documenté
   (WER 41.4 annoncé par les auteurs), mais accès restreint manuellement
   (403 tant que l'accès n'est pas approuvé par l'auteur).
3. Mamadou2727/whisper-medium-zarma-model (sans le "1") : dépôt public mais
   VIDE (aucun poids de modèle, upload abandonné).

Faute de modèle zarma spécialisé immédiatement utilisable, ce script utilise
Whisper-large-v3 (OpenAI, 100% public, jamais bloqué) tel quel — sans
entraînement sur le zarma. Il faut donc s'attendre à des résultats moyens
voire mauvais : Whisper n'a presque pas vu de zarma pendant son
entraînement. C'est un repère de départ ("zéro effort"), pas une solution.

La vraie solution, si ce test confirme que c'est insuffisant : fine-tuner
nous-mêmes Whisper sur les enregistrements zarma collectés (comme on l'a
fait pour la traduction avec M2M100) — il faudra alors transcrire à la main
le contenu exact de chaque enregistrement (possible puisque vous êtes
locuteur natif) pour constituer les données d'entraînement.

=== Avant de lancer, sur Google Colab ===
1. Enregistrer quelques phrases courtes en zarma (voix mémo, n'importe quel
   format : .wav, .m4a, .mp3, .opus...).
2. Les envoyer sur Google Drive, dans "MyDrive/zarma-audio-test/".
3. Exécution > Modifier le type d'exécution > T4 GPU.
4. Cellule 1 :
   !pip install -q transformers librosa soundfile
5. Cellule 2 : coller tout le contenu de ce fichier, exécuter.

Affiche la transcription de chaque fichier au fur et à mesure — comparez
avec ce que vous avez vraiment dit.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import torch
from transformers import pipeline

# === Cellule : monter Drive si besoin ===
if not os.path.isdir("/content/drive/MyDrive"):
    from google.colab import drive as _colab_drive

    _colab_drive.mount("/content/drive")

AUDIO_DIR = Path("/content/drive/MyDrive/zarma-audio-test")
AUDIO_EXTENSIONS = {".wav", ".m4a", ".mp3", ".flac", ".ogg", ".opus"}

audio_files = sorted(p for p in AUDIO_DIR.glob("*") if p.suffix.lower() in AUDIO_EXTENSIONS)
assert audio_files, (
    f"Aucun fichier audio trouvé dans {AUDIO_DIR}. Créer ce dossier sur "
    "Google Drive et y déposer quelques enregistrements."
)
print(f"{len(audio_files)} fichier(s) audio trouvé(s) : {[f.name for f in audio_files]}")

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Device : {device}")

WHISPER_MODEL = "openai/whisper-large-v3"  # public, généraliste — pas spécialisé zarma

print(f"\nChargement de {WHISPER_MODEL} (public, ~3 Go)...")
whisper_pipe = pipeline(
    "automatic-speech-recognition",
    model=WHISPER_MODEL,
    device=0 if device == "cuda" else -1,
    # chunk_length_s : Whisper ne traite que 30s d'un coup ; au-delà, découpe
    # automatiquement en fenêtres glissantes plutôt que de lever une erreur
    # (certains de vos enregistrements dépassent 30s).
    chunk_length_s=30,
)

print("\n" + "=" * 70)
print(f"Transcriptions ({WHISPER_MODEL}, zéro-shot, non spécialisé zarma)")
print("=" * 70)
results: dict[str, str] = {}
for audio_path in audio_files:
    text = whisper_pipe(str(audio_path))["text"].strip()
    results[audio_path.name] = text
    print(f"\n{audio_path.name} : {text}")

results_path = AUDIO_DIR / "asr_results.json"
with open(results_path, "w", encoding="utf-8") as f:
    json.dump({"model_used": WHISPER_MODEL, "transcriptions": results}, f, ensure_ascii=False, indent=2)

print("\n" + "=" * 70)
print(f"Résultats sauvegardés dans {results_path}")
print(
    "Comparez chaque ligne à ce que vous avez vraiment dit. Si c'est "
    "insuffisant (attendu, ce modèle n'a jamais appris le zarma), l'étape "
    "suivante est de fine-tuner Whisper sur vos propres enregistrements."
)
