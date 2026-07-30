#!/usr/bin/env python
"""Service ASR **local** : le vrai modèle, sur la machine de dev (story 6.1).

Sert le **même** contrat `POST /transcribe` que l'app Modal de
`services/asr/app/main.py`. Conséquence directe : l'API n'a rien à savoir de sa
présence — il suffit de la pointer dessus par configuration (NFR9) :

    ASR_MODE=ctc ASR_ENDPOINT_URL=http://127.0.0.1:8001

Pourquoi ce serveur existe
--------------------------

Sans lui, un développeur n'a le choix qu'entre le **MockRecognizer** (qui ne
reconnaît rien : il répète une transcription figée) et un **déploiement GPU
cloud**. Ni l'un ni l'autre ne permet de vérifier, sur un vrai téléphone, que
l'application entend ce qu'on lui dit. Ce serveur comble exactement ce trou.

Ce n'est **pas** un chemin de production : il tourne sur CPU/MPS, sans
authentification, en un seul processus. La production reste Modal.

Décodage contraint (story 5.6/6.1)
----------------------------------

Le chemin CTC ne fait pas d'``argmax`` trame par trame : les logits alimentent la
recherche en faisceau restreinte à la grammaire (`app/decoding.py`), en
**nombres** ou en **expressions** selon ``DECODE_GRAMMAR``. C'est indispensable
ici : en décodage libre, ce modèle transcrit `v1-2.wav` en caractères chinois —
la contrainte est ce qui ramène la sortie dans la langue.

Environnement
-------------

S'exécute dans l'env ASR isolé (`scripts/bench/README-local-asr.md`), jamais dans
le workspace uv racine :

    uv pip install --python asrenv/bin/python -e packages/zarma_numbers
    export DYLD_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_LIBRARY_PATH
    asrenv/bin/python services/asr/local_server.py --port 8001

Deux modèles interchangeables
-----------------------------

``--model-dir`` (ou ``ASR_MODEL_DIR``) charge le **modèle maison** : wav2vec2-base
affiné sur le corpus zarma, 94 M de paramètres, CTC caractère sur 30 symboles.
Sans cette option, le serveur charge Omnilingual comme auparavant.

    # modèle maison
    python services/asr/local_server.py --port 8001 --model-dir /srv/zarma/modele

    # Omnilingual (repli)
    python services/asr/local_server.py --port 8001

Mesuré sur les 529 nombres du corpus, à décodeur contraint identique et sans
qu'aucun des deux n'ait entendu la voix testée : **95,1 % de nombres exacts pour
le modèle maison contre 66,2 % pour Omnilingual**, sur les 12 voix sans
exception. Le modèle maison est aussi 3× plus léger et fonctionne hors-ligne.

Le contrat HTTP ne change pas : seul le champ ``model_version`` des réponses
indique lequel a répondu.

⚠️ L'extraction des logits d'Omnilingual (`_omnilingual_logits`) utilise des
membres privés du pipeline `omnilingual_asr` (`_build_audio_wavform_pipeline`,
`_create_batch_simple`) : l'API publique ne donne accès qu'au texte. C'est le
seul endroit à adapter si ce paquet change. Le modèle maison, lui, n'utilise que
l'API publique de `transformers`.
"""

from __future__ import annotations

import argparse
import hmac
import io
import json
import os
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dataclasses import replace
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

import numpy as np  # noqa: E402
from app.decoding import (  # noqa: E402
    ConstrainedCtcDecoder,
    DecoderConfig,
    DecodeResult,
    build_token_lexicon,
)
from app.http_form import MultipartError, parse_multipart  # noqa: E402
from app.transcription import build_transcribe_payload  # noqa: E402
from app.vad import analyse as analyse_silence  # noqa: E402

CTC_MODEL = "omniASR_CTC_300M_v2"
TARGET_SAMPLE_RATE = 16_000

#: Les ids spéciaux bas ne sont pas des étiquettes CTC (Annexe A §2 de la 5.6).
_MIN_REAL_TOKEN_ID = 3


