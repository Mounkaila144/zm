"""Entraînement v1 du modèle ASR zarma embarqué — CTC caractère sur
wav2vec2-base, évalué en leave-one-voice-out.

À coller dans un notebook Colab (GPU T4), comme train_m2m100_cloud_gpu.py : ce
script n'a pas de dépendance au reste du dépôt et ne s'exécute pas en local
(torch/transformers ne sont pas installés sur le Mac, et 8 Go de mémoire
partagée ne suffisent pas — cf. README).

Préparation, en local puis téléversement :

    research/zarma-assistant/.venv/bin/python \\
        research/zarma-assistant/scripts/build_asr_corpus.py /Users/pc/Music/ia
    cd research/zarma-assistant/data && zip -r asr_corpus.zip asr_corpus

Puis dans Colab (runtime T4), après avoir déposé `asr_corpus.zip` et ce fichier
dans un dossier Drive `zarma_asr_v1` — passer par Drive et non par le panneau de
fichiers, une session gratuite se coupe et vide `/content` :

    from google.colab import drive; drive.mount('/content/drive')

    %cd /content
    !cp /content/drive/MyDrive/zarma_asr_v1/{asr_corpus.zip,train_asr_v1_colab.py} .
    !unzip -oq asr_corpus.zip
    !pip -q install -U transformers soundfile

    # Un seul repli d'abord (~10 min) pour valider la chaîne :
    !python train_asr_v1_colab.py --corpus asr_corpus --folds v7 \
        --output /content/drive/MyDrive/zarma_asr_v1/resultats


Trois décisions de conception, et pourquoi
------------------------------------------

**CTC au niveau caractère, pas au niveau mot.** Le corpus fait 12 minutes pour
39 mots : au niveau mot, `iyega` n'aurait que 11 exemples et n'apprendrait rien
de `iyye`. Au niveau caractère, les mots partagent leur évidence — le préfixe
`way-` est commun à `wayiddu`, `wayiyye`, `waytaci`, `wayhakkou`, `wayyegga`.
C'est aussi ce qu'attend `services/asr/app/decoding.py`, dont la contrainte de
durée raisonne en caractères par trame.

**Leave-one-voice-out plutôt qu'un découpage fixe.** Il n'y a que 8 personnes.
En réserver 2 pour le test amputerait le quart des données d'entraînement, et
un test sur 2 voix est trop instable pour comparer deux idées. On entraîne donc
8 fois en retirant une personne à chaque tour, et on moyenne. Le découpage se
fait sur la colonne `voix` du manifest, **jamais** sur `locuteur` : plusieurs
dossiers sont deux séances d'une même personne, et les mélanger mettrait la
même voix des deux côtés.

**Le décodage reste glouton ici.** Ce script mesure ce que le modèle acoustique
sait, seul. Le décodeur contraint (`decoding.py`, déjà écrit et testé) ne
s'ajoute qu'ensuite : le brancher tout de suite masquerait les faiblesses
acoustiques derrière la grammaire, et c'est justement ce qu'on veut voir en v1.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torchaudio
from torch.utils.data import DataLoader, Dataset
from transformers import Wav2Vec2Config, Wav2Vec2ForCTC, get_linear_schedule_with_warmup

SAMPLE_RATE = 16_000

#: `decoding.py` suppose blank = 0 (son Annexe D §1 : blank = 1 s'effondre).
#: L'identifiant du blank CTC doit donc rester 0 ici, sous peine de rendre les
#: logits inexploitables par le décodeur contraint.
BLANK_ID = 0
SPACE_TOKEN = "|"

#: Perturbations de vitesse, en couples (fréquence d'origine, fréquence cible)
#: **volontairement exprimés en petits entiers** et non en hertz réels.
#:
#: `torchaudio.functional.resample` construit un noyau dont le nombre de phases
#: vaut `new_freq // pgcd(orig, new)`. Demander 16 000 -> 17 777 Hz (vitesse
#: 0,9) donne un pgcd de 1, donc un noyau à 17 777 phases recalculé pour chaque
#: clip sur CPU : mesuré à ~15 min par époque au lieu de ~15 s. Avec (10, 9) le
#: rapport est identique mais le noyau tient en 9 phases.
#:
#: Le rapport longueur = cible/origine : (10, 9) raccourcit de 10 % donc
#: accélère, (10, 11) rallonge donc ralentit.
SPEED_RATIOS = ((10, 9), (20, 19), (1, 1), (20, 21), (10, 11))


# --------------------------------------------------------------------------- #
# Corpus
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Utterance:
    path: Path
    voice: str
    label: str
    text: str
    duration: float


@dataclass(frozen=True)
class Tokenizer:
    """Symboles CTC du zarma écrit.

    Les **lettres doublées sont des symboles uniques** (`aa`, `dd`, `gg`, `kk`,
    `ll`, `yy`), et c'est la décision la plus importante de ce fichier. Le
    décodage CTC fusionne les répétitions consécutives : un modèle qui émet
    `y a a m o` caractère par caractère produit `yamo`, jamais `yaamo`. CTC sait
    s'en sortir en glissant un blanc entre les deux `a`, mais c'est précisément
    ce qu'il apprend en dernier, et 230 des 545 énoncés du corpus contiennent
    une lettre doublée — on ne peut pas payer ce prix avec 12 minutes de
    données. En faisant de `aa` un symbole, le problème disparaît : plus aucune
    transcription de référence n'a deux symboles identiques adjacents.
    """

    vocab: dict[str, int]
    digraphs: frozenset[str]

    @property
    def inverse(self) -> dict[int, str]:
        # `<pad>` et `<unk>` ne doivent rien écrire dans la transcription.
        return {i: ("" if s.startswith("<") else s) for s, i in self.vocab.items()}

    def symbols(self, text: str) -> list[str]:
        text = text.replace(" ", SPACE_TOKEN)
        out: list[str] = []
        index = 0
        while index < len(text):
            pair = text[index : index + 2]
            if len(pair) == 2 and pair in self.digraphs:
                out.append(pair)
                index += 2
            else:
                out.append(text[index])
                index += 1
        return out

    def encode(self, text: str) -> list[int]:
        unknown = self.vocab["<unk>"]
        return [self.vocab.get(s, unknown) for s in self.symbols(text)]

    def decode(self, ids: list[int]) -> str:
        """Décodage CTC glouton : fusion des répétitions, retrait des blancs."""
        inverse = self.inverse
        out: list[str] = []
        previous = None
        for token in ids:
            if token != previous and token != BLANK_ID:
                out.append(inverse.get(token, ""))
            previous = token
        # Espaces multiples repliés : le modèle émet parfois deux séparateurs
        # séparés par un blanc (« cindi  gou »), que CTC ne fusionne donc pas.
        # Aucun texte zarma valide n'a deux espaces — ne pas normaliser ferait
        # compter comme fausses des transcriptions parfaites (c'était l'unique
        # erreur du repli v11).
        return " ".join("".join(out).replace(SPACE_TOKEN, " ").split())


def load_corpus(corpus_dir: Path) -> tuple[list[Utterance], Tokenizer]:
    import csv

    manifest = corpus_dir / "manifest.csv"
    if not manifest.exists():
        raise SystemExit(f"{manifest} introuvable — lancer build_asr_corpus.py d'abord.")

    utterances: list[Utterance] = []
    with manifest.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            utterances.append(
                Utterance(
                    path=corpus_dir / row["fichier"],
                    voice=row["voix"],
                    label=row["etiquette"],
                    text=row["texte_zarma"],
                    duration=float(row["duree_s"]),
                )
            )

    # Vocabulaire dérivé du corpus, jamais codé en dur : si la grammaire gagne
    # un mot, ses symboles suivent sans qu'on y pense.
    digraphs = frozenset(
        u.text[i : i + 2]
        for u in utterances
        for i in range(len(u.text) - 1)
        if u.text[i] == u.text[i + 1] and u.text[i] != " "
    )
    vocab = {"<pad>": BLANK_ID, "<unk>": 1, SPACE_TOKEN: 2}
    for symbol in sorted({c for u in utterances for c in u.text if c != " "} | set(digraphs)):
        vocab[symbol] = len(vocab)
    return utterances, Tokenizer(vocab=vocab, digraphs=digraphs)


def load_audio(path: Path) -> torch.Tensor:
    """Charge un fichier en mono 16 kHz.

    `torchaudio.load` reste le chemin rapide, mais son backend a changé
    plusieurs fois (sox, soundfile, torchcodec) selon les versions installées
    sur Colab ; `soundfile` sert de repli stable plutôt que de faire échouer
    l'entraînement sur un détail d'installation.
    """
    try:
        wave, rate = torchaudio.load(str(path))
        audio = wave.mean(dim=0)
    except Exception:  # noqa: BLE001 - dépend de la version installée
        import soundfile

        data, rate = soundfile.read(str(path), dtype="float32", always_2d=True)
        audio = torch.from_numpy(data).mean(dim=1)
    if rate != SAMPLE_RATE:
        audio = torchaudio.functional.resample(audio, rate, SAMPLE_RATE)
    return audio


# --------------------------------------------------------------------------- #
# Augmentation
# --------------------------------------------------------------------------- #


class Augmenter:
    """Bruit ambiant réel, variation de vitesse, variation de gain.

    Les fonds sonores viennent des enregistrements du projet (`noise/`) : ce
    sont les seuls qui décrivent les conditions d'écoute visées — marché, rue,
    radio. Sans eux le modèle n'apprend que du studio, alors qu'il tournera sur
    un téléphone au Niger.
    """

    def __init__(self, noise_dir: Path, enabled: bool = True) -> None:
        self.enabled = enabled
        self.noises: list[torch.Tensor] = []
        if not enabled:
            return
        for path in sorted(noise_dir.glob("*.wav")):
            self.noises.append(load_audio(path))
        if not self.noises:
            print(f"  (aucun fond sonore dans {noise_dir} — augmentation par bruit désactivée)")

    def __call__(self, audio: torch.Tensor) -> torch.Tensor:
        if not self.enabled:
            return audio

        # Vitesse : ±10 %. Très efficace sur les petits corpus ASR — c'est la
        # seule augmentation qui crée de nouvelles durées de phonèmes.
        orig, target = random.choice(SPEED_RATIOS)
        if orig != target:
            audio = torchaudio.functional.resample(audio, orig, target)

        if self.noises and random.random() < 0.6:
            noise = random.choice(self.noises)
            if noise.numel() > audio.numel():
                start = random.randint(0, noise.numel() - audio.numel() - 1)
                noise = noise[start : start + audio.numel()]
            else:
                noise = noise.repeat(audio.numel() // noise.numel() + 1)[: audio.numel()]
            snr_db = random.uniform(5.0, 25.0)
            speech_power = audio.pow(2).mean().clamp(min=1e-10)
            noise_power = noise.pow(2).mean().clamp(min=1e-10)
            scale = (speech_power / (noise_power * 10 ** (snr_db / 10))).sqrt()
            audio = audio + scale * noise

        audio = audio * random.uniform(0.7, 1.3)
        return audio.clamp(-1.0, 1.0)


class ZarmaDataset(Dataset):
    def __init__(
        self, utterances: list[Utterance], tokenizer: Tokenizer, augmenter: Augmenter | None
    ) -> None:
        self.utterances = utterances
        self.tokenizer = tokenizer
        self.augmenter = augmenter

    def __len__(self) -> int:
        return len(self.utterances)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, list[int]]:
        utterance = self.utterances[index]
        audio = load_audio(utterance.path)
        if self.augmenter is not None:
            audio = self.augmenter(audio)
        # wav2vec2 attend une entrée centrée réduite.
        audio = (audio - audio.mean()) / (audio.std() + 1e-7)
        return audio, self.tokenizer.encode(utterance.text)


def collate(batch: list[tuple[torch.Tensor, list[int]]]) -> dict[str, torch.Tensor]:
    audios, labels = zip(*batch)
    max_audio = max(a.numel() for a in audios)
    max_label = max(len(l) for l in labels)

    inputs = torch.zeros(len(batch), max_audio)
    targets = torch.full((len(batch), max_label), -100, dtype=torch.long)
    for i, (audio, label) in enumerate(zip(audios, labels)):
        inputs[i, : audio.numel()] = audio
        targets[i, : len(label)] = torch.tensor(label, dtype=torch.long)
    return {"input_values": inputs, "labels": targets}


# --------------------------------------------------------------------------- #
# Métriques
# --------------------------------------------------------------------------- #


def _edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, ref in enumerate(reference, start=1):
        current = [i]
        for j, hyp in enumerate(hypothesis, start=1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ref != hyp))
            )
        previous = current
    return previous[-1]


def error_rates(references: list[str], hypotheses: list[str]) -> dict[str, float]:
    char_errors = char_total = word_errors = word_total = exact = 0
    for reference, hypothesis in zip(references, hypotheses):
        char_errors += _edit_distance(list(reference), list(hypothesis))
        char_total += len(reference)
        word_errors += _edit_distance(reference.split(), hypothesis.split())
        word_total += len(reference.split())
        exact += reference == hypothesis
    return {
        "cer": char_errors / max(char_total, 1),
        "wer": word_errors / max(word_total, 1),
        # Le taux qui compte vraiment pour la calculatrice : une phrase à moitié
        # juste donne un mauvais nombre, donc un mauvais calcul.
        "exact": exact / max(len(references), 1),
    }


# --------------------------------------------------------------------------- #
# Entraînement
# --------------------------------------------------------------------------- #


def build_model(backbone: str, vocab_size: int, mask_time_prob: float) -> Wav2Vec2ForCTC:
    config = Wav2Vec2Config.from_pretrained(
        backbone,
        vocab_size=vocab_size,
        pad_token_id=BLANK_ID,
        ctc_loss_reduction="mean",
        # Une paire (audio court, texte long) rendrait la perte infinie et
        # ferait diverger tout le lot ; on la neutralise au lieu de la subir.
        ctc_zero_infinity=True,
        attention_dropout=0.1,
        hidden_dropout=0.1,
        feat_proj_dropout=0.05,
        layerdrop=0.05,
        # SpecAugment reste à la valeur par défaut de HuggingFace (0.05). Un
        # premier essai à 0.3 — choisi pour lutter contre le surapprentissage —
        # a produit un modèle n'émettant que des blancs : masquer un tiers des
        # trames d'énoncés d'une seconde retire trop de signal pour que le CTC
        # sorte de l'effondrement initial. Sur 12 minutes de données, le vrai
        # risque était le sous-apprentissage, pas l'inverse.
        mask_time_prob=mask_time_prob,
        mask_feature_prob=0.0,
    )
    model = Wav2Vec2ForCTC.from_pretrained(backbone, config=config, ignore_mismatched_sizes=True)
    # Les couches convolutives ont appris à extraire des traits acoustiques
    # généraux sur 960 h d'audio ; 12 minutes de zarma ne peuvent que les
    # dégrader.
    model.freeze_feature_encoder()
    return model


def transcribe(
    model: Wav2Vec2ForCTC,
    utterances: list[Utterance],
    tokenizer: Tokenizer,
    device: torch.device,
    batch_size: int,
) -> tuple[list[str], float]:
    """Transcrit sans augmentation. Renvoie aussi la part de trames prédites
    comme blanches : à 100 %, le modèle est effondré sur le blanc et toutes les
    métriques valent 1 — c'est le mode d'échec le plus fréquent du CTC sur
    petit corpus, et le distinguer d'un modèle simplement mauvais fait gagner
    des heures."""
    loader = DataLoader(
        ZarmaDataset(utterances, tokenizer, None),
        batch_size=batch_size,
        shuffle=False,
        collate_fn=collate,
    )
    was_training = model.training
    model.eval()
    hypotheses: list[str] = []
    blank_frames = total_frames = 0
    with torch.no_grad():
        for batch in loader:
            with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
                logits = model(input_values=batch["input_values"].to(device)).logits
            predictions = logits.argmax(dim=-1)
            blank_frames += int((predictions == BLANK_ID).sum())
            total_frames += predictions.numel()
            for sequence in predictions.cpu().tolist():
                hypotheses.append(tokenizer.decode(sequence))
    if was_training:
        model.train()
    return hypotheses, blank_frames / max(total_frames, 1)


def _constrained_decoder_available() -> bool:
    """Le décodeur contraint et la grammaire sont-ils importables ?

    Détermine aussi ce qu'un repli « complet » doit contenir : sans cette
    information, une reprise ne saurait pas distinguer un résultat calculé par
    une version antérieure du script d'un résultat à jour.
    """
    try:
        import decoding  # noqa: F401
        import zarma_numbers  # noqa: F401
    except ImportError:
        return False
    return True


def evaluate_constrained(
    model: Wav2Vec2ForCTC,
    utterances: list[Utterance],
    tokenizer: Tokenizer,
    device: torch.device,
) -> dict | None:
    """Décodage CTC **contraint à la grammaire**, et mesure du nombre reconnu.

    C'est la métrique de l'application : peu importe que la transcription soit
    exacte, ce qui compte est la valeur entière obtenue. Le décodeur
    (`services/asr/app/decoding.py`, déjà écrit et testé) ne peut émettre qu'une
    forme acceptée par l'automate, donc les erreurs qui produisent des non-mots
    disparaissent par construction.

    Renvoie aussi les confiances séparées entre bonnes et mauvaises réponses :
    c'est ce qui permettra de calibrer un seuil de rejet, seule défense contre
    les erreurs qui produisent un nombre *valide* mais faux.
    """
    try:
        from decoding import ConstrainedCtcDecoder, DecoderConfig, build_token_lexicon
        from zarma_numbers import (
            Expression,
            evaluate,
            load_expression_grammar,
            load_grammar,
            parse,
            parse_expression,
        )
    except ImportError as exc:
        print(f"  (décodage contraint ignoré : {exc})")
        return None

    def build(grammar):
        lexicon = build_token_lexicon(
            grammar,
            tokenizer.encode,
            separator=(tokenizer.vocab[SPACE_TOKEN],),
            blank_id=BLANK_ID,
            # Les prononciations portent les formes longues des opérateurs
            # (`kanga itonton`…), qui sont précisément ce que le modèle a appris
            # et ce que les gens disent. Les exclure rendrait toute expression
            # indécodable.
            include_pronunciations=True,
        )
        return ConstrainedCtcDecoder(grammar, lexicon, DecoderConfig())

    # Une grammaire par type d'énoncé, comme dans l'application : le décodeur
    # ne charge qu'une langue à la fois, et un nombre seul n'appartient pas à la
    # langue des expressions (ni l'inverse).
    decoders = {"nombre": build(load_grammar()), "expression": build(load_expression_grammar())}

    def attendu(label: str) -> tuple[str, int] | None:
        """(type d'énoncé, valeur attendue) — `None` si l'énoncé n'est pas une
        saisie valide de la calculatrice. C'est le cas des mots d'opérateur
        isolés : aucune des deux grammaires ne les accepte, et un utilisateur
        qui dirait seulement « kanga itonton » ne demanderait aucun calcul."""
        if label.isdigit():
            return "nombre", int(label)
        match = re.fullmatch(r"(\d+)([-+*/])(\d+)", label)
        if match:
            expression = Expression(
                left=int(match.group(1)), symbol=match.group(2), right=int(match.group(3))
            )
            try:
                return "expression", evaluate(expression).value
            except Exception:  # noqa: BLE001 - hors domaine : hors évaluation
                return None
        return None

    cibles = [(u, attendu(u.label)) for u in utterances]
    cibles = [(u, c) for u, c in cibles if c is not None]
    if not cibles:
        return None

    correct = 0
    good_confidence: list[float] = []
    bad_confidence: list[float] = []
    wrong: list[dict] = []
    # Trace complète de chaque décodage : n meilleures hypothèses et leurs
    # scores. Calibrer un seuil de rejet est alors une analyse locale et
    # instantanée, au lieu de 70 minutes de réentraînement par idée testée.
    trace: list[dict] = []
    model.eval()
    with torch.no_grad():
        for utterance, (genre, valeur_attendue) in cibles:
            audio = load_audio(utterance.path)
            audio = (audio - audio.mean()) / (audio.std() + 1e-7)
            # Une seule séquence à la fois : le décodeur lit des logits (T, V)
            # non rembourrés, et du remplissage fausserait le score CTC.
            logits = model(input_values=audio.unsqueeze(0).to(device)).logits
            result = decoders[genre].decode(logits[0].float().cpu().numpy())
            best = result.best

            value = None
            if best is not None:
                if genre == "nombre":
                    value = parse(best.text)
                else:
                    expression = parse_expression(best.text)
                    if expression is not None:
                        try:
                            value = evaluate(expression).value
                        except Exception:  # noqa: BLE001 - refus du domaine
                            value = None
            juste = value is not None and value == valeur_attendue

            # Écart de score entre la meilleure et la deuxième hypothèse. C'est
            # le signal qui manque à `confidence` : celle-ci compare le chemin
            # contraint au meilleur chemin libre, donc elle dit « est-ce un
            # nombre ? » et non « est-ce le bon nombre ? ». Quand le modèle
            # entend nettement un mot pour un autre, les deux questions ont des
            # réponses opposées — confiance 1,0 sur une valeur fausse.
            scores = [h.score for h in result.hypotheses]
            marge = round(scores[1] - scores[0], 4) if len(scores) > 1 else None

            trace.append(
                {
                    "etiquette": utterance.label,
                    "genre": genre,
                    "attendu": utterance.text,
                    "valeur_attendue": valeur_attendue,
                    "juste": juste,
                    "lu": value,
                    "confiance": round(result.confidence, 4),
                    "marge": marge,
                    "hypotheses": [
                        {"texte": h.text, "score": round(h.score, 4)}
                        for h in result.hypotheses[:3]
                    ],
                }
            )

            if juste:
                correct += 1
                good_confidence.append(result.confidence)
            else:
                bad_confidence.append(result.confidence)
                wrong.append(
                    {
                        "etiquette": utterance.label,
                        "attendu": utterance.text,
                        "obtenu": best.text if best is not None else "",
                        "lu": value,
                        "confiance": round(result.confidence, 3),
                        "marge": marge,
                    }
                )
    par_genre = {}
    for genre in ("nombre", "expression"):
        lot = [t for t in trace if t["genre"] == genre]
        if lot:
            par_genre[genre] = {
                "testes": len(lot),
                "exact": round(sum(t["juste"] for t in lot) / len(lot), 4),
            }

    return {
        "enonces_testes": len(cibles),
        "valeur_exacte": correct / len(cibles),
        # Nombres et expressions séparés : ce sont deux difficultés distinctes,
        # et une moyenne unique masquerait laquelle progresse.
        "par_genre": par_genre,
        # Les effectifs accompagnent les moyennes : « confiance des fausses =
        # 1,0 » ne veut pas dire la même chose sur 2 erreurs et sur 30.
        "n_justes": len(good_confidence),
        "n_fausses": len(bad_confidence),
        "confiance_correctes": round(float(np.mean(good_confidence)), 3) if good_confidence else None,
        "confiance_fausses": round(float(np.mean(bad_confidence)), 3) if bad_confidence else None,
        "erreurs": wrong[:10],
        "trace": trace,
    }


def save_model(
    model: Wav2Vec2ForCTC,
    tokenizer: Tokenizer,
    destination: Path,
    metadata: dict,
) -> None:
    """Écrit le modèle **et son tokenizer** — les deux sont inséparables.

    Les poids seuls ne valent rien : la tête CTC produit 30 colonnes dont
    l'ordre n'est défini que par le vocabulaire construit à partir du corpus.
    Sans `tokenizer.json`, personne (pas même nous) ne peut savoir que la
    colonne 23 est `z` ni que le symbole 5 est le digramme `dd`. C'est
    l'erreur classique qui rend un modèle entraîné définitivement inutilisable.
    """
    destination.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(destination)
    (destination / "tokenizer.json").write_text(
        json.dumps(
            {
                "vocab": tokenizer.vocab,
                "digraphs": sorted(tokenizer.digraphs),
                "blank_id": BLANK_ID,
                "space_token": SPACE_TOKEN,
                "sample_rate": SAMPLE_RATE,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (destination / "entrainement.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nModèle écrit dans {destination}")
    print("  - poids + config (format HuggingFace)")
    print("  - tokenizer.json : indispensable, les poids seuls sont inexploitables")


def _train_loop(
    train: list[Utterance],
    peek: list[Utterance],
    tokenizer: Tokenizer,
    augmenter: Augmenter,
    args: argparse.Namespace,
    device: torch.device,
) -> Wav2Vec2ForCTC:
    """Boucle d'entraînement, partagée par les replis et le modèle final."""
    loader = DataLoader(
        ZarmaDataset(train, tokenizer, augmenter),
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=collate,
        num_workers=2,
        drop_last=True,
    )
    model = build_model(args.backbone, len(tokenizer.vocab), args.mask_time_prob).to(device)

    # Deux taux d'apprentissage distincts. La tête CTC est initialisée au
    # hasard : elle doit bouger vite. L'encodeur, lui, porte 960 h de
    # pré-entraînement — c'est le seul capital du montage, et un taux unique de
    # 3e-4 l'a détruit en cinq époques (perte figée à 3,4 ≈ log(30), soit une
    # sortie uniforme : plus aucune information ne traversait le réseau).
    head_names = ("lm_head",)
    head = [p for n, p in model.named_parameters() if n.startswith(head_names)]
    encoder = [
        p
        for n, p in model.named_parameters()
        if not n.startswith(head_names) and p.requires_grad
    ]
    optimizer = torch.optim.AdamW(
        [{"params": encoder, "lr": args.lr}, {"params": head, "lr": args.head_lr}],
        weight_decay=0.005,
    )
    total_steps = len(loader) * args.epochs
    scheduler = get_linear_schedule_with_warmup(
        optimizer, int(0.1 * total_steps), total_steps
    )

    # Pendant les premiers pas, seule la tête apprend : l'encodeur est gelé le
    # temps que la projection cesse d'être aléatoire. C'est ce qui empêche les
    # gradients de bruit d'atteindre les couches pré-entraînées.
    for parameter in encoder:
        parameter.requires_grad_(False)
    encoder_frozen = True
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")

    model.train()
    started = time.time()
    step = 0
    for epoch in range(args.epochs):
        running = 0.0
        for batch in loader:
            if encoder_frozen and step >= args.head_only_steps:
                for parameter in encoder:
                    parameter.requires_grad_(True)
                encoder_frozen = False
                print(f"      (pas {step} : encodeur dégelé, lr {args.lr:g})")
            step += 1
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
                output = model(
                    input_values=batch["input_values"].to(device),
                    labels=batch["labels"].to(device),
                )
            scaler.scale(output.loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scale_before = scaler.get_scale()
            scaler.step(optimizer)
            scaler.update()
            # Si le scaler a détecté un dépassement, il a sauté le pas
            # d'optimisation : avancer quand même le planificateur décalerait le
            # taux d'apprentissage (c'est l'avertissement PyTorch au 1er pas).
            if scaler.get_scale() >= scale_before:
                scheduler.step()
            running += output.loss.item()

        elapsed = time.time() - started
        # Rythme affiché dès la première époque : deux heures sans une ligne, on
        # ne peut pas distinguer « ça travaille » de « ça patine ».
        if epoch == 0 or (epoch + 1) % 5 == 0 or epoch == args.epochs - 1:
            remaining = elapsed / (epoch + 1) * (args.epochs - epoch - 1)
            sample, blank_share = transcribe(model, peek, tokenizer, device, args.batch_size)
            print(
                f"    époque {epoch + 1:>3}/{args.epochs}  perte {running / len(loader):.3f}"
                f"  blancs {blank_share:.0%}"
                f"  ({elapsed / (epoch + 1):.1f} s/époque, ~{remaining / 60:.0f} min restantes)"
            )
            print(f"      train> « {sample[0] or '(vide)'} »   (attendu « {peek[0].text} »)")


    return model


def train_on(
    train: list[Utterance],
    peek: list[Utterance],
    tokenizer: Tokenizer,
    augmenter: Augmenter,
    args: argparse.Namespace,
    device: torch.device,
) -> Wav2Vec2ForCTC:
    """Entraîne un modèle sur `train`. Utilisé par les replis d'évaluation
    comme par l'entraînement final — une seule recette, donc le modèle livré
    est bien celui qui a été mesuré."""
    return _train_loop(train, peek, tokenizer, augmenter, args, device)


def run_fold(
    held_out: str,
    utterances: list[Utterance],
    tokenizer: Tokenizer,
    augmenter: Augmenter,
    args: argparse.Namespace,
    device: torch.device,
) -> dict:
    train = [u for u in utterances if u.voice != held_out]
    test = [u for u in utterances if u.voice == held_out]
    # Échantillon fixe du jeu d'entraînement, transcrit périodiquement. C'est le
    # diagnostic décisif : si l'entraînement lui-même reste vide, le problème
    # est l'optimisation ; s'il est bon et que seul le test est vide, c'est la
    # généralisation. Sans ça on attend la fin d'un repli pour l'apprendre.
    peek = train[:: max(1, len(train) // 3)][:3]

    model = train_on(train, peek, tokenizer, augmenter, args, device)

    hypotheses, blank_share = transcribe(model, test, tokenizer, device, args.batch_size)
    references = [u.text for u in test]
    metrics = error_rates(references, hypotheses)

    # Les mêmes métriques sur l'entraînement : c'est le seul moyen de séparer
    # « le modèle n'apprend pas » de « le modèle n'a pas généralisé à cette
    # voix ». Sans ce repère, un CER de 1,0 est indéchiffrable.
    train_sample = train[:: max(1, len(train) // 60)][:60]
    train_hypotheses, _ = transcribe(model, train_sample, tokenizer, device, args.batch_size)
    train_metrics = error_rates([u.text for u in train_sample], train_hypotheses)

    metrics.update(
        voix=held_out,
        clips_test=len(test),
        clips_train=len(train),
        blancs=round(blank_share, 3),
        cer_train=round(train_metrics["cer"], 3),
        exact_train=round(train_metrics["exact"], 3),
    )

    constrained = evaluate_constrained(model, test, tokenizer, device)
    if constrained is not None:
        metrics["contraint"] = constrained

    # Uniquement les vraies erreurs : trier les 5 pires sans filtrer remplissait
    # la liste de lignes « attendu == obtenu » dès qu'un repli avait moins de
    # 5 erreurs, et laissait croire à des fautes inexistantes.
    errors = [
        (ref, hyp, label)
        for ref, hyp, label in zip(references, hypotheses, (u.label for u in test))
        if ref != hyp
    ]
    worst = sorted(errors, key=lambda t: -_edit_distance(list(t[0]), list(t[1])))[:8]
    metrics["pires"] = [
        {"etiquette": label, "attendu": ref, "obtenu": hyp} for ref, hyp, label in worst
    ]
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("asr_corpus"))
    parser.add_argument("--output", type=Path, default=Path("resultats_asr_v1"))
    parser.add_argument("--backbone", default="facebook/wav2vec2-base")
    # Fixé sur la courbe observée du repli v7 : perte 0,17 et transcription
    # d'entraînement correcte dès l'époque 30-35, puis 80 époques d'oscillation
    # entre 0,02 et 0,19 sans aucun gain — ni sur les blancs, ni sur les
    # transcriptions. 50 époques couvrent la phase utile avec une marge.
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument(
        "--mask-time-prob",
        type=float,
        default=0.05,
        help="Force de SpecAugment (défaut 0.05, celui de HuggingFace ; 0.3 effondre le CTC)",
    )
    parser.add_argument("--batch-size", type=int, default=8)
    # 3e-4 partout détruisait l'encodeur pré-entraîné (perte figée à log(30)).
    # L'encodeur se déplace lentement, la tête vite.
    parser.add_argument("--lr", type=float, default=5e-5, help="taux de l'encodeur pré-entraîné")
    parser.add_argument("--head-lr", type=float, default=1e-3, help="taux de la tête CTC")
    parser.add_argument(
        "--head-only-steps",
        type=int,
        default=400,
        help="Pas pendant lesquels seule la tête CTC apprend, encodeur gelé (défaut 400)",
    )
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--no-augment", action="store_true")
    parser.add_argument(
        "--final",
        action="store_true",
        help="Entraîne sur TOUTES les voix et sauvegarde le modèle (pas d''évaluation)",
    )
    parser.add_argument(
        "--folds", default="", help="Voix à évaluer, séparées par des virgules (défaut : toutes)"
    )
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        print("/!\\ Aucun GPU détecté — sur CPU, les 8 replis prendront des heures.")

    utterances, tokenizer = load_corpus(args.corpus)
    voices = sorted({u.voice for u in utterances})
    if args.folds:
        voices = [v for v in args.folds.split(",") if v in voices]

    # Une paire (audio trop court, texte trop long) est infaisable en CTC :
    # wav2vec2 produit une trame par 20 ms, il en faut au moins une par
    # caractère. Mieux vaut le voir ici que de chercher plus tard pourquoi la
    # perte stagne.
    infeasible = [u for u in utterances if u.duration * 50 < len(u.text)]
    if infeasible:
        print(f"/!\\ {len(infeasible)} clips trop courts pour leur texte (ignorés par ctc_zero_infinity) :")
        for u in infeasible[:5]:
            print(f"    {u.path.name} « {u.text} » {u.duration:.2f}s")

    print(
        f"{len(utterances)} énoncés | {len(voices)} voix | "
        f"vocabulaire {len(tokenizer.vocab)} symboles, dont les doublées "
        f"{' '.join(sorted(tokenizer.digraphs))}"
    )
    print(
        f"backbone {args.backbone} | {args.epochs} époques | lot {args.batch_size} | "
        f"lr encodeur {args.lr:g} (gelé {args.head_only_steps} pas) | tête {args.head_lr:g} | "
        f"SpecAugment {args.mask_time_prob:g}"
    )

    args.output.mkdir(parents=True, exist_ok=True)
    augmenter = Augmenter(args.corpus / "noise", enabled=not args.no_augment)

    # Reprise après coupure. Une session Colab gratuite s'arrête sans préavis
    # (quota GPU épuisé, inactivité) ; relancer la même commande repart du repli
    # suivant au lieu de tout refaire. C'est la granularité qui vaut le coup :
    # un repli dure ~8 min, sauvegarder en cours de repli coûterait plus cher en
    # écritures Drive que ce qu'il ferait gagner.
    # Un repli n'est « fait » que s'il porte toutes les mesures que cette
    # version sait produire. Sans cette condition, relancer après avoir ajouté
    # le décodage contraint sautait les 8 replis et réaffichait l'ancienne
    # moyenne : le script semblait avoir tourné sans rien recalculer.
    want_constrained = _constrained_decoder_available()
    results_path = args.output / "resultats.json"
    results: list[dict] = []
    if results_path.exists():
        stored = json.loads(results_path.read_text(encoding="utf-8"))
        complete = [r for r in stored if not want_constrained or "contraint" in r]
        outdated = [r["voix"] for r in stored if r not in complete]
        results = complete
        done = {r["voix"] for r in complete}
        remaining = [v for v in voices if v not in done]
        if done or outdated:
            print(
                f"\nReprise : {len(done)} repli(s) complet(s) conservé(s)"
                + (
                    f", {len(outdated)} à refaire faute de mesure contrainte "
                    f"({', '.join(sorted(outdated))})"
                    if outdated
                    else ""
                )
                + f", {len(remaining)} à calculer."
            )
        voices = remaining

    if args.final:
        # Modèle à livrer : entraîné sur **toutes** les voix, sans rien tenir à
        # l'écart. Les replis servent à mesurer, celui-ci sert à déployer — les
        # confondre reviendrait à livrer un modèle amputé du huitième de ses
        # données pour rien.
        print(f"\n=== entraînement final sur les {len(voices)} voix ===")
        peek = utterances[:: max(1, len(utterances) // 3)][:3]
        model = train_on(utterances, peek, tokenizer, augmenter, args, device)
        save_model(
            model,
            tokenizer,
            args.output / "modele",
            {
                "backbone": args.backbone,
                "epoques": args.epochs,
                "lr_encodeur": args.lr,
                "lr_tete": args.head_lr,
                "pas_tete_seule": args.head_only_steps,
                "mask_time_prob": args.mask_time_prob,
                "enonces": len(utterances),
                "voix": sorted(voices),
                "note": "entraîné sur toutes les voix — mesurer avec les replis, pas avec ce modèle",
            },
        )
        return

    if not voices:
        print(
            "\nRien à calculer : tous les replis sont déjà complets. "
            f"Supprimer {results_path} pour tout refaire."
        )

    for voice in voices:
        print(f"\n=== repli : {voice} tenu à l'écart ===")
        metrics = run_fold(voice, utterances, tokenizer, augmenter, args, device)
        results.append(metrics)
        print(
            f"  test  : CER {metrics['cer']:.3f} | WER {metrics['wer']:.3f} | "
            f"exacts {metrics['exact']:.1%}"
        )
        print(
            f"  train : CER {metrics['cer_train']:.3f} | exacts {metrics['exact_train']:.1%} | "
            f"trames blanches {metrics['blancs']:.0%}"
        )
        if metrics["blancs"] > 0.99:
            print("  /!\\ modèle effondré sur le blanc — augmenter --epochs ou baisser --lr.")
        if "contraint" in metrics:
            c = metrics["contraint"]
            print(
                f"  GRAMMAIRE : valeur exacte {c['valeur_exacte']:.1%} "
                f"sur {c['enonces_testes']} énoncés "
                + " ".join(
                    f"[{g} {d['exact']:.0%} sur {d['testes']}]"
                    for g, d in c["par_genre"].items()
                )
                + " | confiance "
                f"{c['confiance_correctes']} (justes) vs {c['confiance_fausses']} (fausses)"
            )
        results_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if not results:
        return
    print("\n=== moyenne leave-one-voice-out ===")
    for metric in ("cer", "wer", "exact"):
        values = [r[metric] for r in results]
        print(
            f"  {metric:<6} {np.mean(values):.3f}  (min {min(values):.3f}, max {max(values):.3f})"
        )
    print(f"\nRésultats détaillés dans {args.output / 'resultats.json'}")


if __name__ == "__main__":
    main()
