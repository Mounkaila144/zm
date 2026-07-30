"""Phase 0 — benchmark de traduction fr<->zarma par un LLM généraliste (GLM,
via le point d'accès compatible Anthropic de z.ai).

Répond à la question : un LLM sans fine-tuning peut-il déjà traduire
correctement entre français et zarma (glossaire + few-shot uniquement) ?
Si la direction zarma->français est bonne, le pipeline conversationnel peut
sauter l'étape de traduction dédiée pour cette direction (cf. Amendement A,
docs/assistant-conversationnel-zarma-strategie.md).

Prérequis : `python scripts/download_feriji.py` déjà exécuté (produit
data/{train,val,test}.jsonl et data/glossary.json), et ZAI_KEY dans .env
(clé z.ai — https://z.ai). On utilise le SDK Python `anthropic` pointé vers
https://api.z.ai/api/anthropic, qui reproduit l'API Anthropic ; le modèle
appelé est GLM (par défaut glm-4.6), pas Claude.

BLEU sur le zarma est une mesure approximative : l'orthographe zarma n'est
pas standardisée (accents, tons, variantes) entre sources — traiter le score
comme un indicateur directionnel, pas une vérité absolue. La relecture
qualitative du fichier JSON de résultats par un locuteur natif reste le
signal qui compte le plus.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import sacrebleu
from anthropic import Anthropic
from dotenv import load_dotenv
from tqdm import tqdm

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

ZAI_BASE_URL = "https://api.z.ai/api/anthropic"

# Prix approximatifs en $/million de tokens (in/out) — confirmés pour GLM-4.6
# uniquement (0.60 $/2.20 $, cache lu à 0.11 $) au moment de l'écriture ;
# à revérifier sur https://z.ai avant de tirer des conclusions budgétaires
# précises sur d'autres modèles, la tarification évolue.
PRICING_PER_MTOK = {
    "glm-4.6": (0.60, 2.20),
}

FR_TO_ZARMA_INSTRUCTIONS = (
    "Tu es un traducteur professionnel français vers zarma (langue songhay "
    "parlée au Niger, code ISO dje). On te donne un glossaire de référence "
    "et des exemples. Traduis STRICTEMENT la phrase française fournie en "
    "zarma. Réponds uniquement avec la traduction, une seule ligne, sans "
    "guillemets ni commentaire.\n\n"
    "Glossaire de référence (français -> zarma) :\n{glossary}\n\n"
    "Exemples :\n{examples}"
)

ZARMA_TO_FR_INSTRUCTIONS = (
    "Tu es un traducteur professionnel zarma vers français (langue songhay "
    "parlée au Niger, code ISO dje). On te donne un glossaire de référence "
    "et des exemples. Traduis STRICTEMENT la phrase zarma fournie en "
    "français. Réponds uniquement avec la traduction, une seule ligne, sans "
    "guillemets ni commentaire.\n\n"
    "Glossaire de référence (français -> zarma, utilisable dans les deux "
    "sens) :\n{glossary}\n\n"
    "Exemples :\n{examples}"
)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def add(self, other) -> None:
        self.input_tokens += getattr(other, "input_tokens", 0) or 0
        self.output_tokens += getattr(other, "output_tokens", 0) or 0
        self.cache_creation_input_tokens += (
            getattr(other, "cache_creation_input_tokens", 0) or 0
        )
        self.cache_read_input_tokens += getattr(other, "cache_read_input_tokens", 0) or 0


def _load_jsonl(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _format_glossary(glossary: list[dict[str, str]]) -> str:
    return "\n".join(f"{g['french']} -> {g['zarma']}" for g in glossary)


def _format_examples(examples: list[dict[str, str]], direction: str) -> str:
    blocks = []
    for ex in examples:
        if direction == "fr_to_zarma":
            blocks.append(f"Français: {ex['french']}\nZarma: {ex['zarma']}")
        else:
            blocks.append(f"Zarma: {ex['zarma']}\nFrançais: {ex['french']}")
    return "\n\n".join(blocks)


def _build_system(
    direction: str,
    glossary: list[dict[str, str]],
    examples: list[dict[str, str]],
    use_cache_control: bool,
) -> list[dict]:
    template = FR_TO_ZARMA_INSTRUCTIONS if direction == "fr_to_zarma" else ZARMA_TO_FR_INSTRUCTIONS
    text = template.format(
        glossary=_format_glossary(glossary),
        examples=_format_examples(examples, direction),
    )
    block = {"type": "text", "text": text}
    if use_cache_control:
        block["cache_control"] = {"type": "ephemeral"}
    return [block]


def _translate(
    client: Anthropic,
    model: str,
    system: list[dict],
    sentence: str,
    direction: str,
    usage: Usage,
    max_retries: int = 3,
) -> str:
    prompt = (
        f"Traduis en zarma : {sentence}"
        if direction == "fr_to_zarma"
        else f"Traduis en français : {sentence}"
    )
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=256,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            usage.add(response.usage)
            return response.content[0].text.strip().strip('"').strip("«»")
        except Exception as exc:  # noqa: BLE001 — on veut retenter sur toute erreur réseau/API
            if attempt == max_retries - 1:
                raise
            wait = 2**attempt
            print(f"  (retry {attempt + 1}/{max_retries} après erreur: {exc}, attente {wait}s)")
            time.sleep(wait)
    raise RuntimeError("unreachable")


def _estimate_cost(model: str, usage: Usage) -> float:
    key = next((k for k in PRICING_PER_MTOK if k in model.lower()), None)
    if key is None:
        return float("nan")
    price_in, price_out = PRICING_PER_MTOK[key]
    # Cache lu au tarif GLM-4.6 confirmé (0.11 $/MTok) ; le cache écrit n'a
    # pas de tarif distinct documenté pour z.ai, on le compte au prix input.
    cache_read_price = 0.11 if key == "glm-4.6" else price_in * 0.1
    cost = (
        usage.input_tokens * price_in
        + usage.cache_creation_input_tokens * price_in
        + usage.cache_read_input_tokens * cache_read_price
    ) / 1_000_000
    cost += usage.output_tokens * price_out / 1_000_000
    return cost


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-size", type=int, default=200)
    parser.add_argument("--few-shot-count", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260727)
    parser.add_argument(
        "--model",
        default="glm-4.6",
        help="ID de modèle GLM servi par z.ai (défaut : glm-4.6).",
    )
    parser.add_argument(
        "--no-cache-control",
        action="store_true",
        help=(
            "Désactive cache_control dans le system prompt. À utiliser si "
            "l'API renvoie une erreur sur ce champ (le support du prompt "
            "caching côté z.ai n'est pas documenté avec certitude)."
        ),
    )
    args = parser.parse_args()

    load_dotenv()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    zai_key = os.environ.get("ZAI_KEY")
    if not zai_key:
        raise SystemExit(
            "ZAI_KEY manquant. Copier .env.example vers .env et renseigner la clé z.ai."
        )

    test_rows = _load_jsonl(DATA_DIR / "test.jsonl")
    train_rows = _load_jsonl(DATA_DIR / "train.jsonl")
    glossary = json.loads((DATA_DIR / "glossary.json").read_text(encoding="utf-8"))

    rng = random.Random(args.seed)
    sample = rng.sample(test_rows, min(args.sample_size, len(test_rows)))
    few_shot = train_rows[: args.few_shot_count]

    client = Anthropic(api_key=zai_key, base_url=ZAI_BASE_URL)
    usage = Usage()

    use_cache_control = not args.no_cache_control
    systems = {
        "fr_to_zarma": _build_system("fr_to_zarma", glossary, few_shot, use_cache_control),
        "zarma_to_fr": _build_system("zarma_to_fr", glossary, few_shot, use_cache_control),
    }

    results = {"fr_to_zarma": [], "zarma_to_fr": []}
    for direction in ("fr_to_zarma", "zarma_to_fr"):
        src_key, ref_key = (
            ("french", "zarma") if direction == "fr_to_zarma" else ("zarma", "french")
        )
        print(f"\n== Direction {direction} — {len(sample)} phrases ==")
        for row in tqdm(sample, desc=direction):
            hypothesis = _translate(
                client, args.model, systems[direction], row[src_key], direction, usage
            )
            results[direction].append(
                {"source": row[src_key], "reference": row[ref_key], "hypothesis": hypothesis}
            )

    bleu_scores = {}
    for direction, items in results.items():
        hyps = [i["hypothesis"] for i in items]
        refs = [[i["reference"] for i in items]]
        bleu_scores[direction] = sacrebleu.corpus_bleu(hyps, refs).score

    cost = _estimate_cost(args.model, usage)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = RESULTS_DIR / f"bench_{timestamp}.json"
    json_path.write_text(
        json.dumps(
            {
                "model": args.model,
                "sample_size": len(sample),
                "few_shot_count": args.few_shot_count,
                "seed": args.seed,
                "bleu": bleu_scores,
                "usage": vars(usage),
                "estimated_cost_usd": cost,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    summary_path = RESULTS_DIR / f"bench_{timestamp}_summary.md"
    lines = [
        f"# Benchmark traduction — {timestamp}",
        "",
        f"Modèle : `{args.model}` — échantillon : {len(sample)} phrases — "
        f"few-shot : {args.few_shot_count} exemples",
        "",
        "## Scores BLEU",
        "",
        f"- fr -> zarma : **{bleu_scores['fr_to_zarma']:.1f}**",
        f"- zarma -> fr : **{bleu_scores['zarma_to_fr']:.1f}**",
        "",
        f"(Pour référence, le M2M100 fine-tuné du papier Feriji obtient "
        f"BLEU 30.06 en fr -> zarma.)",
        "",
        f"## Coût / usage",
        "",
        f"- tokens input : {usage.input_tokens}",
        f"- tokens output : {usage.output_tokens}",
        f"- tokens écrits en cache : {usage.cache_creation_input_tokens}",
        f"- tokens lus depuis le cache : {usage.cache_read_input_tokens}",
        f"- coût estimé : ${cost:.3f}" if cost == cost else "- coût estimé : n/a",
        "",
        "## Exemples (5 premiers par direction)",
        "",
    ]
    for direction, items in results.items():
        lines.append(f"### {direction}")
        for item in items[:5]:
            lines.append(f"- source: {item['source']}")
            lines.append(f"  référence: {item['reference']}")
            lines.append(f"  hypothèse: {item['hypothesis']}")
        lines.append("")
    summary_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"\nRésultats détaillés : {json_path}")
    print(f"Résumé lisible     : {summary_path}")
    print(f"BLEU fr->zarma: {bleu_scores['fr_to_zarma']:.1f}  |  zarma->fr: {bleu_scores['zarma_to_fr']:.1f}")
    print(f"Coût estimé: ${cost:.3f}" if cost == cost else "Coût estimé: n/a")


if __name__ == "__main__":
    main()