def _decode_wav(raw: bytes) -> tuple[np.ndarray, int]:
    """Décode un WAV PCM16 mono en float32 [-1, 1]."""
    with wave.open(io.BytesIO(raw), "rb") as reader:
        sample_rate = reader.getframerate()
        frames = reader.readframes(reader.getnframes())
    samples = np.frombuffer(frames, dtype="<i2").astype("float32") / 32768.0
    return samples, sample_rate


def _select_placement(requested: str) -> tuple[str, object]:
    """Choisit (device, dtype) d'exécution du modèle. **C'est le choix décisif.**

    Le modèle est livré en **bfloat16**, format taillé pour les GPU récents.
    Sur le CPU d'un Mac il n'existe aucune instruction bfloat16 : PyTorch émule
    chaque opération, et la mesure est sans appel — sur 10 s d'audio,
    **33 s** en ``cpu/bfloat16`` contre **1,5 s** en ``cpu/float32`` et
    **0,8 s** en ``mps/float32``. Même modèle, mêmes poids, mêmes sorties
    (vérifié : 12/12 transcriptions identiques sur les enregistrements réels) —
    seul le format de calcul change.

    C'est ce qui faisait dépasser le délai de 30 s de l'API sur un énoncé de
    10 secondes.

    ⚠️ Concerne **uniquement ce serveur de développement**. En production
    (Modal, GPU A10G) le bfloat16 est natif et reste le bon choix : rien à
    changer dans ``app/main.py``.
    """
    import torch

    if requested == "cpu":
        return "cpu", torch.float32
    if requested == "mps":
        if not torch.backends.mps.is_available():
            raise SystemExit("MPS demandé mais indisponible sur cette machine.")
        return "mps", torch.float32
    # auto : le GPU intégré si présent, sinon le CPU — jamais le bfloat16 émulé.
    if torch.backends.mps.is_available():
        return "mps", torch.float32
    return "cpu", torch.float32


class Wav2Vec2Backend:
    """Modèle **maison** : wav2vec2-base affiné sur le corpus zarma, CTC au
    niveau caractère sur 30 symboles.

    Il remplace Omnilingual (300 M paramètres, hébergé) par 94 M embarquables :
    mesuré à 95,1 % de nombres exacts contre 66,2 %, sur les mêmes clips et avec
    le même décodeur contraint.

    Deux détails conditionnent la justesse et n'ont aucun signe extérieur s'ils
    sont faux — le modèle produirait simplement du charabia :

    - **L'encodeur doit être identique à celui de l'entraînement.** Les lettres
      doublées (`aa`, `dd`, `gg`, `kk`, `ll`, `yy`) sont des symboles uniques,
      pas deux caractères : sans cela le décodage CTC fusionne les répétitions
      et `yaamo` devient `yamo`. La liste est lue dans `tokenizer.json`, écrit
      par le script d'entraînement, jamais recopiée ici.
    - **La normalisation de l'entrée doit être identique** : centrée réduite par
      énoncé, comme pendant l'entraînement.
    """

    def __init__(self, model_dir: Path, *, device: str = "auto") -> None:
        import torch
        from transformers import Wav2Vec2ForCTC

        meta = json.loads((model_dir / "tokenizer.json").read_text(encoding="utf-8"))
        self._vocab: dict[str, int] = meta["vocab"]
        self._digraphs = frozenset(meta["digraphs"])
        self._space = meta.get("space_token", "|")
        self.blank_id = int(meta.get("blank_id", 0))
        self.name = f"zarma_w2v2_{model_dir.name}"

        print(f"Chargement du modèle maison depuis {model_dir}…", flush=True)
        started = time.perf_counter()
        self._model = Wav2Vec2ForCTC.from_pretrained(str(model_dir))
        self._device, self._dtype = _select_placement(device)
        self._model.to(device=self._device, dtype=self._dtype).eval()
        self._torch = torch
        print(
            f"  modèle prêt en {time.perf_counter() - started:.1f}s · "
            f"{sum(p.numel() for p in self._model.parameters()) / 1e6:.0f} M paramètres · "
            f"{len(self._vocab)} symboles · exécution {self._device}",
            flush=True,
        )

    def encode(self, text: str) -> list[int]:
        """Texte -> identifiants, en respectant les digrammes."""
        text = text.replace(" ", self._space)
        unknown = self._vocab["<unk>"]
        out: list[int] = []
        index = 0
        while index < len(text):
            pair = text[index : index + 2]
            if pair in self._digraphs:
                out.append(self._vocab.get(pair, unknown))
                index += 2
            else:
                out.append(self._vocab.get(text[index], unknown))
                index += 1
        return out

    def logits(self, samples: np.ndarray, sample_rate: int) -> np.ndarray:
        torch = self._torch
        audio = torch.from_numpy(np.asarray(samples, dtype="float32"))
        audio = (audio - audio.mean()) / (audio.std() + 1e-7)
        with torch.inference_mode():
            out = self._model(
                input_values=audio.unsqueeze(0).to(device=self._device, dtype=self._dtype)
            ).logits
        return out[0].detach().float().cpu().numpy()


