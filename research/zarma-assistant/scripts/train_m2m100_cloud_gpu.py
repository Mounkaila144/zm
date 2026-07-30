"""Fine-tuning complet de M2M100-418M sur le corpus Feriji (fr<->zarma) — à
exécuter dans un notebook Jupyter avec GPU : Kaggle, Amazon SageMaker
(notebook instance ml.g4dn.xlarge ou supérieur), Google Colab, ou tout autre
environnement équivalent. Le script détecte l'environnement et s'adapte.

Différence avec `train_m2m100_lora.py` (pensé pour le Mac local, 8 Go RAM,
sans GPU) : ici on a un vrai GPU avec assez de mémoire, donc on fait un
fine-tuning COMPLET du modèle (pas de LoRA, pas de bricolage de masquage de
gradient) — plus simple, plus proche de la méthode du papier Feriji
(BLEU 30.06 annoncé en fr->zarma, GPU P100 sur Kaggle — exactement ce setup).

Le seul point qui reste nécessaire indépendamment du GPU : le zarma n'a pas
de code langue natif dans M2M100 (~100 langues fixées). On ajoute un token
__dje__ en réutilisant un emplacement d'embedding déjà réservé dans le
checkpoint (voir commentaires dans add_zarma_language ci-dessous) — vérifié
sur la machine locale avant d'arriver ici, cf. _m2m100_zarma.py du dépôt.

=== Sur Google Colab (voie utilisée et validée pour ce projet) ===
1. colab.research.google.com > Fichier > Nouveau notebook.
2. Exécution > Modifier le type d'exécution > Accélérateur matériel > T4 GPU
   > Enregistrer.
3. Cellule 1 :
   !pip install -q "transformers>=4.42" sacrebleu huggingface_hub datasets accelerate
4. Cellule 2 :
   import os
   os.environ["HF_TOKEN"] = "hf_votre_token_ici"
5. Cellule 3 : coller tout le contenu de ce fichier, exécuter.

=== Sur Kaggle ===
1. Notebook > Settings > Accelerator > GPU P100 (ou GPU T4 x2).
2. Notebook > Settings > Internet > On.
3. Add-ons > Secrets > ajouter un secret nommé HF_TOKEN.
4. Copier-coller ce fichier dans une ou plusieurs cellules, Run All.
Nécessite un compte avec numéro de téléphone vérifié (Settings > Phone
Verification), sinon les options GPU/Internet restent grisées.

=== Sur Amazon SageMaker (notebook instance) ===
1. Créer une "Notebook instance" avec un type d'instance GPU
   (ml.g4dn.xlarge est le moins cher avec GPU — un T4, largement suffisant).
2. Ouvrir Jupyter/JupyterLab, choisir le kernel "conda_pytorch_p310" (ou
   équivalent avec PyTorch pré-installé).
3. Dans une cellule, avant de lancer ce script, définir le token HF :
   %env HF_TOKEN=hf_votre_token_ici
4. Coller ce fichier dans une cellule suivante, l'exécuter.
5. IMPORTANT : penser à "Stop" la notebook instance une fois terminé (dans
   la console SageMaker) — elle facture à l'heure tant qu'elle tourne, même
   inactive.

Ce script est autonome : il télécharge Feriji directement depuis HF (pas
besoin de ré-uploader les fichiers locaux), reconstruit le même split
train/val/test (seed fixe = comparable aux résultats déjà obtenus), fine-tune
M2M100, puis évalue le BLEU sur le même échantillon de 200 phrases de test
utilisé pour le benchmark GLM — pour une comparaison directe et honnête.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

# === Cellule 1 : dépendances (Kaggle/Colab/SageMaker ont déjà torch install
# — le reste est rapide) ===
# !pip install -q "transformers>=4.42" sacrebleu huggingface_hub datasets accelerate

import sacrebleu
import torch
from datasets import Dataset
from huggingface_hub import hf_hub_download
from transformers import (
    DataCollatorForSeq2Seq,
    M2M100ForConditionalGeneration,
    M2M100Tokenizer,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
)

import os

# === Cellule 2 : authentification HF — essaie Kaggle Secrets, puis Colab
# Secrets, puis une variable d'environnement classique (SageMaker :
# %env HF_TOKEN=..., ou n'importe quel autre notebook/terminal). ===
HF_TOKEN = None
try:
    from kaggle_secrets import UserSecretsClient

    HF_TOKEN = UserSecretsClient().get_secret("HF_TOKEN")
except Exception:
    pass

if not HF_TOKEN:
    try:
        from google.colab import userdata  # présent uniquement sur Colab

        HF_TOKEN = userdata.get("HF_TOKEN")
    except Exception:
        pass

if not HF_TOKEN:
    HF_TOKEN = os.environ.get("HF_TOKEN")

assert HF_TOKEN, (
    "HF_TOKEN manquant. Sur Kaggle : ajouter le secret. Sur Colab : ajouter "
    "un secret HF_TOKEN (icône clé, barre latérale gauche) OU exécuter "
    "`import os; os.environ['HF_TOKEN'] = 'hf_...'` dans une cellule avant "
    "celle-ci. Sur SageMaker/autre : `%env HF_TOKEN=hf_...` (notebook) ou "
    "`export HF_TOKEN=hf_...` (terminal)."
)

# Répertoire de sortie :
# - Kaggle impose /kaggle/working (seul dossier persistant/téléchargeable) ;
# - Colab : le disque local de la session est éphémère — si la connexion
#   est coupée trop longtemps (ordinateur fermé, veille...), Colab peut
#   recycler la machine et tout perdre, y compris un entraînement en cours.
#   On monte Google Drive et on y sauvegarde les checkpoints, pour pouvoir
#   reprendre l'entraînement là où il s'est arrêté plutôt que de tout
#   refaire depuis le début.
# - Ailleurs (SageMaker...) : un dossier local classique suffit.
if os.path.isdir("/kaggle/working"):
    WORK_DIR = "/kaggle/working"
else:
    try:
        from google.colab import drive as _colab_drive

        _colab_drive.mount("/content/drive")
        WORK_DIR = "/content/drive/MyDrive/zarma-m2m100"
        print(f"Google Drive monté — checkpoints sauvegardés dans {WORK_DIR}")
    except Exception:
        WORK_DIR = "./output"
os.makedirs(WORK_DIR, exist_ok=True)

MODEL_NAME = "facebook/m2m100_418M"
ZARMA_CODE = "dje"
ZARMA_TOKEN = "__dje__"
PROXY_LANG_CODE = "ha"  # hausa — langue la plus proche dispo nativement
SEED = 20260727
SPLIT_RATIOS = (0.8, 0.1, 0.1)
MAX_LENGTH = 128
BENCH_SAMPLE_SIZE = 200  # même taille que le benchmark GLM, pour comparaison directe

FRENCH_KEYS = ("french", "francais", "français", "fr", "src", "source")
ZARMA_KEYS = ("zarma", "dje", "tgt", "target")


# === Cellule 3 : téléchargement + split Feriji (identique à
# research/zarma-assistant/scripts/download_feriji.py) ===
def _pick_key(row: dict, candidates: tuple[str, ...]) -> str:
    for key in candidates:
        if key in row:
            return key
    raise KeyError(f"Clé introuvable parmi {candidates} dans {sorted(row.keys())}")


def load_feriji() -> dict[str, list[dict[str, str]]]:
    corpus_path = Path(
        hf_hub_download(
            repo_id="27Group/Feriji", repo_type="dataset",
            filename="corpus/fr_dje.jsonl", token=HF_TOKEN,
        )
    )
    rows: list[dict[str, str]] = []
    fr_key = zarma_key = None
    with corpus_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if fr_key is None:
                fr_key = _pick_key(record, FRENCH_KEYS)
                zarma_key = _pick_key(record, ZARMA_KEYS)
            french = (record.get(fr_key) or "").strip()
            zarma = (record.get(zarma_key) or "").strip()
            if french and zarma:
                rows.append({"french": french, "zarma": zarma})

    shuffled = rows[:]
    random.Random(SEED).shuffle(shuffled)
    n = len(shuffled)
    n_train = int(n * SPLIT_RATIOS[0])
    n_val = int(n * SPLIT_RATIOS[1])
    return {
        "train": shuffled[:n_train],
        "val": shuffled[n_train : n_train + n_val],
        "test": shuffled[n_train + n_val :],
    }


# === Cellule 4 : ajout du zarma comme langue M2M100 (sans corrompre le
# modèle — voir docstring du module) ===
def add_zarma_language(tokenizer: M2M100Tokenizer, model: M2M100ForConditionalGeneration) -> int:
    if ZARMA_CODE not in tokenizer.lang_code_to_id:
        tokenizer.add_special_tokens({"additional_special_tokens": [ZARMA_TOKEN]})
        new_id = tokenizer.convert_tokens_to_ids(ZARMA_TOKEN)
        tokenizer.lang_code_to_token[ZARMA_CODE] = ZARMA_TOKEN
        tokenizer.lang_token_to_id[ZARMA_TOKEN] = new_id
        tokenizer.id_to_lang_token[new_id] = ZARMA_TOKEN
        tokenizer.lang_code_to_id[ZARMA_CODE] = new_id
    else:
        new_id = tokenizer.lang_code_to_id[ZARMA_CODE]

    native_size = model.get_input_embeddings().weight.shape[0]
    target_size = max(len(tokenizer), native_size)
    if target_size > native_size:
        model.resize_token_embeddings(target_size)  # agrandit seulement, jamais ne réduit

    embed_weight = model.get_input_embeddings().weight
    ha_id = tokenizer.lang_code_to_id[PROXY_LANG_CODE]
    with torch.no_grad():
        embed_weight[new_id] = embed_weight[ha_id].clone()
        out_embed = model.get_output_embeddings()
        if out_embed is not None and out_embed.weight.data_ptr() != embed_weight.data_ptr():
            out_embed.weight[new_id] = out_embed.weight[ha_id].clone()

    return new_id


def build_bidirectional(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    examples = []
    for row in rows:
        examples.append({"src_lang": "fr", "tgt_lang": ZARMA_CODE, "src_text": row["french"], "tgt_text": row["zarma"]})
        examples.append({"src_lang": ZARMA_CODE, "tgt_lang": "fr", "src_text": row["zarma"], "tgt_text": row["french"]})
    return examples


# === Cellule 5 : chargement modèle/tokenizer + préparation des données ===
print("Téléchargement et split du corpus Feriji...")
splits = load_feriji()
print(f"train={len(splits['train'])}  val={len(splits['val'])}  test={len(splits['test'])}")

print("Chargement du tokenizer et du modèle...")
tokenizer = M2M100Tokenizer.from_pretrained(MODEL_NAME)
model = M2M100ForConditionalGeneration.from_pretrained(MODEL_NAME)
zarma_id = add_zarma_language(tokenizer, model)
print(f"Token zarma enregistré : id={zarma_id}")

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Device : {device}")
model.to(device)

train_examples = build_bidirectional(splits["train"])
val_examples = build_bidirectional(splits["val"][:500])  # sous-échantillon pour l'eval pendant l'entraînement
print(f"Exemples d'entraînement (bidirectionnel) : {len(train_examples)}")


def preprocess(example: dict[str, str]) -> dict[str, list[int]]:
    tokenizer.src_lang = example["src_lang"]
    tokenizer.tgt_lang = example["tgt_lang"]
    return tokenizer(
        example["src_text"], text_target=example["tgt_text"], truncation=True, max_length=MAX_LENGTH
    )


train_dataset = Dataset.from_list(train_examples).map(
    preprocess, remove_columns=["src_lang", "tgt_lang", "src_text", "tgt_text"]
)
val_dataset = Dataset.from_list(val_examples).map(
    preprocess, remove_columns=["src_lang", "tgt_lang", "src_text", "tgt_text"]
)

data_collator = DataCollatorForSeq2Seq(tokenizer, model=model, label_pad_token_id=-100)

# === Cellule 6 : entraînement ===
# Sur un P100 (16 Go), batch_size=16 tient confortablement pour un modèle de
# 418M en fp16. Ajuster si "out of memory" (réduire batch_size, augmenter
# gradient_accumulation_steps pour garder le même batch effectif).
training_args = Seq2SeqTrainingArguments(
    output_dir=f"{WORK_DIR}/m2m100-zarma",
    num_train_epochs=4,  # comme le papier Feriji
    per_device_train_batch_size=16,
    per_device_eval_batch_size=16,
    gradient_accumulation_steps=1,
    learning_rate=3e-5,
    fp16=(device == "cuda"),
    logging_steps=50,
    eval_strategy="epoch",
    save_strategy="epoch",
    save_total_limit=1,
    predict_with_generate=False,
    report_to=[],
    dataloader_num_workers=2,
)

trainer = Seq2SeqTrainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=val_dataset,
    data_collator=data_collator,
    processing_class=tokenizer,
)

print("Début de l'entraînement...")
# Reprise automatique : si un checkpoint existe déjà dans training_args.output_dir
# (ex. après une coupure de session Colab), on repart de là plutôt que de tout
# refaire depuis l'époque 0. Sans checkpoint existant, démarrage normal.
existing_checkpoints = sorted(Path(training_args.output_dir).glob("checkpoint-*"))
if existing_checkpoints:
    print(f"Checkpoint trouvé ({existing_checkpoints[-1].name}) — reprise de l'entraînement.")
    trainer.train(resume_from_checkpoint=True)
else:
    trainer.train()

output_dir = f"{WORK_DIR}/m2m100-zarma-final"
trainer.save_model(output_dir)
tokenizer.save_pretrained(output_dir)
print(f"Modèle sauvegardé dans {output_dir}")

# === Cellule 7 : évaluation BLEU sur le même échantillon que le benchmark GLM ===
print("\nÉvaluation BLEU sur l'échantillon de test (comparable au benchmark GLM)...")
model.eval()
rng = random.Random(SEED)
test_sample = rng.sample(splits["test"], min(BENCH_SAMPLE_SIZE, len(splits["test"])))


def translate_batch(texts: list[str], src_lang: str, tgt_lang: str, batch_size: int = 16) -> list[str]:
    tokenizer.src_lang = src_lang
    forced_bos = tokenizer.get_lang_id(tgt_lang)
    outputs = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        inputs = tokenizer(batch, return_tensors="pt", padding=True, truncation=True, max_length=MAX_LENGTH).to(device)
        with torch.no_grad():
            generated = model.generate(**inputs, forced_bos_token_id=forced_bos, max_length=MAX_LENGTH, num_beams=4)
        outputs.extend(tokenizer.batch_decode(generated, skip_special_tokens=True))
    return outputs


fr_sources = [r["french"] for r in test_sample]
dje_refs = [r["zarma"] for r in test_sample]
dje_sources = [r["zarma"] for r in test_sample]
fr_refs = [r["french"] for r in test_sample]

fr_to_dje_hyps = translate_batch(fr_sources, "fr", ZARMA_CODE)
dje_to_fr_hyps = translate_batch(dje_sources, ZARMA_CODE, "fr")

bleu_fr_to_dje = sacrebleu.corpus_bleu(fr_to_dje_hyps, [dje_refs]).score
bleu_dje_to_fr = sacrebleu.corpus_bleu(dje_to_fr_hyps, [fr_refs]).score

print(f"\nBLEU fr -> zarma : {bleu_fr_to_dje:.1f}  (référence papier Feriji : 30.06)")
print(f"BLEU zarma -> fr : {bleu_dje_to_fr:.1f}  (non évalué par le papier)")
print(f"Pour comparaison — GLM-4.6 sans fine-tuning : fr->zarma 1.0, zarma->fr 8.7")

results = {
    "bleu_fr_to_zarma": bleu_fr_to_dje,
    "bleu_zarma_to_fr": bleu_dje_to_fr,
    "sample_size": len(test_sample),
    "examples": [
        {"source": s, "reference": r, "hypothesis": h}
        for s, r, h in list(zip(fr_sources, dje_refs, fr_to_dje_hyps))[:10]
    ],
}
results_path = f"{WORK_DIR}/bleu_results.json"
with open(results_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\nRésultats détaillés : {results_path}")
print(f"Modèle fine-tuné : {output_dir}")
