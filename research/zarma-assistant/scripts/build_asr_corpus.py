"""Consolide les clips ASR découpés à la main en un jeu de données propre.

Source (jamais modifiée) : un dossier par locuteur (`v1/`, `v2/`, …) contenant
des clips déjà découpés et étiquetés à la main `v<N>-<nombre>.wav`, plus un
dossier `operation/` contenant les mots d'opérateur `v<N><signe>.wav`
(signes : + - * :).

Sortie : `data/asr_corpus/` — un clip par fichier sous un nom normalisé
`<locuteur>_<étiquette>.wav`, plus `manifest.csv` (locuteur, étiquette, texte
zarma attendu, durée). Le texte zarma n'est PAS saisi à la main : il est
produit par `zarma_numbers.generate()`, donc toujours cohérent avec la
grammaire que la calculatrice sait analyser.

Le script refuse de deviner : tout fichier dont l'étiquette est illisible ou
hors grammaire est écarté et listé en fin de rapport, jamais inclus au hasard.

À lancer depuis la RACINE du monorepo (besoin du paquet zarma_numbers) :

    cd /Users/pc/project/zarma
    research/zarma-assistant/.venv/bin/python \
        research/zarma-assistant/scripts/build_asr_corpus.py /Users/pc/Music/ia
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import statistics
import subprocess
import sys
import wave
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

try:
    from zarma_numbers import generate
except ImportError:  # pragma: no cover - dépannage
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "zarma_numbers" / "src"))
    from zarma_numbers import generate

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "asr_corpus"

#: Signe de fichier -> forme zarma réellement prononcée dans les clips
#: ('÷' est noté ':' dans les noms de fichiers, '×' -> '*').
#:
#: ⚠️ Ces étiquettes ont été **fausses** jusqu'au 2026-07-29 : elles portaient
#: les formes courtes du lexique (`tonton`, `zabou`, `ingaybor`, `inafaysor`)
#: alors que les 4 locuteurs ont tous prononcé la forme longue. La mesure le
#: prouve sans ambiguïté — ces clips durent 1,40 s de médiane, contre 0,80 s
#: pour un nombre d'un mot et 1,35 s pour un nombre de trois mots. Ce n'était
#: pas une variation de prononciation mais la forme réelle de l'opérateur,
#: confirmée par le locuteur natif du projet.
#:
#: `lexicon.yaml` porte encore les formes courtes avec `status: unresolved`, et
#: la grammaire des expressions n'accepte donc pas encore ces formes longues :
#: c'est une correction distincte, à faire avant de décoder des expressions.
OPERATOR_WORDS = {
    "+": "kanga itonton",
    "-": "kanga izabou",
    "*": "kalangaybor",
    ":": "kan ifaysor",
}

#: Mêmes formes, indexées par le symbole utilisé dans les identifiants de
#: consigne de l'application ('/' et non ':').
OPERATOR_LONG = {
    "+": "kanga itonton",
    "-": "kanga izabou",
    "*": "kalangaybor",
    "/": "kan ifaysor",
}

#: Formes courtes du lexique, enregistrées en plus pour pouvoir décider plus
#: tard si l'application les accepte aussi.
OPERATOR_SHORT = {
    "+": "tonton",
    "-": "zabou",
    "*": "ingaybor",
    "/": "inafaysor",
}

#: Dossiers de la source qui ne contiennent pas d'énoncés ASR (banque de mots
#: pour la synthèse vocale : un mot isolé par fichier, déjà utilisée par l'app).
IGNORED_DIRS = {"pour le tts"}

#: Plusieurs dossiers correspondent à **une même personne** enregistrée lors de
#: deux séances différentes (information donnée par l'utilisateur, impossible à
#: deviner depuis les fichiers). Dossier -> identifiant de voix retenu.
#:
#: C'est la donnée la plus importante du fichier : séparer train et test sans en
#: tenir compte mettrait la même voix des deux côtés, et le score mesuré ne
#: dirait plus rien de ce qui se passera sur le téléphone d'un nouvel
#: utilisateur. Les séances restent distinctes dans la colonne `locuteur`
#: (conditions d'enregistrement différentes = variabilité utile), mais tout
#: découpage doit se faire sur `voix`.
VOICE_ALIASES = {"v4": "v1", "v8": "v2", "v5": "v3"}

#: ATTENTION : la numérotation du dossier `operation/` est **indépendante** de
#: celle des dossiers de nombres — son `v1` n'est pas le `v1` des nombres.
#: Correspondance donnée par l'utilisateur, indevinable depuis les fichiers :
#: locuteur du dossier operation -> séance des nombres.
#:
#: Elle est volontairement exprimée en séances et non en voix : c'est la forme
#: sous laquelle l'information a été donnée, et VOICE_ALIASES fait le reste. Les
#: 4 se résolvent ainsi en v3, v6, v2 et v1 — bien 4 personnes différentes.
OPERATION_SESSIONS = {"op1": "v5", "op2": "v6", "op3": "v8", "op4": "v4"}

EXPECTED_SAMPLE_RATE = 16_000
MIN_DURATION_S = 0.25
MAX_DURATION_S = 12.0

#: Fonds sonores à extraire du dossier TTS vers `noise/`, pour l'augmentation à
#: l'entraînement. Ce sont les seuls enregistrements du projet qui décrivent les
#: conditions d'écoute réelles (marché, rue, radio) — sans eux le modèle
#: n'apprend que du studio. Les « phrase quelconque » sont volontairement
#: exclues : ce n'est pas du bruit mais de la parole hors grammaire, utile plus
#: tard pour tester le rejet, pas pour bruiter des énoncés valides.
NOISE_PREFIXES = ("bruit ambiant", "music", "silence")

#: Durée conservée par fichier de bruit. Les originaux font 3 min 23 chacun ;
#: on tire des extraits de quelques secondes à l'entraînement, donc une minute
#: suffit largement et divise par trois la taille du lot à téléverser.
NOISE_SECONDS = 60


class Clip:
    """Un énoncé. `voice` est la personne réelle — c'est là-dessus, et jamais
    sur `speaker` (la séance), que doivent se faire les découpages
    train/val/test."""

    __slots__ = ("speaker", "voice", "label", "text", "duration", "source")

    def __init__(
        self, speaker: str, voice: str, label: str, text: str, duration: float, source: Path
    ) -> None:
        self.speaker, self.voice, self.label, self.text = speaker, voice, label, text
        self.duration, self.source = duration, source


def _probe(path: Path) -> tuple[float, int, int]:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate(), w.getframerate(), w.getnchannels()


#: Locuteurs de l'application d'enregistrement qui sont la **même personne**
#: qu'une voix du corpus manuel. Le code court garantit l'unicité entre
#: téléphones, pas entre campagnes : quelqu'un qui a enregistré les nombres en
#: juillet et les opérations en août est une seule voix, et les séparer
#: mettrait la même personne des deux côtés d'un découpage train/test.
#:
#: Clé = code de l'application, valeur = voix du corpus manuel.
#: Correspondances données par l'utilisateur (docs/qui-est-qui-locuteurs.md).
APP_VOICE_ALIASES: dict[str, str] = {
    "9vpj": "v2",   # haoua
    "3jun": "v9",   # leyhana
    "tksw": "v1",   # mounkaila
    "dfun": "v3",   # sharifa
    "632q": "v6",   # zouera
    "5x5b": "v7",   # abdoulaye
}

#: Prénoms réels, pour que les rapports parlent de personnes et non de codes.
#: Sans effet sur le traitement.
VOICE_NAMES = {
    "v1": "mounkaila", "v2": "haoua", "v3": "sharifa", "v6": "zouera",
    "v7": "abdoulaye", "v9": "leyhana", "v10": "limou", "v11": "amina",
    "app_2g4s": "daban",
    "app_vztk": "fatiya", "app_238h": "ous-mane", "app_k6jw": "rachida",
}


def _collect_app(source: Path, rejects: list[tuple[str, str, str]]) -> list[Clip]:
    """Ingestion des dossiers produits par l'application d'enregistrement :
    `<nom>-<code>/manifest.csv` plus un WAV par consigne.

    **Le nom de fichier fait foi sur le manifest.** Les deux doivent concorder,
    et le script signale toute divergence au lieu de choisir en silence : sur la
    première campagne, neuf clips nommés `500*5.wav` étaient déclarés `500/5`
    au manifest parce que les locuteurs avaient prononcé une multiplication là
    où la consigne affichait une division. Le manifest décrivait la consigne,
    le fichier décrivait l'enregistrement — c'est l'enregistrement qui compte.
    """
    import urllib.parse

    clips: list[Clip] = []
    for manifest in sorted(source.glob("*/manifest.csv")):
        directory = manifest.parent
        with manifest.open(encoding="utf-8") as handle:
            rows = {r["fichier"]: r for r in csv.DictReader(handle)}

        for path in sorted(directory.glob("*.wav")):
            rel = str(path.relative_to(source))
            label = urllib.parse.unquote(path.stem)
            row = rows.get(path.name)

            if row is None:
                # Fichier non déclaré : on cherche la ligne dont l'identifiant
                # correspond, pour pouvoir signaler la divergence précisément.
                row = next(
                    (r for r in rows.values() if urllib.parse.unquote(r["fichier"][:-4]) == label),
                    None,
                )
            if row is not None and row["identifiant"] != label:
                rejects.append(
                    (
                        "manifest divergent (le nom de fichier fait foi)",
                        rel,
                        f"fichier dit {label!r}, manifest dit {row['identifiant']!r}",
                    )
                )
                row = None

            text = _text_for_label(label)
            if text is None:
                rejects.append(("consigne non interprétable", rel, label))
                continue

            try:
                duration, rate, channels = _probe(path)
            except Exception as exc:  # noqa: BLE001
                rejects.append(("audio illisible", rel, str(exc)))
                continue
            if rate != EXPECTED_SAMPLE_RATE or channels != 1:
                rejects.append(("format inattendu", rel, f"{rate} Hz, {channels} canal/aux"))
                continue
            if not MIN_DURATION_S <= duration <= MAX_DURATION_S:
                rejects.append(("durée aberrante", rel, f"{duration:.2f} s"))
                continue

            code = directory.name.rsplit("-", 1)[-1]
            speaker = f"app_{code}"
            clips.append(
                Clip(speaker, APP_VOICE_ALIASES.get(code, speaker), label, text, duration, path)
            )
    return clips


def _text_for_label(label: str) -> str | None:
    """Forme zarma attendue pour un identifiant de consigne.

    Produite par `zarma_numbers`, jamais écrite à la main — sauf les mots
    d'opérateur, dont les formes longues réellement prononcées ne sont pas
    encore dans `lexicon.yaml` (cf. OPERATOR_WORDS).
    """
    import re

    if label.startswith("mot"):
        return OPERATOR_LONG.get(label[3:])
    if label.startswith("court"):
        return OPERATOR_SHORT.get(label[5:])
    match = re.fullmatch(r"(\d+)([-+*/])(\d+)", label)
    if match:
        operator = OPERATOR_LONG.get(match.group(2))
        if operator is None:
            return None
        try:
            return f"{generate(int(match.group(1)))} {operator} {generate(int(match.group(3)))}"
        except Exception:  # noqa: BLE001
            return None
    if label.isdigit():
        try:
            return generate(int(label))
        except Exception:  # noqa: BLE001
            return None
    return None


def _collect(source: Path, rejects: list[tuple[str, str, str]]) -> list[Clip]:
    clips: list[Clip] = []

    for directory in sorted(source.iterdir()):
        # Certains noms de dossier portent une espace finale.
        dir_name = directory.name.strip()
        if not directory.is_dir() or dir_name in IGNORED_DIRS:
            continue
        is_operations = dir_name == "operation"

        for path in sorted(directory.glob("*.wav")):
            rel = str(path.relative_to(source))
            # Certains noms portent une espace parasite en début/fin.
            stem = path.stem.strip()

            if is_operations:
                match = re.fullmatch(r"(v\d+)\s*([-+*:])", stem)
                if not match:
                    rejects.append(("nom illisible", rel, stem))
                    continue
                # `speaker` reste « opN » : ces mots ont été enregistrés à part,
                # c'est bien une séance distincte. Seule `voice` les rattache à
                # la personne, via la séance de nombres correspondante.
                speaker = f"op{match.group(1)[1:]}"
                session = OPERATION_SESSIONS.get(speaker)
                if session is None:
                    rejects.append(("locuteur operation non rattaché", rel, speaker))
                    continue
                voice = VOICE_ALIASES.get(session, session)
                sign = match.group(2)
                label, text = f"op{sign}", OPERATOR_WORDS[sign]
            else:
                match = re.fullmatch(r"(v\d+)\s*-\s*(\d+)", stem)
                if not match:
                    rejects.append(("étiquette absente ou illisible", rel, stem))
                    continue
                speaker, value = match.group(1), int(match.group(2))
                voice = VOICE_ALIASES.get(speaker, speaker)
                # Le nom de fichier fait foi sur le dossier : quelques clips ont
                # été rangés dans le dossier d'un autre locuteur.
                if speaker != dir_name:
                    rejects.append(
                        ("rangé chez un autre locuteur (rattaché d'après le nom)", rel, speaker)
                    )
                try:
                    text = generate(value)
                except Exception as exc:  # noqa: BLE001 - on veut le message brut
                    rejects.append(("hors grammaire zarma", rel, f"{value} : {exc}"))
                    continue
                label = str(value)

            try:
                duration, rate, channels = _probe(path)
            except Exception as exc:  # noqa: BLE001
                rejects.append(("audio illisible", rel, str(exc)))
                continue
            if rate != EXPECTED_SAMPLE_RATE or channels != 1:
                rejects.append(("format inattendu", rel, f"{rate} Hz, {channels} canal/aux"))
                continue
            if not MIN_DURATION_S <= duration <= MAX_DURATION_S:
                rejects.append(("durée aberrante", rel, f"{duration:.2f} s"))
                continue

            clips.append(Clip(speaker, voice, label, text, duration, path))

    return clips


def _export_noise(source: Path, output: Path) -> int:
    """Copie les fonds sonores en 16 kHz mono mono-canal, tronqués à
    NOISE_SECONDS. Passe par ffmpeg : les originaux sont en 44,1 kHz et le
    module `wave` de la stdlib ne rééchantillonne pas."""
    noise_dir = output / "noise"
    if noise_dir.exists():
        shutil.rmtree(noise_dir)

    candidates = [
        path
        for directory in source.iterdir()
        if directory.is_dir() and directory.name.strip() in IGNORED_DIRS
        for path in sorted(directory.glob("*.wav"))
        if path.stem.strip().lower().startswith(NOISE_PREFIXES)
    ]
    if not candidates:
        return 0

    noise_dir.mkdir(parents=True)
    exported = 0
    for path in candidates:
        target = noise_dir / (path.stem.strip().replace(" ", "_") + ".wav")
        result = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(path), "-t", str(NOISE_SECONDS),
             "-ac", "1", "-ar", str(EXPECTED_SAMPLE_RATE), str(target)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  bruit ignoré ({path.name}) : {result.stderr.strip()}")
            continue
        exported += 1
    return exported


def _speaker_key(speaker: str) -> tuple[int, int, str]:
    """Tri naturel : les voix du corpus manuel (`v3` avant `v10`), puis celles
    du dossier operation (`op1`…), puis celles de l'application, dont le code
    est alphanumérique et peut ne contenir aucun chiffre (`app_vztk`)."""
    if speaker.startswith("app_"):
        return (2, 0, speaker)
    digits = re.sub(r"\D", "", speaker)
    return (1 if speaker.startswith("op") else 0, int(digits) if digits else 0, speaker)


def _report(clips: list[Clip], rejects: list[tuple[str, str, str]]) -> None:
    speakers = sorted({c.speaker for c in clips}, key=_speaker_key)
    voices = sorted({c.voice for c in clips}, key=_speaker_key)
    total = sum(c.duration for c in clips)
    print(
        f"\n{len(clips)} clips retenus | {len(voices)} personnes "
        f"({len(speakers)} séances) | {total / 60:.1f} min d'audio"
    )

    print("\n--- par voix (une ligne = une personne) ---")
    for voice in voices:
        own = [c for c in clips if c.voice == voice]
        sessions = sorted({c.speaker for c in own}, key=_speaker_key)
        detail = f" [séances {' + '.join(sessions)}]" if len(sessions) > 1 else ""
        nom = VOICE_NAMES.get(voice, "")
        print(
            f"  {voice:>8} {nom:<26} {len(own):>3} clips, "
            f"{sum(c.duration for c in own) / 60:.1f} min{detail}"
        )

    with_expressions = {c.voice for c in clips if re.fullmatch(r"\d+[-+*/]\d+", c.label)}
    with_operators = {c.voice for c in clips if not c.label[0].isdigit()}
    print(
        f"\n  opérateurs isolés : {len(with_operators)}/{len(voices)} personnes"
        f"  |  expressions complètes : {len(with_expressions)}/{len(voices)} personnes"
    )

    print("\n--- couverture lexicale (chaque mot que la grammaire peut produire) ---")
    occurrences: Counter[str] = Counter()
    voices_by_word: defaultdict[str, set[str]] = defaultdict(set)
    for clip in clips:
        for word in clip.text.split():
            occurrences[word] += 1
            voices_by_word[word].add(clip.voice)
    for word, count in sorted(occurrences.items(), key=lambda kv: (kv[1], kv[0])):
        # Le nombre de voix compte plus que le nombre d'occurrences : un mot dit
        # 40 fois par 2 personnes reste inconnu pour une troisième.
        heard_by = len(voices_by_word[word])
        flag = "  <-- FAIBLE" if count < 20 or heard_by < len(voices) - 2 else ""
        print(f"  {word:<12} {count:>4} occurrences  {heard_by:>2}/{len(voices)} voix{flag}")

    numbers = sorted({c.label for c in clips if c.label.isdigit()}, key=int)
    expressions = sorted({c.label for c in clips if re.fullmatch(r"\d+[-+*/]\d+", c.label)})
    operators = sorted({c.label for c in clips if not c.label[0].isdigit()})
    print(f"\n--- {len(numbers)} valeurs numériques ---\n  {', '.join(numbers)}")
    print(f"\n--- {len(expressions)} expressions ---\n  {', '.join(expressions)}")
    print(f"\n--- {len(operators)} opérateurs isolés ---\n  {', '.join(operators)}")

    # Un clip nettement plus court/long que les autres énoncés de même longueur
    # de texte signale un découpage ou un étiquetage douteux.
    print("\n--- clips à revérifier (durée incohérente avec le texte) ---")
    by_length: defaultdict[int, list[Clip]] = defaultdict(list)
    for clip in clips:
        by_length[len(clip.text.split())].append(clip)
    suspicious = 0
    for group in by_length.values():
        median = statistics.median(c.duration for c in group)
        for clip in group:
            if clip.duration < median * 0.45 or clip.duration > median * 2.2:
                print(
                    f"  {clip.speaker}_{clip.label}  « {clip.text} »  "
                    f"{clip.duration:.2f} s (médiane {median:.2f} s)"
                )
                suspicious += 1
    if not suspicious:
        print("  aucun")

    print("\n--- fichiers écartés ---")
    if not rejects:
        print("  aucun")
    for kind, path, info in rejects:
        print(f"  [{kind}] {path} -> {info}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "sources",
        type=Path,
        nargs="+",
        help="Dossiers sources. Deux formats reconnus et détectés automatiquement : "
        "le corpus découpé à la main (dossiers v1/, v2/…) et les exports de "
        "l'application d'enregistrement (dossiers <nom>-<code>/ avec manifest.csv).",
    )
    parser.add_argument(
        "--output", type=Path, default=OUTPUT_DIR, help=f"Dossier de sortie (défaut {OUTPUT_DIR})"
    )
    args = parser.parse_args()
    args.source = args.sources[0]

    missing = [s for s in args.sources if not s.is_dir()]
    if missing:
        raise SystemExit("Source introuvable : " + ", ".join(str(s) for s in missing))

    rejects: list[tuple[str, str, str]] = []
    clips: list[Clip] = []
    for source in args.sources:
        # Détection du format : la présence de `*/manifest.csv` signe un export
        # de l'application d'enregistrement.
        if any(source.glob("*/manifest.csv")):
            found = _collect_app(source, rejects)
            kind = "application"
        else:
            found = _collect(source, rejects)
            kind = "découpage manuel"
        print(f"{source} : {len(found)} clips ({kind})")
        clips.extend(found)
    if not clips:
        raise SystemExit("Aucun clip exploitable trouvé.")

    seen: dict[tuple[str, str], Path] = {}
    for clip in clips:
        key = (clip.speaker, clip.label)
        if key in seen:
            rejects.append(("doublon", str(clip.source), f"déjà vu : {seen[key]}"))
        seen[key] = clip.source

    clips_dir = args.output / "clips"
    if clips_dir.exists():
        shutil.rmtree(clips_dir)
    clips_dir.mkdir(parents=True)

    clips.sort(key=lambda c: (_speaker_key(c.speaker), c.label))
    with (args.output / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["fichier", "voix", "locuteur", "etiquette", "texte_zarma", "duree_s"])
        for clip in clips:
            # Les identifiants d'expression contiennent `/` et `*`, impossibles
            # ou risqués dans un nom de fichier. On encode comme le fait
            # l'application (`10/2` -> `10%2F2`) ; l'étiquette vraie reste dans
            # la colonne `etiquette`, qui est la seule source pour l'entraînement.
            name = f"{clip.speaker}_{quote(clip.label, safe='')}.wav"
            # `copy` et non `copy2` : les 319 clips venus de l'application
            # portent une date 1979-11-30 (artefact du ZIP Android), que
            # `zipfile` refuse ensuite d'archiver. La date de modification d'un
            # clip ne porte aucune information utile — seule celle du manifest
            # compte.
            shutil.copy(clip.source, clips_dir / name)
            writer.writerow(
                [
                    f"clips/{name}",
                    clip.voice,
                    clip.speaker,
                    clip.label,
                    clip.text,
                    f"{clip.duration:.3f}",
                ]
            )

    noise_count = _export_noise(args.source, args.output)

    _report(clips, rejects)
    print(
        f"\nJeu de données écrit dans {args.output} "
        f"(manifest.csv + clips/ + {noise_count} fonds sonores dans noise/)"
    )


if __name__ == "__main__":
    main()