class OmnilingualBackend:
    """Modèle Meta `omniASR_CTC_300M_v2` — le chemin historique, conservé comme
    repli. L'API publique du paquet ne donne accès qu'au texte : obtenir les
    logits impose de passer par des membres privés du pipeline."""

    name = CTC_MODEL

    def __init__(self, *, device: str = "auto") -> None:
        from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline

        print(f"Chargement du modèle {CTC_MODEL}…", flush=True)
        started = time.perf_counter()
        self._pipeline = ASRInferencePipeline(model_card=CTC_MODEL)
        self._device, self._dtype = _select_placement(device)
        self._pipeline.model.to(device=self._device, dtype=self._dtype)
        print(
            f"  modèle prêt en {time.perf_counter() - started:.1f}s "
            f"· exécution {self._device}/{str(self._dtype).replace('torch.', '')}",
            flush=True,
        )
        encoder = self._pipeline.tokenizer.create_encoder()
        self._encoder = encoder

    def encode(self, text: str) -> list[int]:
        ids = self._encoder(text)
        ids = ids.tolist() if hasattr(ids, "tolist") else list(ids)
        return [int(i) for i in ids if int(i) > _MIN_REAL_TOKEN_ID]

    def logits(self, samples: np.ndarray, sample_rate: int) -> np.ndarray:
        return _omnilingual_logits(self, samples, sample_rate)


