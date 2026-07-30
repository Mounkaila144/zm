"""Compare le modèle maison (v1, entraîné sur Colab) au modèle Omnilingual de
Meta servi par `services/asr`, sur exactement le même corpus.

Ce qui rend la comparaison honnête
----------------------------------

**Même métrique.** Ni le CER ni le WER ne sont comparés : seul compte le
**nombre reconnu**. Les deux systèmes rendent une forme canonique de la
grammaire, qu'on relit avec `parse()` ; c'est la seule mesure qui parle de la
calculatrice.

**Même décodeur.** Le service applique déjà la recherche en faisceau contrainte
(`app/decoding.py`) sur les logits d'Omnilingual, et les résultats du modèle
maison ont été produits par ce même décodeur. Aucun des deux ne bénéficie d'un
post-traitement que l'autre n'aurait pas.

**Mêmes clips, sans fuite.** Le score du modèle maison pour une voix vient
toujours du repli où cette voix était **tenue à l'écart** : il ne l'avait jamais
entendue. Omnilingual, lui, n'a vu aucun de ces enregistrements. Les deux sont
donc évalués en conditions d'utilisateur inconnu.

Le seul déséquilibre restant est celui qu'on cherche à mesurer : le modèle
maison a appris le zarma sur les 7 autres voix, Omnilingual ne l'a jamais appris.

    cd /Users/pc/project/zarma
    research/zarma-assistant/.venv/bin/python \
        research/zarma-assistant/scripts/compare_asr_models.py \
        --endpoint https://mon-vps.example/transcribe \
        --token "$ASR_ENDPOINT_TOKEN" \
        --results research/zarma-assistant/data/resultats.json
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import statistics
import sys
import time
from pathlib import Path

import httpx

try:
    from zarma_numbers import parse
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "zarma_numbers" / "src"))
    from zarma_numbers import parse

CORPUS = Path(__file__).resolve().parent.parent / "data" / "asr_corpus"


def _recognize(client: httpx.Client, endpoint: str, path: Path, anon_id: str) -> dict:
    """Appelle `POST /api/v1/recognize` — modèle **et** décodeur contraint.

    `consent_id` est volontairement omis : le fournir ferait enregistrer chaque
    clip comme contribution dans la base de production, alors qu'on ne fait que
    mesurer.

    Réessaie sur 429 : l'API limite à 10 requêtes/minute, et un dépassement
    ponctuel ne doit pas faire perdre le clip.
    """
    files = {"audio": (path.name, path.read_bytes(), "audio/wav")}
    for attempt in range(4):
        try:
            response = client.post(endpoint, data={"anon_id": anon_id}, files=files)
        except httpx.TransportError as exc:
            # Coupure réseau ou résolution DNS en échec : transitoire dans la
            # quasi-totalité des cas. Sans ce rattrapage, une seconde de DNS
            # défaillant fait perdre tout le reste du corpus — chaque échec
            # étant instantané, la boucle épuise les 500 clips en quelques
            # secondes sans qu'aucune requête ne parte.
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
            continue
        if response.status_code == 429:
            wait = float(response.headers.get("Retry-After", 6 * (attempt + 1)))
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError("échec persistant après 4 essais")


def _stratified(rows: list[dict], size: int) -> list[dict]:
    """Échantillon réparti sur toutes les voix, et sur toute la plage de
    grandeurs. Prendre les N premiers du manifest donnerait surtout des petits
    nombres d'une seule voix — les cas les plus faciles."""
    if not size or size >= len(rows):
        return rows
    by_voice: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        by_voice[row["voix"]].append(row)
    for group in by_voice.values():
        group.sort(key=lambda r: int(r["etiquette"]))
    quota = max(1, size // len(by_voice))
    sample: list[dict] = []
    for group in by_voice.values():
        step = max(1, len(group) // quota)
        sample.extend(group[::step][:quota])
    return sample


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, help="URL complète de POST /transcribe")
    # Lu dans l'environnement par défaut : le jeton n'a jamais à être tapé dans
    # une ligne de commande, où il finirait dans l'historique du shell.
    parser.add_argument(
        "--token",
        default=os.environ.get("ASR_ENDPOINT_TOKEN", ""),
        help="Jeton Bearer ; par défaut la variable d'environnement ASR_ENDPOINT_TOKEN",
    )
    parser.add_argument("--results", type=Path, help="resultats.json du modèle maison, pour la comparaison")
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument("--limit", type=int, default=0, help="N'envoyer que les N premiers clips (essai de câblage)")
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="Échantillon réparti sur les 8 voix et toutes les grandeurs (0 = tout le corpus)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=10.0,
        help="Requêtes par minute (défaut 10, la limite de l'API)",
    )
    parser.add_argument(
        "--anon-id",
        default="00000000-0000-4000-8000-000000000001",
        help="UUID anonyme exigé par /recognize",
    )
    parser.add_argument(
        "--app-build",
        type=int,
        default=None,
        help="Valeur de X-App-Build (défaut : le minimum publié par /mobile/config)",
    )
    parser.add_argument("--no-resume", action="store_true", help="Ignorer la sortie précédente")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "comparaison_asr.json",
    )
    args = parser.parse_args()

    with (args.corpus / "manifest.csv").open(encoding="utf-8") as handle:
        rows = [r for r in csv.DictReader(handle) if not r["etiquette"].startswith("op")]
    rows = _stratified(rows, args.sample)
    if args.limit:
        rows = rows[: args.limit]

    # `mobile_version_middleware` bloque /recognize avec un 426 si l'en-tête
    # X-App-Build est absent ou inférieur au minimum publié. Le minimum est lu
    # sur le service lui-même plutôt que codé en dur : il changera.
    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    build = args.app_build
    if build is None:
        config_url = args.endpoint.rsplit("/", 1)[0] + "/mobile/config"
        try:
            build = int(httpx.get(config_url, timeout=20).json()["minimum_supported_build"])
            print(f"build minimal exigé par le service : {build}")
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"Impossible de lire {config_url} : {exc}\nForcer avec --app-build.")
    headers["X-App-Build"] = str(build)
    # Reprise : les clips déjà mesurés sont relus depuis la sortie précédente.
    # Un run de 15 minutes ne doit pas être à refaire pour une coupure réseau.
    records: list[dict] = []
    if args.output.exists() and not args.no_resume:
        records = json.loads(args.output.read_text(encoding="utf-8"))
        seen = {r["fichier"] for r in records}
        before = len(rows)
        rows = [r for r in rows if r["fichier"] not in seen]
        if before != len(rows):
            print(f"reprise : {before - len(rows)} clips déjà mesurés, {len(rows)} restants")

    per_voice: dict[str, list[bool]] = collections.defaultdict(list)
    for record in records:
        per_voice[record["voix"]].append(record["juste"])
    decisions: collections.Counter[str] = collections.Counter(
        r["decision"] for r in records if r.get("decision")
    )
    failures = consecutive = 0
    interval = 60.0 / args.rate if args.rate > 0 else 0.0
    started = time.time()
    print(f"{len(rows)} clips à envoyer, {args.rate:g}/min -> environ {len(rows) * interval / 60:.0f} min")

    with httpx.Client(headers=headers, timeout=args.timeout) as client:
        for index, row in enumerate(rows, start=1):
            path = args.corpus / row["fichier"]
            expected = int(row["etiquette"])
            call_started = time.time()
            try:
                payload = _recognize(client, args.endpoint, path, args.anon_id)
            except Exception as exc:  # noqa: BLE001 - réseau : on continue, on compte
                failures += 1
                consecutive += 1
                print(f"  échec sur {path.name} : {exc}")
                # Dix échecs d'affilée : le service est tombé ou le réseau est
                # coupé. Continuer ne ferait que consommer le corpus à vide —
                # mieux vaut s'arrêter et garder ce qui est déjà mesuré.
                if consecutive >= 10:
                    print("  10 échecs consécutifs — arrêt. Relancer pour reprendre.")
                    break
                time.sleep(interval)
                continue
            consecutive = 0

            value = payload.get("recognized_number")
            juste = value == expected
            decisions[payload.get("decision", "?")] += 1
            per_voice[row["voix"]].append(juste)
            records.append(
                {
                    "fichier": row["fichier"],
                    "voix": row["voix"],
                    "etiquette": expected,
                    "attendu": row["texte_zarma"],
                    "obtenu": payload.get("zarma_text", ""),
                    "lu": value,
                    "juste": juste,
                    "decision": payload.get("decision"),
                    "confiance": payload.get("confidence"),
                    "modele": payload.get("model_version"),
                }
            )
            if index % 10 == 0:
                done = sum(1 for r in records if r["juste"])
                print(
                    f"  {index}/{len(rows)}  justes {done / len(records):.1%}"
                    f"  ({time.time() - started:.0f}s)",
                    flush=True,
                )
            # Sauvegarde périodique : n'écrire qu'à la fin faisait perdre un run
            # entier sur la moindre coupure, et la reprise n'avait rien à relire.
            if index % 25 == 0:
                args.output.write_text(
                    json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            # Cadence respectée côté client : mieux vaut attendre que collecter
            # des 429 et fausser la mesure par des clips perdus.
            remaining = interval - (time.time() - call_started)
            if remaining > 0 and index < len(rows):
                time.sleep(remaining)

    if not records:
        raise SystemExit("Aucune transcription obtenue — vérifier --endpoint et --token.")

    args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(1 for r in records if r["juste"])
    versions = {r["modele"] for r in records if r["modele"]}
    print(f"\n=== SERVICE VPS ({', '.join(sorted(versions)) or 'modèle inconnu'}) — {len(records)} nombres ===")
    print(f"  nombre exact : {total / len(records):.1%}   ({total}/{len(records)})")
    print(f"  décisions    : {dict(decisions)}")
    if failures:
        print(f"  échecs réseau: {failures}")

    ours: dict[str, float] = {}
    if args.results and args.results.exists():
        for entry in json.loads(args.results.read_text(encoding="utf-8")):
            if "contraint" in entry:
                ours[entry["voix"]] = entry["contraint"]["nombre_exact"]

    print(f"\n{'voix':>6} {'Omnilingual':>12} {'maison v1':>11}   écart")
    theirs_all: list[float] = []
    ours_all: list[float] = []
    for voice in sorted(per_voice, key=lambda v: int(v[1:])):
        results = per_voice[voice]
        theirs = sum(results) / len(results)
        theirs_all.append(theirs)
        mine = ours.get(voice)
        if mine is None:
            print(f"{voice:>6} {theirs:>11.1%} {'-':>11}")
            continue
        ours_all.append(mine)
        delta = (mine - theirs) * 100
        print(f"{voice:>6} {theirs:>11.1%} {mine:>11.1%}   {delta:+5.1f} pt")

    if ours_all:
        print(
            f"\n  moyenne : Omnilingual {statistics.mean(theirs_all):.1%}  |  "
            f"maison {statistics.mean(ours_all):.1%}"
        )

    # Les erreurs communes disent ce qui est dur dans le corpus lui-même (audio
    # ambigu, mot rare) ; les erreurs propres à un modèle disent ce qui lui
    # manque à lui. Sans cette séparation on ne sait pas quoi corriger.
    print("\n=== où Omnilingual se trompe ===")
    wrong = [r for r in records if not r["juste"]]
    print(f"  {len(wrong)} erreurs")
    for record in wrong[:15]:
        print(
            f"  {record['voix']:>4} {record['etiquette']:>9} -> {str(record['lu']):>9}"
            f"   « {record['attendu'][:42]} »"
        )
    print(f"\nDétail complet : {args.output}")


if __name__ == "__main__":
    main()
