# services/asr

Service du modèle ASR **serverless GPU** (Modal) — charge les modèles Omnilingual
et expose `POST /transcribe`. Moteur vocal **remplaçable**, isolé du reste : l'API
ne l'appelle jamais en dur, uniquement via l'interface `SpeechRecognizer`
(`RemoteCtcRecognizer` / `RemoteLlmRecognizer` côté `services/api`).

## Isolation

- Image **lourde et séparée** de l'API (torch + `omnilingual-asr`), déployée et
  redémarrée indépendamment.
- **Hors workspace uv racine** → la CI reste **sans GPU**. Ce service ne fait pas
  partie des tests CI standard ; seul le smoke test réel (AC4) l'exerce, à la main.

## Modèles (poids Apache 2.0, chargés dans le service)

| Mode | Modèle | `lang` |
|------|--------|--------|
| `ctc` | `omniASR_CTC_300M_v2` | — (aucune) |
| `llm` | `omniASR_LLM_300M_v2` | `["dje_Latn"]` |

## Contrat `/transcribe`

```
POST /transcribe            (HTTPS Modal, secret Bearer)
multipart : audio (WAV PCM16 mono 16 kHz), model, lang? (JSON)
200 : { text, acoustic_score, candidates[], latency_ms, model_version }
```

## Décodage contraint à la grammaire (story 5.6)

Le chemin CTC ne fait plus d'`argmax` trame par trame. Les logits alimentent une
**recherche en faisceau restreinte à la grammaire des nombres zarma** : la sortie
appartient par construction à l'ensemble des formes valides `0`–`1 000 000`, ou
le service **s'abstient**.

### Pourquoi le décodage a lieu **ici** et non côté API