class LocalAsr:
    """Modèle chargé une fois, décodeur compilé une fois."""

    def __init__(
        self,
        *,
        grammar_kind: str,
        config: DecoderConfig,
        model_dir: Path | None = None,
        device: str = "auto",
        threads: int | None = None,
    ) -> None:
        import torch

        if threads is not None:
            # Réglé dans le processus, et pas seulement via OMP_NUM_THREADS :
            # la variable d'environnement ne fixe que le pool OpenMP, alors que
            # `at::get_num_threads` gouverne aussi les noyaux qui ne passent pas
            # par OpenMP. Les deux doivent concorder, sinon on obtient plus de
            # fils que de cœurs et ils se disputent le CPU.
            torch.set_num_threads(threads)
            # Un seul énoncé à la fois : le parallélisme entre opérations n'a
            # rien à recouvrir et ses fils ne feraient que concurrencer ceux du
            # calcul lui-même.
            try:
                torch.set_num_interop_threads(1)
            except RuntimeError:
                pass  # déjà fixé (appel après la première opération parallèle)

        self._backend = (
            Wav2Vec2Backend(model_dir, device=device)
            if model_dir is not None
            else OmnilingualBackend(device=device)
        )
        # Le blank du décodeur suit celui du modèle : une valeur figée ici
        # rendrait les logits illisibles sans aucun message d'erreur.
        blank_id = getattr(self._backend, "blank_id", config.blank_id)
        if blank_id != config.blank_id:
            config = replace(config, blank_id=blank_id)

        from zarma_numbers.grammar import (
            load_calculator_grammar,
            load_expression_grammar,
            load_grammar,
        )

        if grammar_kind == "calculator":
            grammar = load_calculator_grammar()
        elif grammar_kind == "expressions":
            grammar = load_expression_grammar()
        else:
            grammar = load_grammar()
        encode = self._backend.encode

        separator = self._detect_separator(encode)
        lexicon = build_token_lexicon(
            grammar, encode, separator=separator, blank_id=config.blank_id
        )
        self._decoder = ConstrainedCtcDecoder(grammar, lexicon, config)
        print(
            f"  grammaire « {grammar.kind} » : {grammar.state_count} états, "
            f"{len(grammar.tokens)} mots · séparateur {separator}",
            flush=True,
        )
        self._warm_up()

    def _warm_up(self) -> None:
        """Première inférence à vide, pour ne pas la facturer au premier usager.

        Le premier passage sur le GPU intégré compile les noyaux de calcul et
        coûte ~1,5 s de plus que les suivants. La payer au démarrage évite de
        faire croire à une lenteur du produit lors du tout premier essai.
        """
        started = time.perf_counter()
        try:
            self._logits(np.zeros(TARGET_SAMPLE_RATE, dtype="float32"), TARGET_SAMPLE_RATE)
        except Exception as exc:  # noqa: BLE001 - l'échauffement n'est jamais bloquant
            print(f"  (échauffement ignoré : {type(exc).__name__})", flush=True)
            return
        print(f"  échauffement en {time.perf_counter() - started:.1f}s", flush=True)

    @staticmethod
    def _detect_separator(encode) -> tuple[int, ...]:
        """Ids que le tokenizer insère **entre** deux mots.

        Sondé plutôt que codé en dur : un tokenizer différent n'aurait aucune
        raison d'employer les mêmes ids, et une constante fausse ferait échouer
        tout le décodage sans message clair.
        """
        left, right = encode("waranka"), encode("hinza")
        together = encode("waranka hinza")
        if together[: len(left)] == left and together[len(together) - len(right) :] == right:
            return tuple(together[len(left) : len(together) - len(right)])
        return ()

    @property
    def model_name(self) -> str:
        """Identifiant du modèle chargé, tel qu'exposé dans les réponses."""
        return self._backend.name

    def _logits(self, samples: np.ndarray, sample_rate: int) -> np.ndarray:
        """Logits CTC ``(T, V)`` — ils ne quittent jamais ce processus."""
        return self._backend.logits(samples, sample_rate)


    def transcribe(self, wav_bytes: bytes) -> dict[str, object]:
        started = time.perf_counter()
        samples, sample_rate = _decode_wav(wav_bytes)
        audio_seconds = len(samples) / TARGET_SAMPLE_RATE

        # Élagage des bords muets **avant** le modèle. Le coût de l'inférence est
        # linéaire en trames : chaque seconde de silence retirée en tête ou en
        # queue est ~500 ms de calcul économisé, sans toucher au contenu parlé.
        mark = time.perf_counter()
        trimmed = analyse_silence(samples, sample_rate)
        vad_ms = int((time.perf_counter() - mark) * 1000)

        if trimmed.is_silent:
            # Rien à transcrire : on s'abstient tout de suite, sans payer le
            # passage du modèle (mesuré à 7,7 s sur 8 s de silence). La réponse
            # est celle d'un rejet — texte vide — donc le pipeline API décide
            # `repeat` par le chemin existant : aucune décision nouvelle ici.
            latency_ms = int((time.perf_counter() - started) * 1000)
            payload = build_transcribe_payload(
                DecodeResult(
                    hypotheses=(),
                    frame_count=0,
                    latency_ms=0,
                    reject_threshold=self._decoder.config.reject_threshold,
                ),
                model_version=self.model_name,
                latency_ms=latency_ms,
            )
            print(
                f"  → «  » (audio muet) · audio {audio_seconds:.1f}s · "
                f"modèle contourné · total {latency_ms} ms",
                flush=True,
            )
            return payload

        # Les étapes sont chronométrées séparément : sans cette ventilation,
        # diagnostiquer une lenteur revient à deviner.
        mark = time.perf_counter()
        logits = self._logits(trimmed.samples, sample_rate)
        infer_ms = int((time.perf_counter() - mark) * 1000)

        mark = time.perf_counter()
        result = self._decoder.decode(logits)
        decode_ms = int((time.perf_counter() - mark) * 1000)

        latency_ms = int((time.perf_counter() - started) * 1000)
        payload = build_transcribe_payload(
            result, model_version=self.model_name, latency_ms=latency_ms
        )
        trimmed_note = (
            f" · élagué {trimmed.trimmed_seconds:.1f}s" if trimmed.trimmed_seconds > 0.05 else ""
        )
        print(
            f"  → « {payload['text']} » (confiance {payload['acoustic_score']:.2f}) · "
            f"audio {audio_seconds:.1f}s{trimmed_note} · vad {vad_ms} ms · "
            f"modèle {infer_ms} ms · décodage {decode_ms} ms · total {latency_ms} ms",
            flush=True,
        )
        return payload


