"""Charge le modèle M2M100 fine-tuné (sauvegardé sur Google Drive par
train_m2m100_cloud_gpu.py) et permet de traduire librement des phrases —
fr -> zarma ou zarma -> fr — à coller dans une cellule Colab.

Peut être exécuté dans la même session Colab que l'entraînement (le modèle
est encore en mémoire, mais ce script recharge proprement depuis Drive pour
être utilisable aussi dans une toute nouvelle session) ou dans une session
fraîche : il remonte Google Drive si besoin.

=== Usage ===
1. Coller ce fichier dans une cellule Colab, l'exécuter (charge le modèle,
   affiche deux exemples).
2. Dans une cellule suivante, appeler directement :
     to_zarma("Votre phrase en français ici.")
     to_french("Votre phrase en zarma ici.")
   Chaque appel affiche le résultat — modifier le texte et ré-exécuter la
   cellule pour tester d'autres phrases.
"""

from __future__ import annotations

import os

import torch
from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

# === Cellule 1 : monter Drive si besoin (déjà fait si on est dans la même
# session que l'entraînement) ===
if not os.path.isdir("/content/drive/MyDrive"):
    from google.colab import drive as _colab_drive

    _colab_drive.mount("/content/drive")

MODEL_PATH = "/content/drive/MyDrive/zarma-m2m100/m2m100-zarma-final"
ZARMA_CODE = "dje"
ZARMA_TOKEN = "__dje__"
MAX_LENGTH = 128

assert os.path.isdir(MODEL_PATH), (
    f"Modèle introuvable dans {MODEL_PATH} — vérifier que l'entraînement "
    "a bien terminé et sauvegardé (voir la sortie de train_m2m100_cloud_gpu.py)."
)

# === Cellule 2 : chargement (une fois par session) ===
print("Chargement du modèle...")
# src_lang/tgt_lang forcés à "fr" explicitement : le tokenizer sauvegardé en
# fin d'entraînement a gardé "dje" comme dernière langue active dans sa
# config (tokenizer_config.json), et la reconstruction interne de
# M2M100Tokenizer essaie de la résoudre AVANT même que ce script ait pu
# rajouter "dje" dans ses dictionnaires internes -> KeyError immédiat au
# chargement sinon. "fr" est une langue native de M2M100, donc sans risque.
tokenizer = M2M100Tokenizer.from_pretrained(MODEL_PATH, src_lang="fr", tgt_lang="fr")
model = M2M100ForConditionalGeneration.from_pretrained(MODEL_PATH)
device = "cuda" if torch.cuda.is_available() else "cpu"
model.to(device)
model.eval()

# 'dje' comme code langue n'est PAS restauré automatiquement par
# from_pretrained : ce sont des dictionnaires internes spécifiques à
# M2M100Tokenizer (lang_code_to_id, etc.), pas le format de sérialisation
# standard HF. Le token __dje__ lui-même est bien restauré (vocab inchangé),
# donc on peut re-brancher les dictionnaires sans recalculer d'ID.
if ZARMA_CODE not in tokenizer.lang_code_to_id:
    zarma_id = tokenizer.convert_tokens_to_ids(ZARMA_TOKEN)
    tokenizer.lang_code_to_token[ZARMA_CODE] = ZARMA_TOKEN
    tokenizer.lang_token_to_id[ZARMA_TOKEN] = zarma_id
    tokenizer.id_to_lang_token[zarma_id] = ZARMA_TOKEN
    tokenizer.lang_code_to_id[ZARMA_CODE] = zarma_id

print(f"Modèle chargé sur {device}.")


# === Cellule 3 : fonctions de traduction ===
def translate(text: str, src_lang: str, tgt_lang: str, num_beams: int = 4) -> str:
    tokenizer.src_lang = src_lang
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=MAX_LENGTH).to(device)
    forced_bos = tokenizer.get_lang_id(tgt_lang)
    with torch.no_grad():
        generated = model.generate(
            **inputs, forced_bos_token_id=forced_bos, max_length=MAX_LENGTH, num_beams=num_beams
        )
    return tokenizer.batch_decode(generated, skip_special_tokens=True)[0]


def to_zarma(text: str) -> str:
    result = translate(text, "fr", ZARMA_CODE)
    print(f"FR : {text}\nDJE: {result}")
    return result


def to_french(text: str) -> str:
    result = translate(text, ZARMA_CODE, "fr")
    print(f"DJE: {text}\nFR : {result}")
    return result


# === Exemples ===
print("\n--- Exemples ---")
to_zarma("Bonjour, comment allez-vous ?")
print()
to_french("Mate ni go?")

print(
    "\nPrêt. Dans une nouvelle cellule, appeler par exemple :\n"
    '  to_zarma("Votre phrase en français ici.")\n'
    '  to_french("Votre phrase en zarma ici.")'
)