| Critère | Décoder côté service ASR (**retenu**) | Décoder côté API |
|---|---|---|
| Charge réseau | Seuls texte + scores transitent | `T × 10 288` flottants par requête (~1,4 Mo/s d'audio) |
| Couplage | Les logits restent une affaire interne au modèle | L'API dépendrait du vocabulaire du modèle — contraire à NFR9 |
| Latence | Aucun aller-retour supplémentaire | Sérialisation + transfert des logits |
| Taille d'image | `zarma_numbers` est du Python pur, négligeable dans une image torch | L'API resterait légère, mais au prix des deux points ci-dessus |

**Arbitrage** : le décodage est **interne au recognizer**, exécuté là où les
logits existent. `zarma_numbers` est ajouté à l'image Modal pour que la grammaire
soit disponible au bon endroit — **source unique**, jamais réécrite ici. Le
contrat `/transcribe` est inchangé (NFR9) ; l'API et le mobile ne bougent pas.

### Ce que le décodage change dans la réponse

- `text` : forme **canonique** valide (parseable par `zarma_numbers.parse`), ou
  `""` si l'audio ne ressemble pas à un nombre → le pipeline API décide `repeat`
  (FR21, jamais de nombre inventé).
- `acoustic_score` : **vrai** score, la confiance de décodage
  `exp(-(nll_contraint − nll_libre) / nb_tokens)` ∈ `[0, 1]`. Auparavant `1.0`
  en dur, ce qui rendait les signaux de marge et de confusion inopérants.
- `candidates[]` : les N meilleures hypothèses avec leurs scores — elles
  alimentent le signal de **marge** de la confiance composite.
- Champs de diagnostic : `decode_frames`, `decode_latency_ms`, `rejected`.

### Configuration (aucun paramètre en dur)

Tout passe par `AsrSettings` (`services/asr/app/config.py`), lu depuis
l'environnement / les secrets Modal :

| Variable | Défaut | Rôle |
|---|---|---|
| `DECODE_CONSTRAINED` | `true` | Active le décodage contraint (sinon glouton) |
| `DECODE_GRAMMAR` | `numbers` | Langue contrainte : `numbers` (epics 1–5) ou `expressions` (calculatrice vocale, story 6.1) |
| `DECODE_BEAM_WIDTH` | `64` | Largeur du faisceau |
| `DECODE_NBEST` | `5` | Hypothèses exposées dans `candidates[]` |
| `DECODE_BLANK_ID` | `0` | Id du blank CTC — **0**, surtout pas 1 (Annexe D §1) |
| `DECODE_LENGTH_EXPONENT` | `1.0` | Exposant `p` de la normalisation par longueur (optimum mesuré) |
| `DECODE_MIN_FRAMES_PER_TOKEN` | `1.0` | Contrainte de durée (`1.0` = faisabilité CTC) |
| `DECODE_EXACT_RESCORE` | `true` | Re-score forward CTC exact des finalistes |
| `DECODE_REJECT_THRESHOLD` | `0.0` | Seuil de rejet — **non calibré par défaut** |
| `DECODE_SEPARATOR_IDS` | `""` | Ids du séparateur de mots du tokenizer |

`DECODE_REJECT_THRESHOLD` vaut `0.0` (aucun rejet) tant qu'il n'a pas été calibré
sur un corpus dédié : un seuil non calibré serait pire que pas de rejet. Voir
`scripts/README.md` (section 5.6) pour la procédure de calibration, qui n'utilise
**jamais** le split de test (NFR10).

### Tests sans GPU

`decoding.py`, `transcription.py` et `config.py` sont **sans torch ni modal** et
couverts par `services/asr/tests/` en CI (logits en fixtures). Seul `main.py`
(runtime Modal) reste hors CI.

## Serveur local (`local_server.py`) — développement uniquement

Sert le **même** contrat `/transcribe`, avec le vrai modèle, sur la machine de
dev. C'est ce qui permet de vérifier sur un téléphone que l'application entend
réellement ce qu'on lui dit.

```bash
export DYLD_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_LIBRARY_PATH
asrenv/bin/python services/asr/local_server.py --port 8001
```

### ⚠️ Le piège de performance : bfloat16 sur CPU

Le modèle est livré en **bfloat16**, format taillé pour les GPU récents. Le CPU
d'un Mac n'a **aucune instruction bfloat16** : PyTorch émule chaque opération,
et l'inférence devient ~20× plus lente. Mesuré sur cette machine :

| Placement | 10 s d'audio | Facteur temps-réel |
|---|---|---|
| `cpu` / bfloat16 (avant) | **33 s** | ×3,3 |
| `cpu` / float32 | 1,5 s | ×0,15 |
| `mps` / float32 (**défaut**) | **0,8 s** | ×0,08 |

Les sorties sont **identiques** (12/12 transcriptions inchangées sur les
enregistrements réels) : seul le format de calcul change, pas les poids.

C'était la cause des « Le traitement a pris trop de temps » : un énoncé de 10 s
dépassait le délai de 30 s de l'API. Le placement est désormais automatique
(`--device auto|mps|cpu`).

> Ne concerne **que** ce serveur. Sur Modal (A10G) le bfloat16 est natif et
> reste le bon choix : `app/main.py` est inchangé.

### Lire les temps

Chaque requête journalise sa ventilation — sans elle, diagnostiquer une lenteur
revient à deviner :

```
→ « waranka cindi hinza tonton iwey cindi gou » (confiance 0.87)
  · audio 3.7s · modèle 1101 ms · décodage 1074 ms · total 2179 ms
```

Une fois le placement corrigé, modèle et décodage pèsent du même ordre. Le levier
restant côté décodage est `--beam-width` (défaut 256, choisi sur un critère de
latence en story 5.6) — à ne réduire que sur mesure.

## Déploiement

```bash
# Secrets Modal (hors Git) :
modal secret create zarma-asr-token ASR_ENDPOINT_TOKEN=…

# Déploiement indépendant de l'API :
modal deploy services/asr/app/main.py
```

Basculer l'API de Mock au modèle réel = **configuration seule** (aucun changement
d'API ni de mobile) :

```bash
# services/api/.env (hors Git)
ASR_MODE=ctc                 # ou llm
ASR_ENDPOINT_URL=https://…modal.run
ASR_ENDPOINT_TOKEN=…         # secret, jamais committé, jamais côté mobile
```

## Smoke test réel (AC4, hors CI)

```bash
ASR_ENDPOINT_URL=… ASR_ENDPOINT_TOKEN=… \
ASR_SMOKE_AUDIO=dataset/benchmark/<echantillon>.wav ASR_SMOKE_EXPECTED=372 \
uv run pytest services/asr/tests/smoke_real_recognizer.py -q
```

En cas d'échec/cold start côté endpoint, le recognizer replie sur `decision=repeat`
(jamais de nombre inventé) — voir `services/api/app/asr/remote.py`.