def _omnilingual_logits(backend, samples: np.ndarray, sample_rate: int) -> np.ndarray:
    """Logits d'Omnilingual, obtenus via les membres privés du pipeline.

    Isolé dans une fonction plutôt que dans la méthode du backend : c'est le
    seul endroit du projet qui dépende de l'API interne de `omnilingual_asr`,
    et donc le seul à revoir si le paquet change.
    """
    import torch
    from fairseq2.data.data_pipeline import DataPipeline, read_sequence
    from fairseq2.nn.batch_layout import BatchLayout

    pipeline = backend._pipeline  # noqa: SLF001
    builder = DataPipeline.zip(
        [
            pipeline._build_audio_wavform_pipeline(  # noqa: SLF001
                [{"waveform": samples, "sample_rate": sample_rate}]
            ).and_return(),
            read_sequence([None]).and_return(),
        ]
    )
    batch = next(
        iter(builder.bucket(1).map(pipeline._create_batch_simple).and_return())  # noqa: SLF001
    )
    # L'entrée doit suivre le modèle : la convertir aussi, sinon PyTorch refuse
    # le mélange de types (et, laissée en bfloat16, elle ramènerait toute
    # l'inférence au chemin émulé qu'on cherche justement à éviter).
    seqs = batch.source_seqs.to(device=backend._device, dtype=backend._dtype)  # noqa: SLF001
    layout = BatchLayout(seqs.shape, seq_lens=batch.source_seq_lens, device=seqs.device)
    with torch.inference_mode():
        logits, out_layout = pipeline.model(seqs, layout)
    length = int(list(out_layout.seq_lens)[0])
    return logits[0, :length].detach().float().cpu().numpy()


