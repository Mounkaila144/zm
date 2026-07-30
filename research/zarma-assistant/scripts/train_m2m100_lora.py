"""Fine-tune M2M100-418M sur le corpus Feriji (fr<->zarma) via LoRA.

Reproduit l'approche du papier Feriji (ACL 2024, BLEU 30.06 annoncé en
fr->zarma), mais avec un fine-tuning léger (LoRA, via peft) plutôt qu'un
fine-tuning complet : la machine locale n'a que 8 Go de RAM, insuffisant
pour entraîner les 418M paramètres du modèle en entier avec l'optimiseur
Adam. LoRA n'entraîne qu'une petite fraction des poids (adaptateurs de rang
16 sur les projections d'attention) + la ligne d'embedding du nouveau token
'dje' (zarma, absent des ~100 langues nativement supportées par M2M100 —
voir _m2m100_zarma.py pour comment ce token est ajouté sans corrompre le
modèle).

Entraîne dans les DEUX sens (fr->zarma et zarma->fr) simultanément — le
papier n'a évalué que fr->zarma, on comble ce trou.

Usage :
  uv run python scripts/train_m2m100_lora.py --epochs 2 --max-examples 8000
  uv run python scripts/train_m2m100_lora.py  # jeu complet, tous les epochs
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from datasets import Dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    DataCollatorForSeq2Seq,
    M2M100ForConditionalGeneration,
    M2M100Tokenizer,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
)

from _m2m100_zarma import ZARMA_CODE, add_zarma_language, freeze_embeddings_except

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
MODEL_NAME = "facebook/m2m100_418M"
MAX_LENGTH = 128
SEED = 20260727


def _load_jsonl(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _build_bidirectional(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    examples = []
    for row in rows:
        examples.append(
            {"src_lang": "fr", "tgt_lang": ZARMA_CODE, "src_text": row["french"], "tgt_text": row["zarma"]}
        )
        examples.append(
            {"src_lang": ZARMA_CODE, "tgt_lang": "fr", "src_text": row["zarma"], "tgt_text": row["french"]}
        )
    return examples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument(
        "--max-examples",
        type=int,
        default=None,
        help="Limite le nombre de PAIRES fr/zarma utilisées (avant doublement bidirectionnel). "
        "Utile pour un premier test rapide avant de lancer le jeu complet.",
    )
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--output-dir", default=str(MODELS_DIR / "m2m100-lora-zarma"))
    parser.add_argument("--no-grad-checkpoint", action="store_true")
    parser.add_argument("--eval-samples", type=int, default=300)
    args = parser.parse_args()

    train_rows = _load_jsonl(DATA_DIR / "train.jsonl")
    val_rows = _load_jsonl(DATA_DIR / "val.jsonl")

    rng = random.Random(SEED)
    if args.max_examples:
        train_rows = rng.sample(train_rows, min(args.max_examples, len(train_rows)))
    # Val reste petit pour ne pas ralentir l'évaluation entre époques.
    val_rows = rng.sample(val_rows, min(args.eval_samples, len(val_rows)))

    train_examples = _build_bidirectional(train_rows)
    val_examples = _build_bidirectional(val_rows)
    print(f"Exemples d'entraînement (bidirectionnel) : {len(train_examples)}")
    print(f"Exemples de validation (bidirectionnel)   : {len(val_examples)}")

    print("Chargement du tokenizer et du modèle de base...")
    tokenizer = M2M100Tokenizer.from_pretrained(MODEL_NAME)
    model = M2M100ForConditionalGeneration.from_pretrained(MODEL_NAME)
    zarma_id = add_zarma_language(tokenizer, model)
    print(f"Token zarma enregistré : id={zarma_id}")

    peft_config = LoraConfig(
        task_type=TaskType.SEQ_2_SEQ_LM,
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "out_proj"],
    )
    model = get_peft_model(model, peft_config)
    freeze_embeddings_except(model.get_base_model(), zarma_id)
    model.enable_input_require_grads()  # requis : gradient checkpointing + base gelée (peft)
    model.print_trainable_parameters()

    def preprocess(example: dict[str, str]) -> dict[str, list[int]]:
        tokenizer.src_lang = example["src_lang"]
        tokenizer.tgt_lang = example["tgt_lang"]
        encoded = tokenizer(
            example["src_text"],
            text_target=example["tgt_text"],
            truncation=True,
            max_length=MAX_LENGTH,
        )
        return encoded

    train_dataset = Dataset.from_list(train_examples).map(
        preprocess, remove_columns=["src_lang", "tgt_lang", "src_text", "tgt_text"]
    )
    val_dataset = Dataset.from_list(val_examples).map(
        preprocess, remove_columns=["src_lang", "tgt_lang", "src_text", "tgt_text"]
    )

    data_collator = DataCollatorForSeq2Seq(tokenizer, model=model, label_pad_token_id=-100)

    training_args = Seq2SeqTrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        gradient_checkpointing=not args.no_grad_checkpoint,
        learning_rate=args.learning_rate,
        logging_steps=20,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        predict_with_generate=False,
        report_to=[],
        dataloader_num_workers=0,
        remove_unused_columns=False,
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
    trainer.train()

    print(f"Sauvegarde de l'adaptateur LoRA + tokenizer dans {args.output_dir}")
    model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    print("Terminé.")


if __name__ == "__main__":
    main()