def _make_handler(
    asr: LocalAsr, *, token: str, slots: threading.BoundedSemaphore, queue_seconds: float
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
            pass  # journalisation applicative ci-dessous, pas une ligne par requête

        def _send(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            """Vérifie le secret partagé, s'il est configuré.

            L'API envoie ``Authorization: Bearer <ASR_ENDPOINT_TOKEN>``. Sans
            jeton configuré, le service reste ouvert — acceptable **uniquement**
            écouté sur ``127.0.0.1``, ce qui est le défaut.
            """
            if not token:
                return True
            expected = f"Bearer {token}"
            given = self.headers.get("Authorization", "")
            # Comparaison à temps constant : une comparaison naïve laisse fuir
            # le secret octet par octet.
            return hmac.compare_digest(given, expected)

        def do_GET(self) -> None:  # noqa: N802 - imposé par BaseHTTPRequestHandler
            if self.path.rstrip("/") in ("", "/health"):
                self._send(200, {"status": "ok", "model": asr.model_name})
            else:
                self._send(404, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802 - imposé par BaseHTTPRequestHandler
            if self.path.rstrip("/") != "/transcribe":
                self._send(404, {"error": "not_found"})
                return
            if not self._authorized():
                self._send(401, {"error": "unauthorized"})
                return

            length = int(self.headers.get("Content-Length", 0))
            try:
                form = parse_multipart(
                    self.rfile.read(length), self.headers.get("Content-Type", "")
                )
                wav = form.require_file("audio")
            except MultipartError as exc:
                self._send(400, {"error": "bad_request", "detail": str(exc)})
                return

            # Concurrence bornée : l'inférence sature le CPU, en lancer dix en
            # parallèle les ralentit toutes jusqu'au dépassement du délai côté
            # API. Mieux vaut faire patienter, puis **refuser franchement** que
            # de laisser la file grossir sans fin (l'appelant traite un échec
            # comme un repli sûr : texte vide → ``repeat``, jamais un nombre).
            if not slots.acquire(timeout=queue_seconds):
                print("  ⏳ saturé : requête refusée (503)", flush=True)
                self._send(503, {"error": "overloaded"})
                return
            try:
                self._send(200, asr.transcribe(wav))
            except Exception as exc:  # noqa: BLE001 - un échec ne doit pas tuer le serveur
                print(f"  ⛔ échec de transcription : {type(exc).__name__}: {exc}", flush=True)
                self._send(500, {"error": "transcription_failed"})
            finally:
                slots.release()

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Service ASR local (contrat /transcribe).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument(
        "--grammar",
        choices=("numbers", "expressions", "calculator"),
        default="calculator",
        help=(
            "Langue contrainte. `calculator` (défaut) accepte un nombre seul OU "
            "une opération — c'est ce que dicte réellement un utilisateur."
        ),
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=os.environ.get("ASR_MODEL_DIR") or None,
        help=(
            "Dossier du modèle maison (poids HuggingFace + tokenizer.json). "
            "Sans cette option, le serveur charge Omnilingual comme avant."
        ),
    )
    parser.add_argument(
        "--device",
        choices=("auto", "mps", "cpu"),
        default="auto",
        help="Où exécuter le modèle (défaut : auto — GPU intégré si présent).",
    )
    parser.add_argument("--beam-width", type=int, default=DecoderConfig().beam_width)
    parser.add_argument("--nbest", type=int, default=DecoderConfig().nbest)
    parser.add_argument(
        "--reject-threshold",
        type=float,
        default=DecoderConfig().reject_threshold,
        help="Seuil d'abstention sur la confiance de décodage (0 = jamais rejeter).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help=(
            "Inférences simultanées autorisées. Chaque worker occupe ~2 Go de RAM "
            "et sature ses cœurs : au-delà du nombre de vCPU / 2, elles se gênent."
        ),
    )
    parser.add_argument(
        "--queue-seconds",
        type=float,
        default=20.0,
        help="Attente maximale en file avant de répondre 503 (défaut : 20 s).",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=None,
        help=(
            "Fils de calcul PyTorch. Sur ce VPS (4 vCPU AMD sans AVX-512), "
            "l'efficacité parallèle s'effondre au-delà de 2 : mesurer avant de changer."
        ),
    )
    args = parser.parse_args(argv)

    # Le secret ne transite jamais par la ligne de commande (visible dans `ps`).
    token = os.environ.get("ASR_ENDPOINT_TOKEN", "")

    asr = LocalAsr(
        grammar_kind=args.grammar,
        model_dir=Path(args.model_dir) if args.model_dir else None,
        device=args.device,
        threads=args.threads,
        config=DecoderConfig(
            beam_width=args.beam_width,
            nbest=args.nbest,
            reject_threshold=args.reject_threshold,
        ),
    )
    handler = _make_handler(
        asr,
        token=token,
        slots=threading.BoundedSemaphore(max(1, args.workers)),
        queue_seconds=args.queue_seconds,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    exposed = args.host not in ("127.0.0.1", "localhost")
    print(
        f"ASR prêt sur http://{args.host}:{args.port} · "
        f"{args.workers} inférence(s) simultanée(s) · "
        f"authentification {'activée' if token else 'DÉSACTIVÉE'}\n"
        f"  → brancher l'API : ASR_MODE=ctc "
        f"ASR_ENDPOINT_URL=http://{args.host}:{args.port}",
        flush=True,
    )
    if exposed and not token:
        print(
            "  ⚠️  Écoute hors de localhost SANS jeton : n'importe qui peut "
            "consommer le modèle. Définir ASR_ENDPOINT_TOKEN.",
            flush=True,
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
